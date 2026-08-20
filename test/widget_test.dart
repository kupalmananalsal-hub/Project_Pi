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
    expect(find.text('DIRECTION'), findsOneWidget);
    expect(find.text('Listening'), findsOneWidget);
    expect(find.text('THERMAL'), findsOneWidget);
    expect(find.text('MICROPHONES'), findsOneWidget);
    expect(find.text('Simulate distress call'), findsOneWidget);
  });
}
