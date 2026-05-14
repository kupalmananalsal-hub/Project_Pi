import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/alert_event.dart';
import '../providers/app_services_provider.dart';
import '../providers/settings_provider.dart';
import '../services/reconnecting_web_socket_service.dart';

final alertsProvider = NotifierProvider<AlertsController, AlertsState>(
  AlertsController.new,
);

class AlertsState {
  const AlertsState({
    this.history = const [],
    this.activeAlert,
    this.socketStatus = SocketConnectionStatus.disconnected,
    this.error,
  });

  final List<AlertEvent> history;
  final AlertEvent? activeAlert;
  final SocketConnectionStatus socketStatus;
  final String? error;

  AlertsState copyWith({
    List<AlertEvent>? history,
    Object? activeAlert = _unset,
    SocketConnectionStatus? socketStatus,
    Object? error = _unset,
  }) {
    return AlertsState(
      history: history ?? this.history,
      activeAlert: activeAlert == _unset
          ? this.activeAlert
          : activeAlert as AlertEvent?,
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
    state = state.copyWith(activeAlert: null);
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
    final nextHistory = [event, ...state.history];
    if (nextHistory.length > 100) {
      nextHistory.removeRange(100, nextHistory.length);
    }
    state = state.copyWith(history: nextHistory, error: null);

    if (event.isEmergencyKeyword) {
      state = state.copyWith(activeAlert: event);
      final sound = ref.read(settingsProvider).alertSound;
      unawaited(
        ref.read(alertRuntimeServiceProvider).startEmergency(event, sound),
      );
    }
  }
}

const _unset = Object();
