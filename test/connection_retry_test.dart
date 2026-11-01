import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:thermal_audio_monitor/models/system_status.dart';
import 'package:thermal_audio_monitor/providers/connection_provider.dart';

void main() {
  testWidgets('a failed first connect keeps retrying until the Pi is up', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    var piUp = false;
    var fetches = 0;
    final connects = <String>[];
    final container = ProviderContainer(
      overrides: [
        piAutoConnectProvider.overrideWithValue(false),
        piStatusFetcherProvider.overrideWithValue((host, port) async {
          fetches++;
          if (!piUp) throw StateError('pi still booting');
          return SystemStatus.fromJson(const {});
        }),
        piConnectionChannelsProvider.overrideWithValue(
          PiConnectionChannels(
            connect: (host, port) => connects.add(host),
            disconnect: () {},
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    final controller = container.read(connectionProvider.notifier);

    await controller.connect(host: '10.0.0.5', port: 8765);
    expect(
      container.read(connectionProvider).connectionStatus,
      PiConnectionStatus.error,
    );
    expect(container.read(connectionProvider).error, contains('Retrying'));

    await tester.pump(const Duration(seconds: 3));
    expect(fetches, greaterThan(3)); // retried, across fallback hosts
    expect(connects, isEmpty);

    piUp = true;
    await tester.pump(const Duration(seconds: 6));
    expect(container.read(connectionProvider).isConnected, isTrue);
    expect(connects, ['10.0.0.5']);

    controller.disconnect();
    final fetchesAfterDisconnect = fetches;
    await tester.pump(const Duration(seconds: 12));
    expect(fetches, fetchesAfterDisconnect);
  });
}
