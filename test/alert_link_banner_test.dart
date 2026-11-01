import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:thermal_audio_monitor/providers/connection_provider.dart';
import 'package:thermal_audio_monitor/widgets/alert_link_banner.dart';

void main() {
  testWidgets(
    'banner appears after 10 s without an alert link, not on a deliberate disconnect',
    (tester) async {
      SharedPreferences.setMockInitialValues({});
      final container = ProviderContainer(
        overrides: [piAutoConnectProvider.overrideWithValue(false)],
      );
      addTearDown(container.dispose);
      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: container,
          child: const MaterialApp(home: Scaffold(body: AlertLinkBanner())),
        ),
      );

      final banner = find.byKey(const ValueKey('alert-link-banner'));
      await tester.pump(const Duration(seconds: 9));
      expect(banner, findsNothing);
      await tester.pump(const Duration(seconds: 2));
      expect(banner, findsOneWidget);
      expect(find.textContaining('NOT being received'), findsOneWidget);

      container.read(connectionProvider.notifier).disconnect();
      await tester.pump();
      expect(banner, findsNothing);
    },
  );
}
