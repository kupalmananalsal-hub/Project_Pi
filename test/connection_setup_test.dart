import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:thermal_audio_monitor/screens/settings_screen.dart';
import 'package:thermal_audio_monitor/screens/connection_status_screen.dart';
import 'package:thermal_audio_monitor/screens/resident_settings_screen.dart';
import 'package:thermal_audio_monitor/providers/connection_provider.dart';
import 'package:thermal_audio_monitor/providers/alerts_provider.dart';

class SetupAlerts extends AlertsController {
  @override
  AlertsState build() => const AlertsState();
}

class OfflineConnection extends ConnectionController {
  @override
  PiConnectionState build() => PiConnectionState(host: 'pi.test', port: 8765);
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({'host': 'pi.test', 'port': 8765});
    FlutterSecureStorage.setMockInitialValues({});
  });
  testWidgets(
    'Main setup exposes only editable host and port; no manual credentials',
    (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            connectionProvider.overrideWith(OfflineConnection.new),
            alertsProvider.overrideWith(SetupAlerts.new),
          ],
          child: const MaterialApp(home: SettingsScreen()),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(TextField), findsNWidgets(2));
      expect(find.byKey(const ValueKey('pi-api-token-field')), findsNothing);
      expect(
        tester
            .widget<TextField>(find.byKey(const ValueKey('pi-port-field')))
            .readOnly,
        false,
      );
      await tester.enterText(
        find.byKey(const ValueKey('pi-host-field')),
        '192.0.2.42',
      );
      await tester.enterText(
        find.byKey(const ValueKey('pi-port-field')),
        '9876',
      );
      await tester.pump();
      expect(
        tester
            .widget<TextField>(find.byKey(const ValueKey('pi-host-field')))
            .controller!
            .text,
        '192.0.2.42',
      );
      expect(
        tester
            .widget<TextField>(find.byKey(const ValueKey('pi-port-field')))
            .controller!
            .text,
        '9876',
      );
      await tester.pumpWidget(const SizedBox());
    },
  );
  testWidgets('Resident setup contains only address and port plus Connect', (
    tester,
  ) async {
    await tester.pumpWidget(const MaterialApp(home: ResidentSettingsScreen()));
    await tester.pumpAndSettle();
    expect(find.byType(TextFormField), findsNWidgets(2));
    expect(find.text('Connect'), findsOneWidget);
    expect(find.byKey(const ValueKey('resident-id-field')), findsNothing);
    expect(find.byKey(const ValueKey('pi-api-token-field')), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });
  testWidgets(
    'alternate connection screen does not offer manual secrets or downgrade',
    (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            connectionProvider.overrideWith(OfflineConnection.new),
            alertsProvider.overrideWith(SetupAlerts.new),
          ],
          child: const MaterialApp(
            home: Scaffold(body: ConnectionStatusScreen()),
          ),
        ),
      );
      await tester.pump();
      expect(find.byType(TextField), findsNWidgets(2));
      expect(find.text('Pair reliable alert delivery'), findsNothing);
      expect(
        find.text('Administrator: unpair reliable delivery'),
        findsNothing,
      );
      await tester.pumpWidget(const SizedBox());
    },
  );
}
