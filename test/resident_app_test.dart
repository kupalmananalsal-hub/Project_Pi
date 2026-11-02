import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:thermal_audio_monitor/main_resident.dart';
import 'package:thermal_audio_monitor/screens/resident_mode_screen.dart';
import 'package:thermal_audio_monitor/screens/resident_settings_screen.dart';
import 'package:thermal_audio_monitor/services/resident_control_client.dart';

class FakeResidentControl extends ResidentControlClient {
  final tests = <bool>[];
  int holds = 0, releases = 0, pauses = 0;
  @override
  Future<void> connectSaved() async {}
  @override
  Future<void> sendTest({required bool full}) async {
    tests.add(full);
  }

  @override
  Future<void> beginHold() async {
    holds++;
  }

  @override
  Future<void> release() async {
    releases++;
  }

  @override
  Future<void> pause() async {
    pauses++;
  }
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({'host': 'pi.test', 'port': 8765});
    FlutterSecureStorage.setMockInitialValues({});
  });
  Future<FakeResidentControl> mount(WidgetTester tester) async {
    final service = FakeResidentControl();
    await tester.pumpWidget(
      MaterialApp(home: ResidentModeScreen(control: service)),
    );
    return service;
  }

  testWidgets(
    'small phone with enlarged text retains the button and readable status',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(320, 568);
      tester.platformDispatcher.textScaleFactorTestValue = 1.6;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
      await mount(tester);
      await tester.pump();
      expect(tester.takeException(), isNull);
      expect(find.text('HELP'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'black screen, one HELP button, explicit TEST contract and settings',
    (tester) async {
      await mount(tester);
      expect(
        tester.widget<Scaffold>(find.byType(Scaffold)).backgroundColor,
        Colors.black,
      );
      expect(find.text('HELP'), findsOneWidget);
      expect(find.textContaining('TEST'), findsWidgets);
      await tester.tap(find.byKey(const ValueKey('resident-settings-button')));
      await tester.pumpAndSettle();
      expect(find.byType(ResidentSettingsScreen), findsOneWidget);
      expect(find.byKey(const ValueKey('pi-ip-field')), findsOneWidget);
    },
  );
  testWidgets('single tap sends exactly one keyword TEST', (tester) async {
    final service = await mount(tester);
    await tester.tap(find.text('HELP'));
    await tester.pump(const Duration(milliseconds: 400));
    expect(service.tests, [false]);
    expect(service.holds, 0);
  });
  testWidgets('double tap sends full TEST without single tap', (tester) async {
    final service = await mount(tester);
    await tester.tap(find.text('HELP'));
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.text('HELP'));
    await tester.pump(const Duration(milliseconds: 700));
    expect(service.tests, [true]);
    expect(service.holds, 0);
  });
  testWidgets('long press and release never fire tap TESTs', (tester) async {
    final service = await mount(tester);
    final gesture = await tester.startGesture(
      tester.getCenter(find.text('HELP')),
    );
    await tester.pump(const Duration(milliseconds: 700));
    expect(service.holds, 1);
    await gesture.up();
    await tester.pump(const Duration(milliseconds: 500));
    expect(service.releases, greaterThanOrEqualTo(1));
    expect(service.tests, isEmpty);
  });
  testWidgets('pointer cancellation releases hold', (tester) async {
    final service = await mount(tester);
    final gesture = await tester.startGesture(
      tester.getCenter(find.text('HELP')),
    );
    await tester.pump(const Duration(milliseconds: 700));
    await gesture.cancel();
    await tester.pump();
    expect(service.releases, greaterThanOrEqualTo(1));
    expect(service.tests, isEmpty);
  });
  testWidgets(
    'backgrounding releases control; resuming reconnects without a hold',
    (tester) async {
      final service = await mount(tester);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      await tester.pump();
      expect(service.pauses, 1);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();
      expect(service.holds, 0);
    },
  );
  testWidgets('ResidentApp opens configured screen', (tester) async {
    await tester.pumpWidget(const ResidentApp());
    await tester.pumpAndSettle();
    expect(find.byType(ResidentModeScreen), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets('ResidentApp asks for settings without a saved host', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(const ResidentApp());
    await tester.pumpAndSettle();
    expect(find.byType(ResidentSettingsScreen), findsOneWidget);
  });
}
