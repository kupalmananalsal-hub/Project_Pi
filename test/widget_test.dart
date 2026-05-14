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
    expect(find.text('192.168.1.34'), findsOneWidget);
  });
}
