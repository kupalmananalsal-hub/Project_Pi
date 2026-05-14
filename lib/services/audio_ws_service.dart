import '../models/audio_frame.dart';
import 'reconnecting_web_socket_service.dart';

class AudioWsService extends ReconnectingWebSocketService<AudioFrame> {
  AudioWsService({required String host, required int port})
    : super(
        uri: Uri(scheme: 'ws', host: host, port: port, path: '/ws/audio'),
        parser: AudioFrame.fromMessage,
      );
}
