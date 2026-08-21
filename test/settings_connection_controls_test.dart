import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:thermal_audio_monitor/main.dart';
import 'package:thermal_audio_monitor/models/alert_event.dart';
import 'package:thermal_audio_monitor/models/app_settings.dart';
import 'package:thermal_audio_monitor/models/system_status.dart';
import 'package:thermal_audio_monitor/providers/alerts_provider.dart';
import 'package:thermal_audio_monitor/providers/app_services_provider.dart';
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

  testWidgets('gear opens settings with Pi host field and Connect button', (
    tester,
  ) async {
    final container = await pumpApp(tester);

    await openSettings(tester);

    expect(find.text('Settings'), findsOneWidget);
    expect(find.text('Raspberry Pi Connection'), findsOneWidget);
    expect(find.byKey(const ValueKey('pi-host-field')), findsOneWidget);
    expect(find.byKey(const ValueKey('pi-port-field')), findsOneWidget);
    expect(find.text('8765'), findsWidgets);
    expect(find.byKey(const ValueKey('pi-connect-button')), findsOneWidget);
    expect(find.byKey(const ValueKey('pi-disconnect-button')), findsNothing);
    expect(find.text('Disconnected'), findsOneWidget);

    final hostY = tester.getCenter(find.byKey(const ValueKey('pi-host-field'))).dy;
    final connectY =
        tester.getCenter(find.byKey(const ValueKey('pi-connect-button'))).dy;
    expect(connectY, greaterThan(hostY));

    container.dispose();
  });

  testWidgets('Connect invokes channels and shows Disconnect while connected', (
    tester,
  ) async {
    final connectCalls = <({String host, int port})>[];
    var disconnectCalls = 0;

    final container = await pumpApp(
      tester,
      overrides: [
        piStatusFetcherProvider.overrideWithValue((host, port) async {
          expect(host, '10.10.10.10');
          expect(port, 8765);
          return fakeStatus();
        }),
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
    await tester.enterText(
      find.byKey(const ValueKey('pi-host-field')),
      '10.10.10.10',
    );
    await tester.tap(find.byKey(const ValueKey('pi-connect-button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(connectCalls, [(host: '10.10.10.10', port: 8765)]);
    expect(find.byKey(const ValueKey('pi-disconnect-button')), findsOneWidget);
    expect(find.byKey(const ValueKey('pi-connect-button')), findsNothing);
    expect(find.text('Connected'), findsOneWidget);
    expect(container.read(connectionProvider).isConnected, isTrue);
    expect(container.read(settingsProvider).host, '10.10.10.10');

    final hostY = tester.getCenter(find.byKey(const ValueKey('pi-host-field'))).dy;
    final disconnectY = tester
        .getCenter(find.byKey(const ValueKey('pi-disconnect-button')))
        .dy;
    expect(disconnectY, greaterThan(hostY));

    await tester.tap(find.byKey(const ValueKey('pi-disconnect-button')));
    await tester.pump();

    expect(disconnectCalls, 1);
    expect(container.read(connectionProvider).isConnected, isFalse);
    expect(container.read(connectionProvider).userRequestedDisconnect, isTrue);
    expect(container.read(settingsProvider).host, '10.10.10.10');
    expect(find.byKey(const ValueKey('pi-connect-button')), findsOneWidget);
    expect(find.byKey(const ValueKey('pi-disconnect-button')), findsNothing);
    expect(find.text('Disconnected'), findsOneWidget);

    container.dispose();
  });

  testWidgets('explicit Disconnect prevents automatic reconnect on host change', (
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

    await container
        .read(connectionProvider.notifier)
        .connect(host: '10.10.10.10', port: 8765);
    await tester.pump();
    expect(connectCalls, [(host: '10.10.10.10', port: 8765)]);
    expect(container.read(connectionProvider).isConnected, isTrue);

    container.read(connectionProvider.notifier).disconnect();
    await tester.pump();
    expect(disconnectCalls, 1);
    expect(container.read(connectionProvider).userRequestedDisconnect, isTrue);

    await container.read(settingsProvider.notifier).updateHost('10.20.30.40');
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(connectCalls, [(host: '10.10.10.10', port: 8765)]);
    expect(container.read(connectionProvider).isConnected, isFalse);
    expect(container.read(settingsProvider).host, '10.20.30.40');

    await container
        .read(connectionProvider.notifier)
        .connect(host: '10.20.30.40', port: 8765);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(connectCalls, [
      (host: '10.10.10.10', port: 8765),
      (host: '10.20.30.40', port: 8765),
    ]);
    expect(container.read(connectionProvider).isConnected, isTrue);
    expect(container.read(connectionProvider).userRequestedDisconnect, isFalse);

    container.dispose();
  });

  testWidgets('Monitor still shows Listening Voice Detected and direction arrow', (
    tester,
  ) async {
    final container = await pumpApp(tester);

    expect(find.text('Listening'), findsOneWidget);
    expect(find.byType(RadarCompass), findsOneWidget);
    expect(find.byKey(const ValueKey('voice-direction-arrow')), findsOneWidget);

    container.read(alertsProvider.notifier).handleAlertForTest(
      AlertEvent.fromMessage({
        'event_id': 'voice-settings-1',
        'event': 'keyword_detected',
        'keyword': 'help',
        'confidence': 0.9,
        'final_confidence': 0.9,
        'source': 'openwakeword',
        'direction': 'left',
        'direction_angle': 270,
        'alert_level': 'visual_only',
        'decision_state': 'advisory',
        'decision_reason': 'voice_advisory',
        'alert_modality': 'voice_only',
        'thermal_state': 'negative',
        'timestamp': '2026-08-21T00:00:00Z',
      }),
    );
    await tester.pump();

    expect(find.text('Voice Detected!'), findsOneWidget);
    expect(find.text('Listening'), findsNothing);

    await tester.pump(const Duration(seconds: 3));
    await tester.pump();

    expect(find.text('Listening'), findsOneWidget);
    expect(find.text('Voice Detected!'), findsNothing);

    container.dispose();
  });
}
