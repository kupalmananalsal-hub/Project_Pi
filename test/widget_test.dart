import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:thermal_audio_monitor/main.dart';

void main() {
  testWidgets('app shows the monitor tab', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: ThermalAudioMonitorApp()),
    );
    await tester.pump();

    expect(find.text('Monitor'), findsWidgets);
    expect(find.textContaining('10.233.82.236'), findsOneWidget);
  });
}
