import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/alert_event.dart';
import '../providers/app_services_provider.dart';
import '../providers/settings_provider.dart';
import '../providers/thermal_provider.dart';
import '../services/reconnecting_web_socket_service.dart';

final alertsProvider = NotifierProvider<AlertsController, AlertsState>(
  AlertsController.new,
);

class AlertsState {
  const AlertsState({
    this.history = const [],
    this.pendingGuidance,
    this.pendingGuidanceHumanDetected = false,
    this.activeAlert,
    this.activeAlertHumanDetected = false,
    this.socketStatus = SocketConnectionStatus.disconnected,
    this.error,
  });

  final List<AlertEvent> history;
  final AlertEvent? pendingGuidance;
  final bool pendingGuidanceHumanDetected;
  final AlertEvent? activeAlert;
  final bool activeAlertHumanDetected;
  final SocketConnectionStatus socketStatus;
  final String? error;

  AlertsState copyWith({
    List<AlertEvent>? history,
    Object? pendingGuidance = _unset,
    bool? pendingGuidanceHumanDetected,
    Object? activeAlert = _unset,
    bool? activeAlertHumanDetected,
    SocketConnectionStatus? socketStatus,
    Object? error = _unset,
  }) {
    return AlertsState(
      history: history ?? this.history,
      pendingGuidance: pendingGuidance == _unset
          ? this.pendingGuidance
          : pendingGuidance as AlertEvent?,
      pendingGuidanceHumanDetected:
          pendingGuidanceHumanDetected ?? this.pendingGuidanceHumanDetected,
      activeAlert: activeAlert == _unset
          ? this.activeAlert
          : activeAlert as AlertEvent?,
      activeAlertHumanDetected:
          activeAlertHumanDetected ?? this.activeAlertHumanDetected,
      socketStatus: socketStatus ?? this.socketStatus,
      error: error == _unset ? this.error : error as String?,
    );
  }
}

class AlertsController extends Notifier<AlertsState> {
  ReconnectingWebSocketService<AlertEvent>? _socket;
  StreamSubscription<AlertEvent>? _alertSubscription;
  StreamSubscription<SocketConnectionStatus>? _statusSubscription;

  @override
  AlertsState build() {
    ref.onDispose(disconnect);
    return const AlertsState();
  }

  void connect(String host, int port) {
    disconnect();
    _socket = ReconnectingWebSocketService<AlertEvent>(
      uri: Uri(scheme: 'ws', host: host, port: port, path: '/ws/alerts'),
      parser: AlertEvent.fromMessage,
    );
    _alertSubscription = _socket!.messages.listen(
      _handleAlert,
      onError: (Object error) {
        state = state.copyWith(error: error.toString());
      },
    );
    _statusSubscription = _socket!.status.listen((status) {
      state = state.copyWith(socketStatus: status);
    });
    _socket!.connect();
  }

  Future<void> dismissActiveAlert() async {
    await ref.read(alertRuntimeServiceProvider).stopEmergency();
    state = state.copyWith(activeAlert: null, activeAlertHumanDetected: false);
  }

  Future<void> confirmGuidanceAlert() async {
    final event = state.pendingGuidance;
    if (event == null) {
      return;
    }
    final humanDetected = state.pendingGuidanceHumanDetected;
    state = state.copyWith(
      pendingGuidance: null,
      pendingGuidanceHumanDetected: false,
      activeAlert: event,
      activeAlertHumanDetected: humanDetected,
    );
    final sound = ref.read(settingsProvider).alertSound;
    await ref
        .read(alertRuntimeServiceProvider)
        .startEmergency(event, sound, vibrate: event.shouldVibrate);
  }

  void dismissGuidance() {
    state = state.copyWith(
      pendingGuidance: null,
      pendingGuidanceHumanDetected: false,
    );
  }

  void clearHistory() {
    state = state.copyWith(history: const [], error: null);
  }

  void disconnect() {
    _alertSubscription?.cancel();
    _alertSubscription = null;
    _statusSubscription?.cancel();
    _statusSubscription = null;
    _socket?.disconnect();
    _socket = null;
    if (ref.mounted) {
      state = state.copyWith(socketStatus: SocketConnectionStatus.disconnected);
    }
  }

  void _handleAlert(AlertEvent event) {
    if (event.isConnectionMessage) {
      return;
    }

    if (event.isHistorical) {
      _addAlertToHistorySilently(event);
      return;
    }

    final nextHistory = [event, ...state.history];
    if (nextHistory.length > 100) {
      nextHistory.removeRange(100, nextHistory.length);
    }
    state = state.copyWith(history: nextHistory, error: null);

    if (event.shouldShowDirectionGuidance) {
      final humanDetected =
          event.humanDetected || ref.read(thermalProvider).humanDetected;
      state = state.copyWith(
        pendingGuidance: event,
        pendingGuidanceHumanDetected: humanDetected,
      );
    }
  }

  void _addAlertToHistorySilently(AlertEvent event) {
    final nextHistory = [event, ...state.history];
    if (nextHistory.length > 100) {
      nextHistory.removeRange(100, nextHistory.length);
    }
    state = state.copyWith(history: nextHistory, error: null);
  }
}

const _unset = Object();
