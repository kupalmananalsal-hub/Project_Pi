import 'dart:async';
import 'dart:collection';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/alert_event.dart';
import '../models/app_settings.dart';
import '../models/thermal_frame.dart';
import '../providers/app_services_provider.dart';
import '../providers/settings_provider.dart';
import '../providers/thermal_provider.dart';
import '../services/reconnecting_web_socket_service.dart';
import '../services/alert_trace.dart';
import '../services/alert_delivery_service.dart';

final alertsProvider = NotifierProvider<AlertsController, AlertsState>(
  AlertsController.new,
);

class AlertsState {
  const AlertsState({
    this.history = const [],
    this.pendingGuidance,
    this.pendingGuidanceHumanDetected = false,
    this.keywordNotice,
    this.thermalSoftAlert = false,
    this.activeAlert,
    this.activeAlertHumanDetected = false,
    this.activeAlertThermalFrame,
    this.socketStatus = SocketConnectionStatus.disconnected,
    this.error,
    this.pairingState = AlertPairingState.legacy,
  });

  final List<AlertEvent> history;
  final AlertEvent? pendingGuidance;
  final bool pendingGuidanceHumanDetected;
  final AlertEvent? keywordNotice;
  final bool thermalSoftAlert;
  final AlertEvent? activeAlert;
  final bool activeAlertHumanDetected;
  final ThermalFrame? activeAlertThermalFrame;
  final SocketConnectionStatus socketStatus;
  final String? error;
  final AlertPairingState pairingState;

  AlertsState copyWith({
    List<AlertEvent>? history,
    Object? pendingGuidance = _unset,
    bool? pendingGuidanceHumanDetected,
    Object? keywordNotice = _unset,
    bool? thermalSoftAlert,
    Object? activeAlert = _unset,
    bool? activeAlertHumanDetected,
    Object? activeAlertThermalFrame = _unset,
    SocketConnectionStatus? socketStatus,
    Object? error = _unset,
    AlertPairingState? pairingState,
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
      thermalSoftAlert: thermalSoftAlert ?? this.thermalSoftAlert,
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
      pairingState: pairingState ?? this.pairingState,
    );
  }
}

class AlertsController extends Notifier<AlertsState> {
  static const _keywordNoticeDuration = Duration(seconds: 3);
  static const _thermalConfirmationWindow = Duration(seconds: 2);
  static const _thermalSoftAlertDuration = Duration(seconds: 4);
  static const _thermalSoftBeepCooldown = Duration(seconds: 7);

  ReconnectingWebSocketService<AlertEvent>? _socket;
  AlertDeliveryService? _delivery;
  int _connectionGeneration = 0;
  Future<void> _deliveryClose = Future.value();
  // Insertion-ordered so the oldest ids can be evicted; the durable inbox does the real dedup.
  final LinkedHashSet<String> _handledIds = LinkedHashSet();
  // Alerts replaced on screen by a newer one; dismissing the overlay confirms them too,
  // otherwise the Pi keeps replaying them as unconfirmed.
  final List<String> _supersededAlertIds = [];
  StreamSubscription<AlertEvent>? _alertSubscription;
  StreamSubscription<SocketConnectionStatus>? _statusSubscription;
  Timer? _keywordNoticeTimer;
  Timer? _pendingVoiceTimer;
  Timer? _thermalSoftAlertTimer;
  AlertEvent? _pendingVoiceEvent;
  DateTime? _pendingVoiceStartedAt;
  DateTime? _lastThermalHumanAt;
  ThermalFrame? _lastThermalHumanFrame;
  DateTime? _lastSoftBeepAt;

  @override
  AlertsState build() {
    final alertRuntimeService = ref.read(alertRuntimeServiceProvider);
    ref.listen<ThermalState>(thermalProvider, _handleThermalStateChanged);
    ref.onDispose(() {
      _keywordNoticeTimer?.cancel();
      _pendingVoiceTimer?.cancel();
      _thermalSoftAlertTimer?.cancel();
      alertRuntimeService.stopEmergency();
      disconnect();
    });
    return const AlertsState();
  }

  Future<void> connect(String host, int port) async {
    disconnect();
    final generation = _connectionGeneration;
    try {
      await _deliveryClose;
      final pairing = await CaregiverCredentials.endpointState(host);
      if (generation != _connectionGeneration || !ref.mounted) return;
      state = state.copyWith(pairingState: pairing, error: null);
      if (pairing == AlertPairingState.reconfigurationRequired) {
        state = state.copyWith(
          error:
              'Reliable alert delivery requires pairing for this endpoint. Re-pair with the Pi administrator or explicitly unpair.',
        );
        return;
      }
      final token = await CaregiverCredentials.token(host);
      if (generation != _connectionGeneration || !ref.mounted) return;
      if (token != null && token.isNotEmpty) {
        final installation = await CaregiverCredentials.installationId();
        final inbox = await AlertDeliveryService.openInbox(host, installation);
        if (generation != _connectionGeneration || !ref.mounted) return;
        _delivery = AlertDeliveryService(
          uri: Uri(
            scheme: 'ws',
            host: host,
            port: AppSettings.normalizeBackendPort(port),
            path: '/ws/alerts',
          ),
          installation: installation,
          token: token,
          inbox: inbox,
          onEvent: (event) {
            if (!ref.mounted || generation != _connectionGeneration) {
              return false;
            }
            // Durable delivery has already checked active state and confirmation.
            _handledIds.remove(event.eventId);
            _handleAlert(event);
            return identical(state.activeAlert, event);
          },
          isActive: (id) => ref.mounted && state.activeAlert?.eventId == id,
          onError: (error) {
            if (ref.mounted && generation == _connectionGeneration) {
              state = state.copyWith(error: error.toString());
            }
          },
          onStatus: (status) {
            if (ref.mounted && generation == _connectionGeneration) {
              state = state.copyWith(socketStatus: status);
            }
          },
        )..connect();
        return;
      }
      if (pairing == AlertPairingState.reliable) {
        state = state.copyWith(
          pairingState: AlertPairingState.reconfigurationRequired,
          error: 'Pairing credential unavailable. Re-pair before connecting.',
        );
        return;
      }
    } catch (error) {
      if (ref.mounted && generation == _connectionGeneration) {
        state = state.copyWith(error: 'Alert delivery setup failed: $error');
      }
      return;
    }
    _socket = ReconnectingWebSocketService<AlertEvent>(
      uri: Uri(
        scheme: 'ws',
        host: host,
        port: AppSettings.normalizeBackendPort(port),
        path: '/ws/alerts',
      ),
      parser: (message) {
        try {
          return AlertEvent.fromMessage(message);
        } catch (error) {
          String? eventId;
          try {
            final decoded = message is String ? jsonDecode(message) : message;
            if (decoded is Map) eventId = decoded['event_id']?.toString();
          } catch (_) {}
          traceAlert('flutter_parse', eventId, 'failed', {
            'error_type': error.runtimeType.toString(),
          });
          rethrow;
        }
      },
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
    final dismissed = state.activeAlert;
    final confirmedIds = [
      ..._supersededAlertIds,
      if (dismissed?.eventId != null) dismissed!.eventId!,
    ];
    _supersededAlertIds.clear();
    for (final id in confirmedIds) {
      unawaited(
        _delivery?.confirm(id).catchError((Object error) {
              traceAlert('ack_user_confirmed', id, 'failed', {
                'reason': error.runtimeType.toString(),
              });
            }) ??
            Future.value(),
      );
    }
    await ref.read(alertRuntimeServiceProvider).stopEmergency();
    if (!ref.mounted || !identical(state.activeAlert, dismissed)) return;
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

  @visibleForTesting
  void handleAlertForTest(AlertEvent event) {
    _handleAlert(event);
  }

  @visibleForTesting
  void handleThermalStateForTest(ThermalState? previous, ThermalState next) {
    _handleThermalStateChanged(previous, next);
  }

  void replaceHistory(List<AlertEvent> history) {
    state = state.copyWith(history: List.unmodifiable(history), error: null);
  }

  void disconnect() {
    _connectionGeneration++;
    final delivery = _delivery;
    _delivery = null;
    if (delivery != null) _deliveryClose = delivery.dispose();
    _alertSubscription?.cancel();
    _alertSubscription = null;
    _statusSubscription?.cancel();
    _statusSubscription = null;
    _keywordNoticeTimer?.cancel();
    _keywordNoticeTimer = null;
    _pendingVoiceTimer?.cancel();
    _pendingVoiceTimer = null;
    _pendingVoiceEvent = null;
    _pendingVoiceStartedAt = null;
    _thermalSoftAlertTimer?.cancel();
    _thermalSoftAlertTimer = null;
    _socket?.disconnect();
    _socket = null;
    if (ref.mounted) {
      state = state.copyWith(
        socketStatus: SocketConnectionStatus.disconnected,
        keywordNotice: null,
        thermalSoftAlert: false,
      );
    }
  }

  void _handleAlert(AlertEvent event) {
    traceAlert('flutter_receive', event.eventId, 'parsed', {
      'decision_state': event.rawDecisionState,
      'stream_type': event.streamType,
    });
    if (event.isConnectionMessage) {
      return;
    }

    if (event.isHistorical) {
      traceAlert('provider_disposition', event.eventId, 'history_only');
      _addAlertToHistorySilently(event);
      return;
    }

    if (event.eventId != null && !_handledIds.add(event.eventId!)) {
      traceAlert('provider_disposition', event.eventId, 'duplicate_ignored');
      return;
    }
    if (_handledIds.length > 256) _handledIds.remove(_handledIds.first);

    final nextHistory = [event, ...state.history];
    if (nextHistory.length > 100) {
      nextHistory.removeRange(100, nextHistory.length);
    }
    state = state.copyWith(history: nextHistory, error: null);

    if (event.duplicateEvent) {
      traceAlert('provider_disposition', event.eventId, 'duplicate_ignored');
      return;
    }

    if (event.hasAuthoritativeDecision) {
      _handleAuthoritativeAlert(event);
      return;
    }

    _handleLegacyAlert(event);
  }

  void _handleAuthoritativeAlert(AlertEvent event) {
    switch (event.decisionState) {
      case AlertDecisionState.suppressed:
        traceAlert('provider_disposition', event.eventId, 'suppressed', {
          'reason': event.decisionReason,
        });
        _clearPendingVoiceState(clearKeywordNotice: true);
        return;
      case AlertDecisionState.advisory:
        traceAlert('provider_disposition', event.eventId, 'notice', {
          'reason': event.decisionReason,
        });
        _clearPendingVoiceState();
        if (event.isRecognizedConfiguredKeyword) {
          _showKeywordNotice(event);
          unawaited(
            ref.read(alertRuntimeServiceProvider).playSoftThermalBeep(),
          );
        }
        return;
      case AlertDecisionState.confirmed:
      case AlertDecisionState.critical:
        traceAlert(
          'provider_disposition',
          event.eventId,
          'emergency_candidate',
          {'decision_state': event.rawDecisionState},
        );
        unawaited(_startAuthoritativeEmergencyAlert(event));
        return;
      case AlertDecisionState.systemFault:
        traceAlert('provider_disposition', event.eventId, 'system_fault', {
          'reason': event.decisionReason,
        });
        _clearPendingVoiceState(clearKeywordNotice: true);
        state = state.copyWith(
          thermalSoftAlert: false,
          error: 'Pi fault: ${event.keyword}. Alerts may not be detected.',
        );
        return;
      case AlertDecisionState.unknown:
        traceAlert('provider_disposition', event.eventId, 'unknown_decision', {
          'reason': event.rawDecisionState,
        });
        _clearPendingVoiceState(clearKeywordNotice: true);
        state = state.copyWith(
          thermalSoftAlert: false,
          error: 'Unknown backend alert decision: ${event.rawDecisionState}',
        );
        return;
    }
  }

  void _handleLegacyAlert(AlertEvent event) {
    if (event.source == 'manual_button_single') {
      _showKeywordNotice(event);
      unawaited(ref.read(alertRuntimeServiceProvider).playSoftThermalBeep());
      return;
    }

    if (!event.shouldShowDirectionGuidance) {
      return;
    }

    assert(() {
      debugPrint(
        'Alert WS live keyword=${event.keyword} '
        'humanDetected=${event.humanDetected} '
        'source=${event.source ?? "unknown"}',
      );
      return true;
    }());

    if (_hasThermalPresenceFor(event)) {
      unawaited(
        _startThermalConfirmedAlert(
          event,
          ref.read(thermalProvider).frame ?? _lastThermalHumanFrame,
        ),
      );
      return;
    }

    if (event.isRecognizedConfiguredKeyword) {
      _showKeywordNotice(event);
      unawaited(ref.read(alertRuntimeServiceProvider).playSoftThermalBeep());
    }
    _startThermalConfirmationWindow(event);
  }

  void _clearPendingVoiceState({bool clearKeywordNotice = false}) {
    _pendingVoiceTimer?.cancel();
    _pendingVoiceTimer = null;
    _pendingVoiceEvent = null;
    _pendingVoiceStartedAt = null;
    if (clearKeywordNotice) {
      _keywordNoticeTimer?.cancel();
      _keywordNoticeTimer = null;
      state = state.copyWith(keywordNotice: null);
    }
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
    state = state.copyWith(
      keywordNotice: event,
      thermalSoftAlert: false,
      error: null,
    );
    _keywordNoticeTimer = Timer(_keywordNoticeDuration, () {
      if (ref.mounted) {
        state = state.copyWith(keywordNotice: null);
      }
    });
  }

  void _startThermalConfirmationWindow(AlertEvent event) {
    _pendingVoiceTimer?.cancel();
    _pendingVoiceEvent = event;
    _pendingVoiceStartedAt = DateTime.now();
    _pendingVoiceTimer = Timer(_thermalConfirmationWindow, () {
      if (_pendingVoiceEvent == event) {
        _pendingVoiceEvent = null;
        _pendingVoiceStartedAt = null;
      }
    });
  }

  bool _hasThermalPresenceFor(AlertEvent event) {
    if (event.humanDetected) {
      return true;
    }
    final thermal = ref.read(thermalProvider);
    if (thermal.humanDetected) {
      return true;
    }
    final lastThermalAt = _lastThermalHumanAt;
    if (lastThermalAt == null) {
      return false;
    }
    return DateTime.now().difference(lastThermalAt) <=
        _thermalConfirmationWindow;
  }

  void _handleThermalStateChanged(ThermalState? previous, ThermalState next) {
    final wasDetected = previous?.humanDetected ?? false;
    if (!next.humanDetected) {
      return;
    }

    _lastThermalHumanAt = DateTime.now();
    _lastThermalHumanFrame = next.frame;

    final pending = _pendingVoiceEvent;
    final pendingStartedAt = _pendingVoiceStartedAt;
    if (pending != null &&
        pending.source != 'manual_button_single' &&
        pendingStartedAt != null &&
        DateTime.now().difference(pendingStartedAt) <=
            _thermalConfirmationWindow) {
      unawaited(_startThermalConfirmedAlert(pending, next.frame));
      return;
    }

    if (!wasDetected &&
        state.keywordNotice == null &&
        state.activeAlert == null &&
        pending == null) {
      _showThermalSoftAlert();
    }
  }

  void _showThermalSoftAlert() {
    state = state.copyWith(thermalSoftAlert: true, error: null);
    _thermalSoftAlertTimer?.cancel();
    _thermalSoftAlertTimer = Timer(_thermalSoftAlertDuration, () {
      if (ref.mounted) {
        state = state.copyWith(thermalSoftAlert: false);
      }
    });

    final now = DateTime.now();
    final lastSoftBeepAt = _lastSoftBeepAt;
    if (lastSoftBeepAt == null ||
        now.difference(lastSoftBeepAt) >= _thermalSoftBeepCooldown) {
      _lastSoftBeepAt = now;
      unawaited(ref.read(alertRuntimeServiceProvider).playSoftThermalBeep());
    }
  }

  Future<void> _startThermalConfirmedAlert(
    AlertEvent event,
    ThermalFrame? thermalFrame,
  ) async {
    if (event.source == 'manual_button_single') {
      _showKeywordNotice(event);
      unawaited(ref.read(alertRuntimeServiceProvider).playSoftThermalBeep());
      return;
    }
    await _startFullEmergencyAlert(
      event,
      thermalFrame,
      humanDetected: true,
      vibrate: true,
    );
  }

  Future<void> _startAuthoritativeEmergencyAlert(AlertEvent event) async {
    final isDoubleTapManual = event.source == 'manual_button';
    final isSingleTapManual = event.source == 'manual_button_single';

    if (isSingleTapManual ||
        event.decisionState == AlertDecisionState.advisory) {
      if (event.isRecognizedConfiguredKeyword) {
        _showKeywordNotice(event);
        unawaited(ref.read(alertRuntimeServiceProvider).playSoftThermalBeep());
      }
      return;
    }

    final hasHuman =
        event.backendThermalState == BackendThermalState.positive ||
        (event.backendThermalState == BackendThermalState.unknown &&
            event.humanDetected);
    if (!hasHuman &&
        !isDoubleTapManual &&
        event.decisionState != AlertDecisionState.critical) {
      traceAlert('provider_disposition', event.eventId, 'thermal_gate_notice', {
        'reason': 'no_recent_thermal_presence',
      });
      // Keyword detected but no thermal human — show status badge + soft beep.
      // No full-screen alert, no alarm, no vibration.
      if (event.isRecognizedConfiguredKeyword) {
        _showKeywordNotice(event);
        unawaited(ref.read(alertRuntimeServiceProvider).playSoftThermalBeep());
      }
      return;
    }
    // Keyword + Human confirmed — trigger full-screen alarm.
    await _startFullEmergencyAlert(
      event,
      null,
      humanDetected: hasHuman,
      vibrate: true,
    );
  }

  Future<void> _startFullEmergencyAlert(
    AlertEvent event,
    ThermalFrame? thermalFrame, {
    required bool humanDetected,
    required bool vibrate,
  }) async {
    _pendingVoiceTimer?.cancel();
    _pendingVoiceTimer = null;
    _pendingVoiceEvent = null;
    _pendingVoiceStartedAt = null;
    _thermalSoftAlertTimer?.cancel();
    _thermalSoftAlertTimer = null;
    final showKeyword = event.isRecognizedConfiguredKeyword;
    if (showKeyword) {
      _keywordNoticeTimer?.cancel();
      _keywordNoticeTimer = Timer(_keywordNoticeDuration, () {
        if (ref.mounted) {
          state = state.copyWith(keywordNotice: null);
        }
      });
    } else {
      _keywordNoticeTimer?.cancel();
      _keywordNoticeTimer = null;
    }
    final replaced = state.activeAlert?.eventId;
    if (replaced != null && replaced != event.eventId) {
      _supersededAlertIds.add(replaced);
    }
    state = state.copyWith(
      keywordNotice: showKeyword ? event : null,
      pendingGuidance: null,
      pendingGuidanceHumanDetected: false,
      thermalSoftAlert: false,
      activeAlert: event,
      activeAlertHumanDetected: humanDetected,
      activeAlertThermalFrame: thermalFrame,
      error: null,
    );
    traceAlert('overlay', event.eventId, 'activated', {
      'human_detected': humanDetected,
    });
    final sound = ref.read(settingsProvider).alertSound;
    await ref
        .read(alertRuntimeServiceProvider)
        .startEmergency(event, sound, vibrate: vibrate);
  }
}

const _unset = Object();
