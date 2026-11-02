import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:thermal_audio_monitor/models/alert_event.dart';
import 'package:thermal_audio_monitor/models/app_settings.dart';
import 'package:thermal_audio_monitor/providers/alerts_provider.dart';
import 'package:thermal_audio_monitor/providers/app_services_provider.dart';
import 'package:thermal_audio_monitor/providers/connection_provider.dart';
import 'package:thermal_audio_monitor/services/resident_monitor_service.dart';
import 'package:thermal_audio_monitor/widgets/alert_overlay.dart';
import 'package:thermal_audio_monitor/widgets/resident_test_layer.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'alert_runtime_execution_test.dart' show TestRuntime;

class FixtureMonitor extends ResidentMonitorService {
  bool acceptAcks = true;
  final acknowledgements = <String>[];
  final claimed = <String>{};
  @override
  Future<void> start(AppSettings settings) async {
    connected = true;
    state = {'remote_mute_available': false, 'resident_connected': true};
    notifyListeners();
  }

  void send(String id, {bool full = false}) {
    connected = true;
    pending.add(ResidentTestEvent(id, full));
    notifyListeners();
  }

  @override
  Future<bool> claim(ResidentTestEvent event) async {
    pending.removeWhere((e) => e.id == event.id);
    return claimed.add(event.id);
  }

  @override
  Future<bool> acknowledge(ResidentTestEvent event, String disposition) async {
    acknowledgements.add('${event.id}:$disposition');
    return acceptAcks;
  }
}

class FixtureAlerts extends AlertsController {
  @override
  AlertsState build() => const AlertsState();
  void realEmergency() => state = AlertsState(
    activeAlert: AlertEvent(
      eventId: 'real-one',
      keyword: 'help',
      confidence: .99,
      timestamp: DateTime.now(),
    ),
  );
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));
  testWidgets(
    'keyword TEST gets presentation and user ACK without entering real history',
    (tester) async {
      final monitor = FixtureMonitor();
      final alerts = FixtureAlerts();
      final runtime = TestRuntime();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            residentMonitorProvider.overrideWithValue(monitor),
            piAutoConnectProvider.overrideWithValue(false),
            alertsProvider.overrideWith(() => alerts),
            alertRuntimeServiceProvider.overrideWithValue(runtime),
          ],
          child: MaterialApp(
            home: ResidentTestLayer(
              builder: (status) => Scaffold(body: status),
            ),
          ),
        ),
      );
      await tester.pump();
      monitor.send('test-one');
      await tester.pump();
      await tester.pump();
      expect(find.text('KEYWORD SPOTTED TEST / SIMULATION'), findsOneWidget);
      expect(monitor.acknowledgements, contains('test-one:presented'));
      expect(alerts.state.history, isEmpty);
      expect(runtime.audioStarts, 0);
      await tester.tap(find.text('Acknowledge TEST'));
      await tester.pump();
      expect(monitor.acknowledgements, contains('test-one:user_acknowledged'));
      monitor.send('test-one');
      await tester.pump();
      expect(find.text('KEYWORD SPOTTED TEST / SIMULATION'), findsNothing);
      await tester.pumpWidget(const SizedBox());
    },
  );
  testWidgets(
    'Full TEST is explicit and silent by default; real emergency preempts it',
    (tester) async {
      final monitor = FixtureMonitor();
      final alerts = FixtureAlerts();
      final runtime = TestRuntime();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            residentMonitorProvider.overrideWithValue(monitor),
            piAutoConnectProvider.overrideWithValue(false),
            alertsProvider.overrideWith(() => alerts),
            alertRuntimeServiceProvider.overrideWithValue(runtime),
          ],
          child: MaterialApp(
            home: ResidentTestLayer(
              builder: (status) => Scaffold(body: status),
            ),
          ),
        ),
      );
      await tester.pump();
      monitor.send('test-full', full: true);
      await tester.pump();
      await tester.pump();
      expect(find.byType(AlertOverlay), findsOneWidget);
      expect(find.text('FULL ALERT TEST / SIMULATION'), findsOneWidget);
      expect(find.text('TEST audio and vibration disabled'), findsOneWidget);
      expect(runtime.audioStarts, 0);
      alerts.realEmergency();
      await tester.pump();
      expect(find.byType(AlertOverlay), findsNothing);
      expect(
        monitor.acknowledgements,
        contains('test-full:deferred_real_emergency'),
      );
      expect(runtime.stops, 0);
      await tester.pumpWidget(const SizedBox());
    },
  );
  testWidgets(
    'locally authorized Full TEST starts outputs once and disconnect stops only TEST',
    (tester) async {
      final monitor = FixtureMonitor();
      final alerts = FixtureAlerts();
      final runtime = TestRuntime();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            residentMonitorProvider.overrideWithValue(monitor),
            piAutoConnectProvider.overrideWithValue(false),
            alertsProvider.overrideWith(() => alerts),
            alertRuntimeServiceProvider.overrideWithValue(runtime),
          ],
          child: MaterialApp(
            home: ResidentTestLayer(
              builder: (status) => Scaffold(body: status),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.tap(find.byTooltip('Resident TEST controls'));
      await tester.pumpAndSettle();
      await tester.tap(
        find.text('Authorize TEST audio / vibration this session'),
      );
      await tester.pumpAndSettle();
      monitor.send('test-authorized', full: true);
      await tester.pump();
      await tester.pump();
      await tester.pump();
      expect(runtime.audioStarts, 1);
      expect(runtime.vibrationStarts, 1);
      monitor.send('test-authorized', full: true);
      await tester.pump();
      expect(runtime.audioStarts, 1);
      monitor.connected = false;
      monitor.notifyListeners();
      await tester.pump();
      expect(runtime.stops, 1);
      expect(find.byType(AlertOverlay), findsNothing);
      monitor.connected = true;
      monitor.acceptAcks = false;
      monitor.notifyListeners();
      await tester.pump();
      await tester.tap(find.byTooltip('Resident TEST controls'));
      await tester.pumpAndSettle();
      await tester.tap(
        find.text('Authorize TEST audio / vibration this session'),
      );
      await tester.pumpAndSettle();
      monitor.send('test-rejected-ack', full: true);
      await tester.pump();
      await tester.pump();
      await tester.pump();
      expect(
        runtime.audioStarts,
        1,
        reason: 'Rejected presentation acknowledgement must block TEST outputs',
      );
      runtime.playback.complete();
      await tester.pumpWidget(const SizedBox());
    },
  );
}
