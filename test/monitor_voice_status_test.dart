import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:thermal_audio_monitor/main.dart';
import 'package:thermal_audio_monitor/models/alert_event.dart';
import 'package:thermal_audio_monitor/models/app_settings.dart';
import 'package:thermal_audio_monitor/models/voice_direction.dart';
import 'package:thermal_audio_monitor/providers/alerts_provider.dart';
import 'package:thermal_audio_monitor/providers/app_services_provider.dart';
import 'package:thermal_audio_monitor/services/alert_runtime_service.dart';
import 'package:thermal_audio_monitor/widgets/radar_compass.dart';

class FakeAlertRuntimeService extends AlertRuntimeService {
  @override
  Future<void> startEmergency(
    AlertEvent event,
    AlertSound sound, {
    bool vibrate = true,
  }) async {}

  @override
  Future<void> stopEmergency() async {}

  @override
  Future<void> playSoftThermalBeep() async {}

  @override
  Future<void> dispose() async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  AlertEvent voiceEvent({
    String id = 'voice-1',
    String direction = 'left',
    double? angle,
    String modality = 'voice_only',
  }) {
    final payload = <String, Object?>{
      'event_id': id,
      'event': 'keyword_detected',
      'keyword': 'help',
      'confidence': 0.78,
      'final_confidence': 0.78,
      'source': 'openwakeword',
      'direction': direction,
      'alert_level': 'visual_only',
      'decision_state': 'advisory',
      'decision_reason': 'voice_advisory',
      'alert_modality': modality,
      'thermal_state': 'negative',
      'timestamp': '2026-08-20T00:00:00Z',
    };
    if (angle != null) {
      payload['direction_angle'] = angle;
    }
    return AlertEvent.fromMessage(payload);
  }

  AlertEvent thermalOnlyEvent() {
    return AlertEvent.fromMessage({
      'event_id': 'thermal-1',
      'event': 'keyword_detected',
      'keyword': 'thermal',
      'confidence': 0,
      'source': 'thermal',
      'direction': 'front',
      'alert_level': 'visual_only',
      'decision_state': 'advisory',
      'decision_reason': 'thermal_only_sustained',
      'alert_modality': 'thermal_only',
      'thermal_state': 'positive',
      'timestamp': '2026-08-20T00:00:00Z',
    });
  }

  Future<ProviderContainer> pumpMonitor(WidgetTester tester) async {
    final container = ProviderContainer(
      overrides: [
        alertRuntimeServiceProvider.overrideWithValue(
          FakeAlertRuntimeService(),
        ),
      ],
    );
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const ThermalAudioMonitorApp(),
      ),
    );
    await tester.pump();
    return container;
  }

  testWidgets('default Monitor status is Listening', (tester) async {
    final container = await pumpMonitor(tester);

    expect(find.text('Listening'), findsOneWidget);
    expect(find.text('Voice Detected!'), findsNothing);

    container.dispose();
  });

  testWidgets('voice keyword alert shows Voice Detected then times out', (
    tester,
  ) async {
    final container = await pumpMonitor(tester);

    container.read(alertsProvider.notifier).handleAlertForTest(voiceEvent());
    await tester.pump();

    expect(find.text('Voice Detected!'), findsOneWidget);
    expect(find.text('Listening'), findsNothing);

    await tester.pump(const Duration(seconds: 3));
    await tester.pump();

    expect(find.text('Listening'), findsOneWidget);
    expect(find.text('Voice Detected!'), findsNothing);

    container.dispose();
  });

  testWidgets('second voice alert resets the Voice Detected timeout', (
    tester,
  ) async {
    final container = await pumpMonitor(tester);

    container
        .read(alertsProvider.notifier)
        .handleAlertForTest(voiceEvent(id: 'voice-1'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 2));

    container
        .read(alertsProvider.notifier)
        .handleAlertForTest(voiceEvent(id: 'voice-2', direction: 'right'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    expect(find.text('Voice Detected!'), findsOneWidget);
    expect(find.text('Listening'), findsNothing);

    await tester.pump(const Duration(seconds: 2));
    await tester.pump();

    expect(find.text('Listening'), findsOneWidget);

    container.dispose();
  });

  testWidgets('thermal-only event does not show Voice Detected', (
    tester,
  ) async {
    final container = await pumpMonitor(tester);

    container
        .read(alertsProvider.notifier)
        .handleAlertForTest(thermalOnlyEvent());
    await tester.pump();

    expect(find.text('Listening'), findsOneWidget);
    expect(find.text('Voice Detected!'), findsNothing);

    container.dispose();
  });

  testWidgets('direction arrow rotates from numeric direction angle', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: RadarCompass(
            direction: voiceEvent(direction: 'front', angle: 90).voiceDirection,
          ),
        ),
      ),
    );

    final rotation = tester.widget<AnimatedRotation>(
      find.byType(AnimatedRotation),
    );
    expect(rotation.turns, closeTo(0.25, 0.001));
    expect(find.byKey(const ValueKey('voice-direction-arrow')), findsOneWidget);
    expect(find.textContaining('°'), findsNothing);
  });

  testWidgets('missing or invalid direction does not crash', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: RadarCompass(direction: VoiceDirection.unknown())),
      ),
    );

    expect(tester.takeException(), isNull);
    expect(find.byKey(const ValueKey('voice-direction-arrow')), findsOneWidget);
    expect(find.textContaining('°'), findsNothing);
  });
}
