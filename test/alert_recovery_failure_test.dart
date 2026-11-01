import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:thermal_audio_monitor/services/alert_delivery_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory directory;
  late AlertInbox inbox;
  late AlertDeliveryService client;
  var outputs = 0;
  var active = false;
  var failWrite = false;
  var crashIntent = false;
  var staleIntent = false;
  final sent = <Map<String, dynamic>>[];
  const hello = {
    'protocol_version': 2,
    'type': 'connected',
    'instance': 'db',
    'high_water': 1,
    'recovery_cursor': 0,
  };
  Map<String, dynamic> alert({bool present = true, String mode = 'replay'}) => {
    'protocol_version': 2,
    'type': 'alert',
    'event_id': 'critical-2m',
    'sequence': 1,
    'present': present,
    'delivery_mode': mode,
    'event': {
      'event_id': 'critical-2m',
      'sequence': 1,
      'keyword': 'help',
      'decision_state': 'critical',
      'thermal_state': 'negative',
    },
  };
  Future<void> start() async {
    inbox = AlertInbox(
      directory,
      writeSnapshot: (file, contents) async {
        if (failWrite) throw const FileSystemException('injected_no_space');
        await file.writeAsString(contents, flush: true);
      },
    );
    await inbox.load();
    client = AlertDeliveryService(
      uri: Uri.parse('ws://localhost/ws/alerts'),
      installation: 'test',
      token: 'test',
      inbox: inbox,
      isActive: (_) => active,
      afterIntent: () async {
        if (staleIntent) client.invalidateSessionForTest();
        if (crashIntent) throw StateError('injected_process_crash');
      },
      onEvent: (event) {
        // The presentation acknowledgement must not exist before this callback.
        if (outputs == 0) {
          expect(
            inbox.outbox.containsKey('ack_presented:critical-2m'),
            isFalse,
          );
        }
        if (event.isHistorical) return false;
        outputs++;
        active = true;
        return true;
      },
      onError: (_) {},
      onStatus: (_) {},
      onSendForTest: sent.add,
    );
    await client.handleMessageForTest(hello);
  }

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('alert-recovery');
    outputs = 0;
    active = false;
    failWrite = false;
    crashIntent = false;
    staleIntent = false;
    sent.clear();
    await start();
  });
  tearDown(() async {
    await client.dispose();
    await directory.delete(recursive: true);
  });

  test(
    'stale session after intent cannot present or acknowledge presentation',
    () async {
      staleIntent = true;
      await client.handleMessageForTest(alert());
      expect(outputs, 0);
      expect(sent.any((m) => m['type'] == 'ack_presented'), isFalse);
      staleIntent = false;
      await client.handleMessageForTest(alert());
      expect(outputs, 1);
    },
  );

  test(
    'crash immediately after durable intent permits restart presentation',
    () async {
      crashIntent = true;
      await expectLater(client.handleMessageForTest(alert()), throwsStateError);
      expect(inbox.events['critical-2m']['disposition'], 'intent_committed');
      expect(inbox.outbox.containsKey('ack_presented:critical-2m'), isFalse);
      expect(outputs, 0);
      await client.dispose();
      crashIntent = false;
      await start();
      await client.handleMessageForTest(alert());
      expect(outputs, 1);
    },
  );

  test(
    'presented unconfirmed restarts, active reconnect and live duplicate do not',
    () async {
      await client.handleMessageForTest(alert());
      await client.handleMessageForTest({
        'protocol_version': 2,
        'type': 'ack_committed',
        'event_id': 'critical-2m',
        'acknowledgement': 'ack_presented',
      });
      await client.handleMessageForTest(hello);
      await client.handleMessageForTest(alert());
      await client.handleMessageForTest(alert(mode: 'live'));
      expect(outputs, 1);
      await client.dispose();
      active = false;
      await start();
      await client.handleMessageForTest(alert());
      expect(outputs, 2);
    },
  );

  test(
    'twenty reconnects preserve active overlay without duplicate output',
    () async {
      await client.handleMessageForTest(alert());
      for (var i = 0; i < 20; i++) {
        await client.handleMessageForTest(hello);
        await client.handleMessageForTest(alert());
      }
      expect(outputs, 1);
    },
  );

  test(
    'inbox stays bounded and storage exhaustion still sounds the alarm once',
    () async {
      for (var i = 0; i < 10000; i++) {
        inbox.events['history-$i'] = {
          'processed': true,
          'event': {
            'event_id': 'history-$i',
            'sequence': i + 2,
            'keyword': 'help',
          },
        };
      }
      await inbox.save();
      final restored = AlertInbox(directory);
      await restored.load();
      expect(restored.events.length, AlertInbox.maxEvents);
      expect(restored.events.containsKey('history-9999'), isTrue);
      expect(restored.events.containsKey('history-0'), isFalse);
      failWrite = true;
      sent.clear();
      await expectLater(
        client.handleMessageForTest(alert()),
        throwsA(isA<FileSystemException>()),
      );
      expect(outputs, 1);
      expect(sent, isEmpty);
      failWrite = false;
      await client.handleMessageForTest(alert());
      expect(outputs, 1);
      expect(sent.any((m) => m['type'] == 'ack_received'), isTrue);
    },
  );

  test(
    'explicit confirmation survives restart even before server commits it',
    () async {
      await client.handleMessageForTest(alert());
      await client.confirm('critical-2m');
      await client.dispose();
      active = false;
      await start();
      await client.handleMessageForTest(alert());
      expect(outputs, 1);
      expect(inbox.events['critical-2m']['user_confirmed'], isTrue);
      expect(sent.any((m) => m['type'] == 'ack_user_confirmed'), isTrue);
    },
  );

  test(
    'server expiry denies restart presentation after five minutes',
    () async {
      await client.handleMessageForTest(alert());
      await client.dispose();
      active = false;
      await start();
      await client.handleMessageForTest(alert(present: false));
      expect(outputs, 1);
    },
  );

  test(
    'full storage still alarms but sends no receipt, then recovers',
    () async {
      failWrite = true;
      sent.clear();
      await expectLater(
        client.handleMessageForTest(alert()),
        throwsA(isA<FileSystemException>()),
      );
      expect(sent, isEmpty);
      expect(outputs, 1);
      expect(inbox.events, isEmpty);
      failWrite = false;
      await client.handleMessageForTest(alert());
      expect(outputs, 1);
      expect(sent.any((m) => m['type'] == 'ack_received'), isTrue);
    },
  );

  test(
    'interrupted ack removal restores outbox and resends on reconnect',
    () async {
      await client.handleMessageForTest(alert());
      failWrite = true;
      await expectLater(
        client.handleMessageForTest({
          'protocol_version': 2,
          'type': 'ack_committed',
          'event_id': 'critical-2m',
          'acknowledgement': 'ack_presented',
        }),
        throwsA(isA<FileSystemException>()),
      );
      expect(inbox.outbox.containsKey('ack_presented:critical-2m'), isTrue);
      failWrite = false;
      sent.clear();
      await client.handleMessageForTest(hello);
      expect(sent.any((m) => m['type'] == 'ack_presented'), isTrue);
    },
  );

  test(
    'partial newest snapshot falls back; both corrupt snapshots fail closed',
    () async {
      await client.handleMessageForTest(alert());
      await client.dispose();
      await File(
        '${directory.path}/inbox.${inbox.revision % 2}.json',
      ).writeAsString('{"partial":');
      final restored = AlertInbox(directory);
      await restored.load();
      expect(restored.events.containsKey('critical-2m'), isTrue);
      await File(
        '${directory.path}/inbox.${(inbox.revision + 1) % 2}.json',
      ).writeAsString('broken');
      await expectLater(AlertInbox(directory).load(), throwsStateError);
    },
  );
}
