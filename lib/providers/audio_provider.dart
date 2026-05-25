import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/app_settings.dart';
import '../models/audio_frame.dart';
import '../services/reconnecting_web_socket_service.dart';

final audioProvider = NotifierProvider<AudioController, AudioState>(
  AudioController.new,
);

class AudioState {
  const AudioState({
    this.latest,
    this.history = const [],
    this.socketStatus = SocketConnectionStatus.disconnected,
    this.error,
  });

  final AudioFrame? latest;
  final List<AudioFrame> history;
  final SocketConnectionStatus socketStatus;
  final String? error;

  AudioState copyWith({
    Object? latest = _unset,
    List<AudioFrame>? history,
    SocketConnectionStatus? socketStatus,
    Object? error = _unset,
  }) {
    return AudioState(
      latest: latest == _unset ? this.latest : latest as AudioFrame?,
      history: history ?? this.history,
      socketStatus: socketStatus ?? this.socketStatus,
      error: error == _unset ? this.error : error as String?,
    );
  }
}

class AudioController extends Notifier<AudioState> {
  ReconnectingWebSocketService<AudioFrame>? _socket;
  StreamSubscription<AudioFrame>? _audioSubscription;
  StreamSubscription<SocketConnectionStatus>? _statusSubscription;

  @override
  AudioState build() {
    ref.onDispose(disconnect);
    return const AudioState();
  }

  void connect(String host, int port) {
    disconnect();
    _socket = ReconnectingWebSocketService<AudioFrame>(
      uri: Uri(
        scheme: 'ws',
        host: host,
        port: AppSettings.normalizeBackendPort(port),
        path: '/ws/audio',
      ),
      parser: AudioFrame.fromMessage,
    );
    _audioSubscription = _socket!.messages.listen(
      (frame) {
        final nextHistory = [...state.history, frame];
        if (nextHistory.length > 120) {
          nextHistory.removeRange(0, nextHistory.length - 120);
        }
        state = state.copyWith(
          latest: frame,
          history: nextHistory,
          error: null,
        );
      },
      onError: (Object error) {
        state = state.copyWith(error: error.toString());
      },
    );
    _statusSubscription = _socket!.status.listen((status) {
      state = state.copyWith(socketStatus: status);
    });
    _socket!.connect();
  }

  void disconnect() {
    _audioSubscription?.cancel();
    _audioSubscription = null;
    _statusSubscription?.cancel();
    _statusSubscription = null;
    _socket?.disconnect();
    _socket = null;
    if (ref.mounted) {
      state = state.copyWith(socketStatus: SocketConnectionStatus.disconnected);
    }
  }
}

const _unset = Object();
