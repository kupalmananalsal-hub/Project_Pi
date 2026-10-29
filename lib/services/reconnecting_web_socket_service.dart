import 'dart:async';
import 'alert_trace.dart';

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
    this.connector,
    this.reconnectDelay = const Duration(seconds: 2),
    this.maxReconnectDelay = const Duration(seconds: 30),
  });

  final Uri uri;
  final WebSocketChannel Function(Uri)? connector;
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
  int _generation = 0;

  void _trace(String stage, String outcome, [String? reason]) {
    traceAlert(stage, null, outcome, {
      'host': uri.host,
      'port': uri.port,
      'generation': _generation,
      'attempt': _reconnectAttempt,
      'reason': reason,
    });
  }

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
    _trace('socket_status', 'disconnected', 'manual_close');
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
    _generation++;
    final generation = _generation;
    _trace('socket_attempt', openingStatus.name);
    try {
      _channel = connector != null
          ? connector!(uri)
          : WebSocketChannel.connect(uri);
      unawaited(
        _channel!.ready
            .then((_) {
              if (generation == _generation && !_manualClose) {
                _trace('socket_attempt', 'ready');
              }
            })
            .catchError((Object error) {
              if (generation == _generation && !_manualClose) {
                _trace(
                  'socket_attempt',
                  'failed',
                  error.runtimeType.toString(),
                );
              }
            }),
      );
      _subscription = _channel!.stream.listen(
        (message) {
          if (generation != _generation || _manualClose) return;
          _reconnectAttempt = 0;
          if (!_status.isClosed) {
            _trace('socket_status', 'connected');
            _status.add(SocketConnectionStatus.connected);
          }
          try {
            _messages.add(parser(message));
          } catch (error, stackTrace) {
            _trace('socket_parse', 'failed', error.runtimeType.toString());
            _messages.addError(error, stackTrace);
          }
        },
        onError: (Object error, StackTrace stackTrace) {
          _trace('socket_error', 'failed', error.runtimeType.toString());
          if (!_messages.isClosed) {
            _messages.addError(error, stackTrace);
          }
          _scheduleReconnect();
        },
        onDone: _scheduleReconnect,
        cancelOnError: false,
      );
    } catch (error, stackTrace) {
      _trace('socket_error', 'connection_failed', error.runtimeType.toString());
      _messages.addError(error, stackTrace);
      _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    if (_manualClose || !_started || _reconnectTimer != null) {
      return;
    }
    _status.add(SocketConnectionStatus.reconnecting);
    _trace('socket_status', 'reconnecting', 'stream_closed_or_failed');
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
