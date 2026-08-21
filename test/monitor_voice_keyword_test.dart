import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:thermal_audio_monitor/main.dart';
import 'package:thermal_audio_monitor/models/alert_event.dart';
import 'package:thermal_audio_monitor/models/app_settings.dart';
import 'package:thermal_audio_monitor/models/audio_frame.dart';
import 'package:thermal_audio_monitor/models/system_status.dart';
import 'package:thermal_audio_monitor/models/voice_direction.dart';
import 'package:thermal_audio_monitor/providers/alerts_provider.dart';
import 'package:thermal_audio_monitor/providers/app_services_provider.dart';
import 'package:thermal_audio_monitor/providers/audio_provider.dart';
import 'package:thermal_audio_monitor/providers/connection_provider.dart';
import 'package:thermal_audio_monitor/providers/settings_provider.dart';
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

class _FakeAudioController extends AudioController {
  void publish(AudioFrame frame) {
    state = state.copyWith(latest: frame, error: null);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({
      'host': '10.159.83.236',
      'port': 8765,
    });
  });

  Future<ProviderContainer> pumpApp(
    WidgetTester tester, {
    bool autoConnect = false,
    List overrides = const [],
  }) async {
    final container = ProviderContainer(
      overrides: [
        alertRuntimeServiceProvider.overrideWithValue(
          FakeAlertRuntimeService(),
        ),
        piAutoConnectProvider.overrideWithValue(autoConnect),
        ...overrides,
      ],
    );
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const ThermalAudioMonitorApp(),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    return container;
  }

  Future<void> openSettings(WidgetTester tester) async {
    await tester.tap(find.byTooltip('Settings'));
    await tester.pumpAndSettle();
  }

  SystemStatus fakeStatus() {
    return SystemStatus(receivedAt: DateTime.utc(2026, 8, 21));
  }

  AlertEvent keywordEvent({
    String id = 'kw-1',
    String keyword = 'help',
    String modality = 'voice_only',
  }) {
    return AlertEvent.fromMessage({
      'event_id': id,
      'event': 'keyword_detected',
      'keyword': keyword,
      'confidence': 0.9,
      'final_confidence': 0.9,
      'source': 'openwakeword',
      'direction': 'left',
      'alert_level': 'visual_only',
      'decision_state': 'advisory',
      'decision_reason': 'voice_advisory',
      'alert_modality': modality,
      'thermal_state': 'negative',
      'timestamp': '2026-08-21T00:00:00Z',
    });
  }

  testWidgets('default Monitor status is LISTENING with direction arrow', (
    tester,
  ) async {
    final container = await pumpApp(tester);

    expect(find.text('LISTENING'), findsOneWidget);
    expect(find.text('KEYWORD SPOTTED!'), findsNothing);
    expect(find.byKey(const ValueKey('voice-direction-arrow')), findsOneWidget);
    expect(find.byType(RadarCompass), findsOneWidget);

    container.dispose();
  });

  testWidgets('audio frame moves compass without triggering keyword status', (
    tester,
  ) async {
    final container = await pumpApp(
      tester,
      overrides: [audioProvider.overrideWith(_FakeAudioController.new)],
    );

    expect(find.text('LISTENING'), findsOneWidget);

    (container.read(audioProvider.notifier) as _FakeAudioController).publish(
      AudioFrame(
        leftRms: 0.1,
        rightRms: 0.8,
        direction: 'right',
        directionAngleDegrees: 90,
        timestamp: DateTime.utc(2026, 8, 21),
      ),
    );
    await tester.pump();

    expect(find.text('LISTENING'), findsOneWidget);
    expect(find.text('KEYWORD SPOTTED!'), findsNothing);
    final rotation = tester.widget<AnimatedRotation>(
      find.byType(AnimatedRotation),
    );
    expect(rotation.turns, closeTo(0.25, 0.001));

    container.dispose();
  });

  testWidgets('recognized keyword shows KEYWORD SPOTTED then returns', (
    tester,
  ) async {
    final container = await pumpApp(tester);

    container.read(alertsProvider.notifier).handleAlertForTest(keywordEvent());
    await tester.pump();

    expect(find.text('KEYWORD SPOTTED!'), findsOneWidget);
    expect(find.text('LISTENING'), findsNothing);

    await tester.pump(const Duration(seconds: 3));
    await tester.pump();

    expect(find.text('LISTENING'), findsOneWidget);
    expect(find.text('KEYWORD SPOTTED!'), findsNothing);

    container.dispose();
  });

  testWidgets('thermal-only alert does not show KEYWORD SPOTTED', (
    tester,
  ) async {
    final container = await pumpApp(tester);

    container.read(alertsProvider.notifier).handleAlertForTest(
      keywordEvent(id: 'thermal-1', keyword: 'thermal', modality: 'thermal_only'),
    );
    await tester.pump();

    expect(find.text('LISTENING'), findsOneWidget);
    expect(find.text('KEYWORD SPOTTED!'), findsNothing);

    container.dispose();
  });

  testWidgets('second keyword resets the KEYWORD SPOTTED timeout', (
    tester,
  ) async {
    final container = await pumpApp(tester);

    container
        .read(alertsProvider.notifier)
        .handleAlertForTest(keywordEvent(id: 'kw-1'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 2));

    container
        .read(alertsProvider.notifier)
        .handleAlertForTest(keywordEvent(id: 'kw-2', keyword: 'tulong'));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    expect(find.text('KEYWORD SPOTTED!'), findsOneWidget);

    await tester.pump(const Duration(seconds: 2));
    await tester.pump();

    expect(find.text('LISTENING'), findsOneWidget);

    container.dispose();
  });

  testWidgets('settings shows Connect Disconnect and thermal controls', (
    tester,
  ) async {
    final connectCalls = <({String host, int port})>[];
    var disconnectCalls = 0;

    final container = await pumpApp(
      tester,
      overrides: [
        piStatusFetcherProvider.overrideWithValue(
          (host, port) async => fakeStatus(),
        ),
        piConnectionChannelsProvider.overrideWithValue(
          PiConnectionChannels(
            connect: (host, port) {
              connectCalls.add((host: host, port: port));
            },
            disconnect: () {
              disconnectCalls += 1;
            },
          ),
        ),
      ],
    );

    await openSettings(tester);

    expect(find.text('Raspberry Pi Connection'), findsOneWidget);
    expect(find.byKey(const ValueKey('pi-host-field')), findsOneWidget);
    expect(find.byKey(const ValueKey('pi-connect-button')), findsOneWidget);

    final hostY = tester.getCenter(find.byKey(const ValueKey('pi-host-field'))).dy;
    final connectY =
        tester.getCenter(find.byKey(const ValueKey('pi-connect-button'))).dy;
    expect(connectY, greaterThan(hostY));

    await tester.enterText(
      find.byKey(const ValueKey('pi-host-field')),
      '10.10.10.10',
    );
    await tester.tap(find.byKey(const ValueKey('pi-connect-button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(connectCalls, [(host: '10.10.10.10', port: 8765)]);
    expect(find.byKey(const ValueKey('pi-disconnect-button')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('pi-disconnect-button')));
    await tester.pump();
    expect(disconnectCalls, 1);
    expect(container.read(connectionProvider).userRequestedDisconnect, isTrue);
    container.dispose();
  });

  testWidgets('explicit Disconnect prevents auto reconnect on host change', (
    tester,
  ) async {
    final connectCalls = <({String host, int port})>[];

    final container = await pumpApp(
      tester,
      overrides: [
        piStatusFetcherProvider.overrideWithValue(
          (host, port) async => fakeStatus(),
        ),
        piConnectionChannelsProvider.overrideWithValue(
          PiConnectionChannels(
            connect: (host, port) {
              connectCalls.add((host: host, port: port));
            },
            disconnect: () {},
          ),
        ),
      ],
    );

    await container
        .read(connectionProvider.notifier)
        .connect(host: '10.10.10.10', port: 8765);
    await tester.pump();
    container.read(connectionProvider.notifier).disconnect();
    await tester.pump();

    await container.read(settingsProvider.notifier).updateHost('10.20.30.40');
    await tester.pump(const Duration(milliseconds: 50));

    expect(connectCalls, [(host: '10.10.10.10', port: 8765)]);
    expect(container.read(settingsProvider).host, '10.20.30.40');

    await container
        .read(connectionProvider.notifier)
        .connect(host: '10.20.30.40', port: 8765);
    await tester.pump();

    expect(connectCalls.length, 2);
    expect(container.read(connectionProvider).userRequestedDisconnect, isFalse);

    container.dispose();
  });

  testWidgets('RadarCompass has no degree readout', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: RadarCompass(
            direction: const VoiceDirection(
              sector: VoiceDirectionSector.right,
              angleDegrees: 90,
              confidence: 0.8,
            ),
          ),
        ),
      ),
    );

    expect(find.byKey(const ValueKey('voice-direction-arrow')), findsOneWidget);
    expect(find.textContaining('°'), findsNothing);
  });
}
