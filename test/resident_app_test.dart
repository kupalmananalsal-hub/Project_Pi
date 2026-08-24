import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:thermal_audio_monitor/main_resident.dart';
import 'package:thermal_audio_monitor/screens/resident_mode_screen.dart';
import 'package:thermal_audio_monitor/services/resident_alert_service.dart';

class FakeResidentAlertService extends ResidentAlertService {
  int manualAlertCalls = 0;
  String? lastKeyword;
  double? lastConfidence;
  String? lastSource;
  bool shouldSucceed = true;

  @override
  Future<bool> sendManualAlert({
    String keyword = 'manual',
    double confidence = 1.0,
    String source = 'manual_button',
    String? hostOverride,
    int? portOverride,
  }) async {
    manualAlertCalls++;
    lastKeyword = keyword;
    lastConfidence = confidence;
    lastSource = source;
    return shouldSucceed;
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

  testWidgets('ResidentModeScreen renders pure black screen with large HELP button', (
    tester,
  ) async {
    final fakeService = FakeResidentAlertService();

    await tester.pumpWidget(
      MaterialApp(
        home: ResidentModeScreen(alertService: fakeService),
      ),
    );
    await tester.pump();

    // Verify pure black background
    final scaffold = tester.widget<Scaffold>(find.byType(Scaffold));
    expect(scaffold.backgroundColor, Colors.black);

    // Verify HELP button text
    expect(find.text('HELP'), findsOneWidget);

    // Verify no app bar or bottom navigation
    expect(find.byType(AppBar), findsNothing);
    expect(find.byType(NavigationBar), findsNothing);
    expect(find.byType(BottomNavigationBar), findsNothing);
  });

  testWidgets('Tapping HELP button triggers alert and shows Alert sent toast', (
    tester,
  ) async {
    final fakeService = FakeResidentAlertService()..shouldSucceed = true;

    await tester.pumpWidget(
      MaterialApp(
        home: ResidentModeScreen(alertService: fakeService),
      ),
    );
    await tester.pump();

    await tester.tap(find.text('HELP'));
    await tester.pump(); // Start press animation
    await tester.pump(const Duration(milliseconds: 300)); // Complete animation & send
    await tester.pumpAndSettle();

    expect(fakeService.manualAlertCalls, 1);
    expect(fakeService.lastKeyword, 'manual');
    expect(fakeService.lastConfidence, 1.0);
    expect(fakeService.lastSource, 'manual_button');

    expect(find.text('Alert sent'), findsOneWidget);
  });

  testWidgets('Failed alert shows Failed to send toast', (tester) async {
    final fakeService = FakeResidentAlertService()..shouldSucceed = false;

    await tester.pumpWidget(
      MaterialApp(
        home: ResidentModeScreen(alertService: fakeService),
      ),
    );
    await tester.pump();

    await tester.tap(find.text('HELP'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pumpAndSettle();

    expect(fakeService.manualAlertCalls, 1);
    expect(find.text('Failed to send'), findsOneWidget);
  });

  testWidgets('ResidentApp builds successfully with black theme', (
    tester,
  ) async {
    await tester.pumpWidget(const ResidentApp());
    await tester.pump();

    expect(find.byType(ResidentModeScreen), findsOneWidget);
    expect(find.text('HELP'), findsOneWidget);
  });
}
