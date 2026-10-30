import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:thermal_audio_monitor/services/reconnecting_web_socket_service.dart';

class FakeSink implements WebSocketSink {
  int closes = 0;
  @override
  Future<void> close([int? closeCode, String? closeReason]) async {
    closes++;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class FakeChannel implements WebSocketChannel {
  final incoming = StreamController<dynamic>();
  final handshake = Completer<void>();
  @override
  final FakeSink sink = FakeSink();
  @override
  Stream<dynamic> get stream => incoming.stream;
  @override
  Future<void> get ready => handshake.future;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  test(
    'stalled readiness closes old sink and stale completion cannot reconnect',
    () async {
      final channels = <FakeChannel>[];
      final second = Completer<void>();
      final socket = ReconnectingWebSocketService<String>(
        uri: Uri.parse('ws://localhost/ws/alerts'),
        parser: (v) => '$v',
        readyTimeout: const Duration(milliseconds: 20),
        reconnectDelay: const Duration(milliseconds: 10),
        connector: (_) {
          final channel = FakeChannel();
          channels.add(channel);
          if (channels.length == 2) {
            channel.handshake.complete();
            second.complete();
          }
          return channel;
        },
      );
      final subscription = socket.messages.listen((_) {}, onError: (_) {});
      socket.connect();
      await second.future.timeout(const Duration(seconds: 1));
      expect(channels.first.sink.closes, 1);
      channels.first.handshake.complete();
      await Future<void>.delayed(const Duration(milliseconds: 40));
      expect(channels.length, 2);
      await socket.dispose();
      expect(channels.last.sink.closes, 1);
      await subscription.cancel();
      for (final channel in channels) {
        await channel.incoming.close();
      }
    },
  );
}
