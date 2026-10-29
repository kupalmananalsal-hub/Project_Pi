import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:thermal_audio_monitor/main.dart';

void main() {
  testWidgets('app shows the monitor tab', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: ThermalAudioMonitorApp()),
    );
    await tester.pump();

    expect(find.text('Monitor'), findsWidgets);
    expect(find.text('DIRECTION'), findsOneWidget);
    expect(find.text('LISTENING'), findsOneWidget);
    expect(find.text('THERMAL'), findsOneWidget);
    expect(find.text('MICROPHONES'), findsOneWidget);
    expect(find.text('Simulate distress call'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 20));
  });
}
