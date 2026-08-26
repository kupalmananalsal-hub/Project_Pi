import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:thermal_audio_monitor/models/alert_event.dart';
import 'package:thermal_audio_monitor/models/app_settings.dart';
import 'package:thermal_audio_monitor/providers/alerts_provider.dart';
import 'package:thermal_audio_monitor/providers/app_services_provider.dart';
import 'package:thermal_audio_monitor/providers/thermal_provider.dart'
    as thermal;
import 'package:thermal_audio_monitor/services/alert_runtime_service.dart';
import 'package:thermal_audio_monitor/utils/human_detector.dart';

class FakeAlertRuntimeService extends AlertRuntimeService {
  int emergencyStarts = 0;
  int softBeeps = 0;
  AlertEvent? lastEmergencyEvent;
  bool? lastVibrate;

  @override
  Future<void> startEmergency(
    AlertEvent event,
    AlertSound sound, {
    bool vibrate = true,
  }) async {
    emergencyStarts++;
    lastEmergencyEvent = event;
    lastVibrate = vibrate;
  }

  @override
  Future<void> stopEmergency() async {}

  @override
  Future<void> playSoftThermalBeep() async {
    softBeeps++;
  }

  @override
  Future<void> dispose() async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  ProviderContainer makeContainer(FakeAlertRuntimeService runtime) {
    final container = ProviderContainer(
      overrides: [alertRuntimeServiceProvider.overrideWithValue(runtime)],
    );
    addTearDown(container.dispose);
    container.read(alertsProvider);
    return container;
  }

  Future<void> drainAsync() => Future<void>.delayed(Duration.zero);

  AlertEvent eventFrom({
    required String decisionState,
    String source = 'openwakeword',
    String alertLevel = 'visual_only',
    String alertModality = 'voice_only',
    String thermalState = 'negative',
    bool humanDetected = false,
    bool duplicateEvent = false,
    double confidence = 0.75,
  }) {
    return AlertEvent.fromMessage({
      'event_id': 'event-$decisionState-$duplicateEvent',
      'event': 'keyword_detected',
      'keyword': 'help',
      'confidence': confidence,
      'final_confidence': confidence,
      'source': source,
      'direction': 'left',
      'alert_level': alertLevel,
      'human_detected': humanDetected,
      'decision_state': decisionState,
      'decision_reason': 'test_reason',
      'alert_modality': alertModality,
      'thermal_state': thermalState,
      'policy_version': 'test-policy',
      'duplicate_event': duplicateEvent,
      'timestamp': '2026-08-20T00:00:00Z',
    });
  }

  thermal.ThermalState thermalHumanState() {
    return const thermal.ThermalState(
      humanDetection: HumanDetectionResult(detected: true),
    );
  }

  test(
    'suppressed authoritative payload parses and produces no live alert',
    () async {
      final runtime = FakeAlertRuntimeService();
      final container = makeContainer(runtime);
      final controller = container.read(alertsProvider.notifier);
      final event = eventFrom(
        decisionState: 'suppressed',
        alertLevel: 'none',
        thermalState: 'unavailable',
        confidence: 0.2,
      );

      expect(event.decisionState, AlertDecisionState.suppressed);
      expect(event.hasAuthoritativeDecision, isTrue);
      expect(event.shouldShowDirectionGuidance, isFalse);

      controller.handleAlertForTest(event);
      await drainAsync();

      final state = container.read(alertsProvider);
      expect(state.history, hasLength(1));
      expect(state.keywordNotice, isNull);
      expect(state.activeAlert, isNull);
      expect(runtime.emergencyStarts, 0);
      expect(runtime.softBeeps, 0);
    },
  );

  test('advisory authoritative payload shows only the voice banner', () async {
    final runtime = FakeAlertRuntimeService();
    final container = makeContainer(runtime);
    final controller = container.read(alertsProvider.notifier);
    final event = eventFrom(decisionState: 'advisory');

    controller.handleAlertForTest(event);
    await drainAsync();

    final state = container.read(alertsProvider);
    expect(state.keywordNotice, event);
    expect(state.activeAlert, isNull);
    expect(runtime.emergencyStarts, 0);
    expect(runtime.softBeeps, 1);
  });

  test(
    'confirmed authoritative payload starts full emergency immediately',
    () async {
      final runtime = FakeAlertRuntimeService();
      final container = makeContainer(runtime);
      final controller = container.read(alertsProvider.notifier);
      final event = eventFrom(
        decisionState: 'confirmed',
        alertLevel: 'full_alert',
        alertModality: 'voice_thermal',
        thermalState: 'positive',
        humanDetected: true,
      );

      controller.handleAlertForTest(event);
      await drainAsync();

      final state = container.read(alertsProvider);
      expect(state.activeAlert, event);
      expect(state.activeAlertHumanDetected, isTrue);
      expect(runtime.emergencyStarts, 1);
      expect(runtime.lastVibrate, isTrue);
    },
  );

  test(
    'critical voice-only (no human) shows keyword notice only — no full-screen',
    () async {
      final runtime = FakeAlertRuntimeService();
      final container = makeContainer(runtime);
      final controller = container.read(alertsProvider.notifier);
      final event = eventFrom(
        decisionState: 'critical',
        alertLevel: 'full_alert',
        alertModality: 'voice_only',
        thermalState: 'unavailable',
        confidence: 0.95,
        // humanDetected defaults to false
      );

      controller.handleAlertForTest(event);
      await drainAsync();

      // Per alert table Option B: Keyword Only (no human) → status badge +
      // soft notification beep. NO full-screen, no alarm, no vibration.
      final state = container.read(alertsProvider);
      expect(state.keywordNotice, event);
      expect(state.activeAlert, isNull);
      expect(runtime.emergencyStarts, 0);
      expect(runtime.softBeeps, 1);
    },
  );

  test(
    'critical manual button bypasses thermal gate and starts full emergency',
    () async {
      final runtime = FakeAlertRuntimeService();
      final container = makeContainer(runtime);
      final controller = container.read(alertsProvider.notifier);
      final event = eventFrom(
        decisionState: 'critical',
        alertLevel: 'full_alert',
        alertModality: 'voice_only',
        thermalState: 'negative',
        confidence: 1.0,
        source: 'manual_button',
      );

      controller.handleAlertForTest(event);
      await drainAsync();

      final state = container.read(alertsProvider);
      expect(state.activeAlert, event);
      expect(state.activeAlertHumanDetected, isTrue);
      expect(runtime.emergencyStarts, 1);
      expect(runtime.softBeeps, 0);
    },
  );

  test(
    'authoritative advisory is not upgraded by later local thermal state',
    () async {
      final runtime = FakeAlertRuntimeService();
      final container = makeContainer(runtime);
      final controller = container.read(alertsProvider.notifier);
      final event = eventFrom(decisionState: 'advisory');

      controller.handleAlertForTest(event);
      controller.handleThermalStateForTest(null, thermalHumanState());
      await drainAsync();

      final state = container.read(alertsProvider);
      expect(state.keywordNotice, event);
      expect(state.activeAlert, isNull);
      expect(runtime.emergencyStarts, 0);
    },
  );

  test(
    'authoritative suppressed is not upgraded by later local thermal state',
    () async {
      final runtime = FakeAlertRuntimeService();
      final container = makeContainer(runtime);
      final controller = container.read(alertsProvider.notifier);
      final event = eventFrom(
        decisionState: 'suppressed',
        alertLevel: 'none',
        thermalState: 'unavailable',
        confidence: 0.2,
      );

      controller.handleAlertForTest(event);
      controller.handleThermalStateForTest(null, thermalHumanState());
      await drainAsync();

      final state = container.read(alertsProvider);
      expect(state.activeAlert, isNull);
      expect(state.thermalSoftAlert, isTrue);
      expect(runtime.emergencyStarts, 0);
      expect(runtime.softBeeps, 1);
    },
  );

  test('legacy payload keeps compatibility thermal escalation path', () async {
    final runtime = FakeAlertRuntimeService();
    final container = makeContainer(runtime);
    final controller = container.read(alertsProvider.notifier);
    final event = AlertEvent.fromMessage({
      'event': 'keyword_detected',
      'keyword': 'help',
      'confidence': 0.75,
      'alert_level': 'visual_only',
      'human_detected': false,
      'direction': 'front',
      'timestamp': '2026-08-20T00:00:00Z',
    });

    controller.handleAlertForTest(event);
    controller.handleThermalStateForTest(null, thermalHumanState());
    await drainAsync();

    expect(event.hasAuthoritativeDecision, isFalse);
    expect(container.read(alertsProvider).activeAlert, event);
    expect(runtime.emergencyStarts, 1);
  });

  test(
    'unknown authoritative state does not crash or start alerting',
    () async {
      final runtime = FakeAlertRuntimeService();
      final container = makeContainer(runtime);
      final controller = container.read(alertsProvider.notifier);
      final event = eventFrom(decisionState: 'future_state');

      controller.handleAlertForTest(event);
      await drainAsync();

      final state = container.read(alertsProvider);
      expect(event.decisionState, AlertDecisionState.unknown);
      expect(state.activeAlert, isNull);
      expect(state.error, contains('Unknown backend alert decision'));
      expect(runtime.emergencyStarts, 0);
    },
  );

  test(
    'duplicate event response does not create a second live alert',
    () async {
      final runtime = FakeAlertRuntimeService();
      final container = makeContainer(runtime);
      final controller = container.read(alertsProvider.notifier);
      // humanDetected:true so the first event triggers a full emergency
      // (per new alert table: Keyword + Human → full-screen alarm).
      final first = eventFrom(
        decisionState: 'critical',
        alertLevel: 'full_alert',
        humanDetected: true,
        confidence: 0.95,
      );
      final duplicate = eventFrom(
        decisionState: 'critical',
        alertLevel: 'full_alert',
        duplicateEvent: true,
        confidence: 0.95,
      );

      controller.handleAlertForTest(first);
      await drainAsync();
      controller.handleAlertForTest(duplicate);
      await drainAsync();

      expect(container.read(alertsProvider).history, hasLength(2));
      expect(runtime.emergencyStarts, 1);
    },
  );

  test('thermal-only soft alert behavior remains functional', () async {
    final runtime = FakeAlertRuntimeService();
    final container = makeContainer(runtime);
    final controller = container.read(alertsProvider.notifier);

    controller.handleThermalStateForTest(null, thermalHumanState());
    await drainAsync();

    final state = container.read(alertsProvider);
    expect(state.thermalSoftAlert, isTrue);
    expect(state.activeAlert, isNull);
    expect(runtime.softBeeps, 1);
  });
}
