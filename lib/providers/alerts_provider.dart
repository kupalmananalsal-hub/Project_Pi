import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/alert_event.dart';
import '../models/app_settings.dart';
import '../models/thermal_frame.dart';
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
    this.keywordNotice,
    this.activeAlert,
    this.activeAlertHumanDetected = false,
    this.activeAlertThermalFrame,
    this.socketStatus = SocketConnectionStatus.disconnected,
    this.error,
  });

  final List<AlertEvent> history;
  final AlertEvent? pendingGuidance;
  final bool pendingGuidanceHumanDetected;
  final AlertEvent? keywordNotice;
  final AlertEvent? activeAlert;
  final bool activeAlertHumanDetected;
  final ThermalFrame? activeAlertThermalFrame;
  final SocketConnectionStatus socketStatus;
  final String? error;

  AlertsState copyWith({
    List<AlertEvent>? history,
    Object? pendingGuidance = _unset,
    bool? pendingGuidanceHumanDetected,
    Object? keywordNotice = _unset,
    Object? activeAlert = _unset,
    bool? activeAlertHumanDetected,
    Object? activeAlertThermalFrame = _unset,
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
      keywordNotice: keywordNotice == _unset
          ? this.keywordNotice
          : keywordNotice as AlertEvent?,
      activeAlert: activeAlert == _unset
          ? this.activeAlert
          : activeAlert as AlertEvent?,
      activeAlertHumanDetected:
          activeAlertHumanDetected ?? this.activeAlertHumanDetected,
      activeAlertThermalFrame: activeAlertThermalFrame == _unset
          ? this.activeAlertThermalFrame
          : activeAlertThermalFrame as ThermalFrame?,
      socketStatus: socketStatus ?? this.socketStatus,
      error: error == _unset ? this.error : error as String?,
    );
  }
}

class AlertsController extends Notifier<AlertsState> {
  static const _keywordNoticeDuration = Duration(seconds: 5);

  ReconnectingWebSocketService<AlertEvent>? _socket;
  StreamSubscription<AlertEvent>? _alertSubscription;
  StreamSubscription<SocketConnectionStatus>? _statusSubscription;
  Timer? _keywordNoticeTimer;

  @override
  AlertsState build() {
    ref.onDispose(() {
      _keywordNoticeTimer?.cancel();
      disconnect();
    });
    return const AlertsState();
  }

  void connect(String host, int port) {
    disconnect();
    _socket = ReconnectingWebSocketService<AlertEvent>(
      uri: Uri(
        scheme: 'ws',
        host: host,
        port: AppSettings.normalizeBackendPort(port),
        path: '/ws/alerts',
      ),
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
    state = state.copyWith(
      activeAlert: null,
      activeAlertHumanDetected: false,
      activeAlertThermalFrame: null,
    );
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
      activeAlertThermalFrame: ref.read(thermalProvider).frame,
    );
    final sound = ref.read(settingsProvider).alertSound;
    await ref
        .read(alertRuntimeServiceProvider)
        .startEmergency(event, sound, vibrate: humanDetected);
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

  void replaceHistory(List<AlertEvent> history) {
    state = state.copyWith(history: List.unmodifiable(history), error: null);
  }

  void disconnect() {
    _alertSubscription?.cancel();
    _alertSubscription = null;
    _statusSubscription?.cancel();
    _statusSubscription = null;
    _keywordNoticeTimer?.cancel();
    _keywordNoticeTimer = null;
    _socket?.disconnect();
    _socket = null;
    if (ref.mounted) {
      state = state.copyWith(
        socketStatus: SocketConnectionStatus.disconnected,
        keywordNotice: null,
      );
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

    if (!event.shouldShowDirectionGuidance) {
      return;
    }

    final thermal = ref.read(thermalProvider);
    final humanDetected = event.humanDetected || thermal.humanDetected;
    if (humanDetected) {
      unawaited(_startThermalConfirmedAlert(event, thermal.frame));
      return;
    }

    _showKeywordNotice(event);
  }

  void _addAlertToHistorySilently(AlertEvent event) {
    final nextHistory = [event, ...state.history];
    if (nextHistory.length > 100) {
      nextHistory.removeRange(100, nextHistory.length);
    }
    state = state.copyWith(history: nextHistory, error: null);
  }

  void _showKeywordNotice(AlertEvent event) {
    _keywordNoticeTimer?.cancel();
    state = state.copyWith(keywordNotice: event, error: null);
    _keywordNoticeTimer = Timer(_keywordNoticeDuration, () {
      if (ref.mounted) {
        state = state.copyWith(keywordNotice: null);
      }
    });
  }

  Future<void> _startThermalConfirmedAlert(
    AlertEvent event,
    ThermalFrame? thermalFrame,
  ) async {
    _keywordNoticeTimer?.cancel();
    _keywordNoticeTimer = null;
    state = state.copyWith(
      keywordNotice: null,
      pendingGuidance: null,
      pendingGuidanceHumanDetected: false,
      activeAlert: event,
      activeAlertHumanDetected: true,
      activeAlertThermalFrame: thermalFrame,
      error: null,
    );
    final sound = ref.read(settingsProvider).alertSound;
    await ref
        .read(alertRuntimeServiceProvider)
        .startEmergency(event, sound, vibrate: true);
  }
}

const _unset = Object();
