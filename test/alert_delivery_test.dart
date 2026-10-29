import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:thermal_audio_monitor/services/alert_delivery_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory directory;
  setUp(() async {
    directory = await Directory.systemTemp.createTemp('alert-inbox-test');
  });
  tearDown(() async {
    await directory.delete(recursive: true);
  });

  test(
    'durable replay does not repeat outputs after restart; old history stays silent',
    () async {
      var outputs = 0;
      var history = 0;
      AlertDeliveryService service(AlertInbox inbox) => AlertDeliveryService(
        uri: Uri.parse('ws://localhost/ws/alerts'),
        installation: 'phone',
        token: 'test',
        inbox: inbox,
        onEvent: (event) {
          if (event.isHistorical) {
            history++;
            return false;
          }
          outputs++;
          return true;
        },
        onError: (error) => fail('$error'),
        onStatus: (_) {},
      );
      Map<String, dynamic> event(String id, int seq, bool present) => {
        'protocol_version': 2,
        'type': 'alert',
        'event_id': id,
        'sequence': seq,
        'present': present,
        'event': {
          'event_id': id,
          'sequence': seq,
          'keyword': 'help',
          'decision_state': 'critical',
          'thermal_state': 'negative',
        },
      };
      final first = AlertInbox(directory);
      await first.load();
      var client = service(first);
      await client.handleMessageForTest({
        'protocol_version': 2,
        'type': 'connected',
        'instance': 'db1',
      });
      await client.handleMessageForTest(event('recent', 1, true));
      await client.handleMessageForTest(event('recent', 1, true));
      expect(outputs, 1);
      expect(first.outbox.containsKey('ack_presented:recent'), isTrue);
      await client.dispose();
      final restarted = AlertInbox(directory);
      await restarted.load();
      client = service(restarted);
      await client.handleMessageForTest({
        'protocol_version': 2,
        'type': 'connected',
        'instance': 'db1',
      });
      await client.handleMessageForTest(event('recent', 1, true));
      await client.handleMessageForTest(event('old', 2, false));
      expect(outputs, 1);
      expect(history, 1);
      await client.confirm('recent');
      expect(restarted.outbox.containsKey('ack_user_confirmed:recent'), isTrue);
      await client.handleMessageForTest({
        'protocol_version': 2,
        'type': 'ack_committed',
        'event_id': 'recent',
        'acknowledgement': 'ack_user_confirmed',
      });
      expect(
        restarted.outbox.containsKey('ack_user_confirmed:recent'),
        isFalse,
      );
      await client.dispose();
    },
  );

  test(
    'received but unfinished intent recovers and malformed snapshots fail closed',
    () async {
      final inbox = AlertInbox(directory);
      await inbox.load();
      inbox.events['pending'] = {
        'processed': false,
        'event': {'event_id': 'pending', 'sequence': 1},
      };
      await inbox.save();
      final restored = AlertInbox(directory);
      await restored.load();
      expect(restored.events['pending']['processed'], isFalse);
      await File('${directory.path}/inbox.1.json').writeAsString('broken');
      await expectLater(AlertInbox(directory).load(), throwsStateError);
    },
  );
}
