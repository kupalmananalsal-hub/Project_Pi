import 'dart:async';

import 'package:web_socket_channel/web_socket_channel.dart';

enum SocketConnectionStatus {
  disconnected,
  connecting,
  connected,
  reconnecting,
}

class ReconnectingWebSocketService<T> {
  ReconnectingWebSocketService({
    required this.uri,
    required this.parser,
    this.reconnectDelay = const Duration(seconds: 2),
    this.maxReconnectDelay = const Duration(seconds: 30),
  });

  final Uri uri;
  final T Function(dynamic message) parser;
  final Duration reconnectDelay;
  final Duration maxReconnectDelay;

  final _messages = StreamController<T>.broadcast();
  final _status = StreamController<SocketConnectionStatus>.broadcast();

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;
  Timer? _reconnectTimer;
  bool _manualClose = false;
  bool _started = false;
  int _reconnectAttempt = 0;

  Stream<T> get messages => _messages.stream;

  Stream<SocketConnectionStatus> get status => _status.stream;

  void connect() {
    if (_started) {
      return;
    }
    _manualClose = false;
    _started = true;
    _open(SocketConnectionStatus.connecting);
  }

  Future<void> disconnect() async {
    _manualClose = true;
    _started = false;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    await _subscription?.cancel();
    _subscription = null;
    await _channel?.sink.close();
    _channel = null;
    if (!_status.isClosed) {
      _status.add(SocketConnectionStatus.disconnected);
    }
  }

  Future<void> dispose() async {
    await disconnect();
    await _messages.close();
    await _status.close();
  }

  void _open(SocketConnectionStatus openingStatus) {
    if (_manualClose) {
      return;
    }
    _status.add(openingStatus);
    try {
      _channel = WebSocketChannel.connect(uri);
      _subscription = _channel!.stream.listen(
        (message) {
          _reconnectAttempt = 0;
          if (!_status.isClosed) {
            _status.add(SocketConnectionStatus.connected);
          }
          try {
            _messages.add(parser(message));
          } catch (error, stackTrace) {
            _messages.addError(error, stackTrace);
          }
        },
        onError: (Object error, StackTrace stackTrace) {
          if (!_messages.isClosed) {
            _messages.addError(error, stackTrace);
          }
          _scheduleReconnect();
        },
        onDone: _scheduleReconnect,
        cancelOnError: false,
      );
    } catch (error, stackTrace) {
      _messages.addError(error, stackTrace);
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    if (_manualClose || !_started || _reconnectTimer != null) {
      return;
    }
    _status.add(SocketConnectionStatus.reconnecting);
    _subscription?.cancel();
    _subscription = null;
    _channel = null;
    final delay = _nextDelay();
    _reconnectTimer = Timer(delay, () {
      _reconnectTimer = null;
      _open(SocketConnectionStatus.reconnecting);
    });
  }

  Duration _nextDelay() {
    final multiplier = 1 << _reconnectAttempt.clamp(0, 6);
    _reconnectAttempt++;
    final milliseconds = reconnectDelay.inMilliseconds * multiplier;
    return Duration(
      milliseconds: milliseconds.clamp(
        reconnectDelay.inMilliseconds,
        maxReconnectDelay.inMilliseconds,
      ),
    );
  }
}
