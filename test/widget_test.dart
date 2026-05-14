import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:thermal_audio_monitor/main.dart';

void main() {
  testWidgets('app shows the connection tab', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(child: ThermalAudioMonitorApp()),
    );
    await tester.pump();

    expect(find.text('Connection'), findsOneWidget);
    expect(find.text('10.156.203.236'), findsOneWidget);
  });
}
