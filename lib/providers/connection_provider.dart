import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/app_settings.dart';
import '../models/system_status.dart';
import '../services/pi_api_service.dart';
import 'alerts_provider.dart';
import 'audio_provider.dart';
import 'noise_suppression_provider.dart';
import 'settings_provider.dart';
import 'thermal_provider.dart';

final connectionProvider =
    NotifierProvider<ConnectionController, PiConnectionState>(
      ConnectionController.new,
    );

typedef PiStatusFetcher = Future<SystemStatus> Function(String host, int port);

final piStatusFetcherProvider = Provider<PiStatusFetcher>((ref) {
  return (host, port) => PiApiService(host: host, port: port).fetchStatus();
});

class PiConnectionChannels {
  const PiConnectionChannels({required this.connect, required this.disconnect});

  final void Function(String host, int port) connect;
  final void Function() disconnect;
}

final piConnectionChannelsProvider = Provider<PiConnectionChannels>((ref) {
  return PiConnectionChannels(
    connect: (host, port) {
      if (ref.read(settingsProvider).thermalMonitoringEnabled) {
        ref.read(thermalProvider.notifier).connect(host, port);
      } else {
        ref.read(thermalProvider.notifier).disconnect();
      }
      ref.read(audioProvider.notifier).connect(host, port);
      ref.read(alertsProvider.notifier).connect(host, port);
      unawaited(
        ref.read(noiseSuppressionProvider.notifier).connect(host, port),
      );
    },
    disconnect: () {
      ref.read(thermalProvider.notifier).disconnect();
      ref.read(audioProvider.notifier).disconnect();
      ref.read(alertsProvider.notifier).disconnect();
      ref.read(noiseSuppressionProvider.notifier).disconnect();
    },
  );
});

final piAutoConnectProvider = Provider<bool>((ref) => true);

enum PiConnectionStatus { disconnected, connecting, connected, error }

extension PiConnectionStatusLabel on PiConnectionStatus {
  String get label {
    switch (this) {
      case PiConnectionStatus.disconnected:
        return 'Disconnected';
      case PiConnectionStatus.connecting:
        return 'Connecting...';
      case PiConnectionStatus.connected:
        return 'Connected';
      case PiConnectionStatus.error:
        return 'Error';
    }
  }
}

class PiConnectionState {
  PiConnectionState({
    String host = AppSettings.defaultHost,
    int? port,
    PiConnectionStatus? connectionStatus,
    bool? isConnected,
    bool? isConnecting,
    this.userRequestedDisconnect = false,
    this.status,
    this.lastStatusAt,
    this.error,
  }) : host = host.trim().isEmpty ? AppSettings.defaultHost : host.trim(),
       port = AppSettings.normalizeBackendPort(port),
       connectionStatus =
           connectionStatus ??
           _statusFromLegacyFlags(
             isConnected: isConnected,
             isConnecting: isConnecting,
             error: error,
           );

  final String host;
  final int port;
  final PiConnectionStatus connectionStatus;
  final bool userRequestedDisconnect;
  final SystemStatus? status;
  final DateTime? lastStatusAt;
  final String? error;

  bool get isConnected => connectionStatus == PiConnectionStatus.connected;

  bool get isConnecting => connectionStatus == PiConnectionStatus.connecting;

  String get connectionStatusLabel => connectionStatus.label;

  PiConnectionState copyWith({
    String? host,
    int? port,
    PiConnectionStatus? connectionStatus,
    bool? isConnected,
    bool? isConnecting,
    bool? userRequestedDisconnect,
    Object? status = _unset,
    Object? lastStatusAt = _unset,
    Object? error = _unset,
  }) {
    final nextError = error == _unset ? this.error : error as String?;
    return PiConnectionState(
      host: host ?? this.host,
      port: AppSettings.normalizeBackendPort(port ?? this.port),
      connectionStatus:
          connectionStatus ??
          _statusFromLegacyFlags(
            isConnected: isConnected,
            isConnecting: isConnecting,
            error: nextError,
            fallback: this.connectionStatus,
          ),
      userRequestedDisconnect:
          userRequestedDisconnect ?? this.userRequestedDisconnect,
      status: status == _unset ? this.status : status as SystemStatus?,
      lastStatusAt: lastStatusAt == _unset
          ? this.lastStatusAt
          : lastStatusAt as DateTime?,
      error: nextError,
    );
  }

  static PiConnectionStatus _statusFromLegacyFlags({
    bool? isConnected,
    bool? isConnecting,
    String? error,
    PiConnectionStatus fallback = PiConnectionStatus.disconnected,
  }) {
    if (isConnecting == true) {
      return PiConnectionStatus.connecting;
    }
    if (isConnected == true) {
      return PiConnectionStatus.connected;
    }
    if (error != null && error.isNotEmpty) {
      return PiConnectionStatus.error;
    }
    if (isConnecting != null || isConnected != null) {
      return PiConnectionStatus.disconnected;
    }
    return fallback;
  }
}

class ConnectionController extends Notifier<PiConnectionState> {
  Timer? _statusTimer;
  bool _startupConnectScheduled = false;
  bool _updatingSettingsForConnect = false;

  @override
  PiConnectionState build() {
    final settings = ref.watch(settingsProvider);
    ref.listen(settingsProvider, (previous, next) {
      if (previous != null &&
          (previous.host != next.host || previous.port != next.port)) {
        if (_updatingSettingsForConnect) {
          return;
        }
        if (state.userRequestedDisconnect) {
          state = state.copyWith(host: next.host, port: next.port);
          return;
        }
        if (!ref.read(piAutoConnectProvider)) {
          state = state.copyWith(host: next.host, port: next.port);
          return;
        }
        unawaited(connect(host: next.host, port: next.port));
        return;
      }
      if (!state.isConnected && !state.isConnecting) {
        state = state.copyWith(host: next.host, port: next.port);
      }
    });
    if (ref.read(piAutoConnectProvider) && !_startupConnectScheduled) {
      _startupConnectScheduled = true;
      Future.microtask(() async {
        if (!ref.mounted) {
          return;
        }
        if (!state.userRequestedDisconnect &&
            !state.isConnected &&
            !state.isConnecting) {
          await connect(host: settings.host, port: settings.port);
        }
      });
    }
    ref.onDispose(_stopPolling);
    return PiConnectionState(host: settings.host, port: settings.port);
  }

  Future<void> connect({String? host, int? port}) async {
    final settings = ref.read(settingsProvider);
    final requestedHost = (host ?? settings.host).trim();
    final requestedPort = AppSettings.normalizeBackendPort(
      port ?? settings.port,
    );
    if (requestedHost.isEmpty) {
      state = state.copyWith(
        connectionStatus: PiConnectionStatus.error,
        isConnected: false,
        isConnecting: false,
        status: null,
        lastStatusAt: null,
        error: 'Pi IP or hostname is required.',
        userRequestedDisconnect: false,
      );
      return;
    }

    _updatingSettingsForConnect = true;
    try {
      await ref.read(settingsProvider.notifier).updateHost(requestedHost);
      await ref.read(settingsProvider.notifier).updatePort(requestedPort);
    } finally {
      _updatingSettingsForConnect = false;
    }

    state = state.copyWith(
      host: requestedHost,
      port: requestedPort,
      connectionStatus: PiConnectionStatus.connecting,
      error: null,
      userRequestedDisconnect: false,
    );

    try {
      final target = await _fetchStatusWithFallback(
        requestedHost,
        requestedPort,
      );
      ref.read(piConnectionChannelsProvider).connect(target.host, target.port);
      state = state.copyWith(
        host: target.host,
        port: target.port,
        connectionStatus: PiConnectionStatus.connected,
        status: target.status,
        lastStatusAt: DateTime.now(),
        error: target.usedFallback
            ? 'Connected through ${AppSettings.fallbackHost}'
            : null,
      );
      _startPolling(target.host, target.port);
    } catch (error) {
      _closeConnectionChannels();
      state = state.copyWith(
        host: requestedHost,
        port: requestedPort,
        connectionStatus: PiConnectionStatus.error,
        status: null,
        lastStatusAt: null,
        error: _friendlyError(error),
        userRequestedDisconnect: false,
      );
    }
  }

  void disconnect() {
    _closeConnectionChannels();
    state = state.copyWith(
      connectionStatus: PiConnectionStatus.disconnected,
      status: null,
      lastStatusAt: null,
      error: null,
      userRequestedDisconnect: true,
    );
  }

  Future<void> setThermalMonitoring(bool enabled) async {
    await ref.read(settingsProvider.notifier).setThermalMonitoring(enabled);
    if (!enabled) {
      ref.read(thermalProvider.notifier).disconnect();
      return;
    }
    if (state.isConnected) {
      ref.read(thermalProvider.notifier).connect(state.host, state.port);
    }
  }

  void _closeConnectionChannels() {
    _stopPolling();
    ref.read(piConnectionChannelsProvider).disconnect();
  }

  Future<void> refreshStatus() async {
    if (!state.isConnected) {
      return;
    }
    try {
      final status = await ref.read(piStatusFetcherProvider)(
        state.host,
        state.port,
      );
      state = state.copyWith(
        connectionStatus: PiConnectionStatus.connected,
        status: status,
        lastStatusAt: DateTime.now(),
        error: null,
      );
    } catch (error) {
      state = state.copyWith(
        connectionStatus: PiConnectionStatus.error,
        error: _friendlyError(error),
      );
    }
  }

  void _startPolling(String host, int port) {
    _stopPolling();
    _statusTimer = Timer.periodic(const Duration(seconds: 5), (_) async {
      try {
        final status = await ref.read(piStatusFetcherProvider)(host, port);
        state = state.copyWith(
          connectionStatus: PiConnectionStatus.connected,
          status: status,
          lastStatusAt: DateTime.now(),
          error: null,
        );
      } catch (error) {
        state = state.copyWith(
          connectionStatus: PiConnectionStatus.error,
          error: _friendlyError(error),
        );
      }
    });
  }

  void _stopPolling() {
    _statusTimer?.cancel();
    _statusTimer = null;
  }

  Future<_ResolvedTarget> _fetchStatusWithFallback(
    String host,
    int port,
  ) async {
    final candidates = <String>[
      host,
      if (host != AppSettings.fallbackHost) AppSettings.fallbackHost,
      if (host != AppSettings.mdnsFallbackHost) AppSettings.mdnsFallbackHost,
    ];

    Object? lastError;
    for (final candidate in candidates) {
      try {
        final status = await ref.read(piStatusFetcherProvider)(candidate, port);
        return _ResolvedTarget(
          host: candidate,
          port: port,
          status: status,
          usedFallback: candidate != host,
        );
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError ?? StateError('Unable to connect to Pi.');
  }

  String _friendlyError(Object error) {
    if (error is DioException) {
      switch (error.type) {
        case DioExceptionType.connectionTimeout:
        case DioExceptionType.receiveTimeout:
        case DioExceptionType.sendTimeout:
          return 'Connection timed out.';
        case DioExceptionType.cancel:
          return 'Connection cancelled.';
        case DioExceptionType.badResponse:
        case DioExceptionType.badCertificate:
        case DioExceptionType.connectionError:
        case DioExceptionType.unknown:
          return 'Unable to connect to Raspberry Pi.';
      }
    }
    return 'Unable to connect to Raspberry Pi.';
  }
}

class _ResolvedTarget {
  const _ResolvedTarget({
    required this.host,
    required this.port,
    required this.status,
    required this.usedFallback,
  });

  final String host;
  final int port;
  final SystemStatus status;
  final bool usedFallback;
}

const _unset = Object();
