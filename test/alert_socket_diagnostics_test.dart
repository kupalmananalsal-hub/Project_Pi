import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:thermal_audio_monitor/services/reconnecting_web_socket_service.dart';

void main() {
  test(
    'connection failure records target, generation, and reconnect',
    () async {
      const port = 8765;
      final records = <Map<String, dynamic>>[];
      final reconnected = Completer<void>();
      final original = debugPrint;
      debugPrint = (String? message, {int? wrapWidth}) {
        if (message == null || !message.startsWith('{')) return;
        final record = jsonDecode(message) as Map<String, dynamic>;
        records.add(record);
        if (record['stage'] == 'socket_attempt' &&
            (record['generation'] as int) >= 2 &&
            !reconnected.isCompleted) {
          reconnected.complete();
        }
      };
      final socket = ReconnectingWebSocketService<String>(
        uri: Uri(
          scheme: 'ws',
          host: '127.0.0.1',
          port: port,
          path: '/ws/alerts',
        ),
        parser: (message) => message.toString(),
        connector: (_) => throw StateError('simulated connection failure'),
        reconnectDelay: const Duration(milliseconds: 10),
      );
      final subscription = socket.messages.listen(
        (_) {},
        onError: (Object _) {},
      );
      try {
        socket.connect();
        await reconnected.future.timeout(const Duration(seconds: 5));
        expect(records.any((r) => r['stage'] == 'socket_error'), isTrue);
        expect(records.any((r) => r['outcome'] == 'reconnecting'), isTrue);
        expect(records.first['port'], port);
        expect(records.first['host'], '127.0.0.1');
      } finally {
        await socket.dispose();
        await subscription.cancel();
        debugPrint = original;
      }
    },
  );
}
