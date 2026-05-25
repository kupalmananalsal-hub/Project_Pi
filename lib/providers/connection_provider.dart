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

class PiConnectionState {
  PiConnectionState({
    String host = AppSettings.defaultHost,
    int? port,
    this.isConnected = false,
    this.isConnecting = false,
    this.status,
    this.lastStatusAt,
    this.error,
  }) : host = host.trim().isEmpty ? AppSettings.defaultHost : host.trim(),
       port = AppSettings.normalizeBackendPort(port);

  final String host;
  final int port;
  final bool isConnected;
  final bool isConnecting;
  final SystemStatus? status;
  final DateTime? lastStatusAt;
  final String? error;

  PiConnectionState copyWith({
    String? host,
    int? port,
    bool? isConnected,
    bool? isConnecting,
    Object? status = _unset,
    Object? lastStatusAt = _unset,
    Object? error = _unset,
  }) {
    return PiConnectionState(
      host: host ?? this.host,
      port: AppSettings.normalizeBackendPort(port ?? this.port),
      isConnected: isConnected ?? this.isConnected,
      isConnecting: isConnecting ?? this.isConnecting,
      status: status == _unset ? this.status : status as SystemStatus?,
      lastStatusAt: lastStatusAt == _unset
          ? this.lastStatusAt
          : lastStatusAt as DateTime?,
      error: error == _unset ? this.error : error as String?,
    );
  }
}

class ConnectionController extends Notifier<PiConnectionState> {
  Timer? _statusTimer;
  bool _startupConnectScheduled = false;

  @override
  PiConnectionState build() {
    final settings = ref.watch(settingsProvider);
    ref.listen(settingsProvider, (previous, next) {
      if (previous != null &&
          (previous.host != next.host || previous.port != next.port)) {
        unawaited(connect(host: next.host, port: next.port));
        return;
      }
      if (!state.isConnected && !state.isConnecting) {
        state = state.copyWith(host: next.host, port: next.port);
      }
    });
    if (!_startupConnectScheduled) {
      _startupConnectScheduled = true;
      Future.microtask(() async {
        if (!ref.mounted) {
          return;
        }
        if (!state.isConnected && !state.isConnecting) {
          await connect(host: settings.host, port: settings.port);
        }
      });
    }
    ref.onDispose(_stopPolling);
    return PiConnectionState(host: settings.host, port: settings.port);
  }

  Future<void> connect({String? host, int? port}) async {
    final settings = ref.read(settingsProvider);
    final requestedHost = (host ?? settings.host).trim().isEmpty
        ? AppSettings.defaultHost
        : (host ?? settings.host).trim();
    final requestedPort = AppSettings.normalizeBackendPort(
      port ?? settings.port,
    );

    await ref.read(settingsProvider.notifier).updateHost(requestedHost);
    await ref.read(settingsProvider.notifier).updatePort(requestedPort);

    state = state.copyWith(
      host: requestedHost,
      port: requestedPort,
      isConnecting: true,
      isConnected: false,
      error: null,
    );

    try {
      final target = await _fetchStatusWithFallback(
        requestedHost,
        requestedPort,
      );
      ref.read(thermalProvider.notifier).connect(target.host, target.port);
      ref.read(audioProvider.notifier).connect(target.host, target.port);
      ref.read(alertsProvider.notifier).connect(target.host, target.port);
      unawaited(
        ref
            .read(noiseSuppressionProvider.notifier)
            .connect(target.host, target.port),
      );
      state = state.copyWith(
        host: target.host,
        port: target.port,
        isConnected: true,
        isConnecting: false,
        status: target.status,
        lastStatusAt: DateTime.now(),
        error: target.usedFallback
            ? 'Connected through ${AppSettings.fallbackHost}'
            : null,
      );
      _startPolling(target.host, target.port);
    } catch (error) {
      disconnect();
      state = state.copyWith(
        host: requestedHost,
        port: requestedPort,
        isConnected: false,
        isConnecting: false,
        status: null,
        lastStatusAt: null,
        error: _friendlyError(error),
      );
    }
  }

  void disconnect() {
    _stopPolling();
    ref.read(thermalProvider.notifier).disconnect();
    ref.read(audioProvider.notifier).disconnect();
    ref.read(alertsProvider.notifier).disconnect();
    ref.read(noiseSuppressionProvider.notifier).disconnect();
    state = state.copyWith(
      isConnected: false,
      isConnecting: false,
      status: null,
      lastStatusAt: null,
    );
  }

  Future<void> refreshStatus() async {
    if (!state.isConnected) {
      return;
    }
    try {
      final status = await PiApiService(
        host: state.host,
        port: state.port,
      ).fetchStatus();
      state = state.copyWith(
        status: status,
        lastStatusAt: DateTime.now(),
        error: null,
      );
    } catch (error) {
      state = state.copyWith(error: _friendlyError(error));
    }
  }

  void _startPolling(String host, int port) {
    _stopPolling();
    _statusTimer = Timer.periodic(const Duration(seconds: 5), (_) async {
      try {
        final status = await PiApiService(host: host, port: port).fetchStatus();
        state = state.copyWith(
          status: status,
          lastStatusAt: DateTime.now(),
          error: null,
        );
      } catch (error) {
        state = state.copyWith(error: _friendlyError(error));
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
        final status = await PiApiService(
          host: candidate,
          port: port,
        ).fetchStatus();
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
      return error.message ?? error.type.name;
    }
    return error.toString();
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
