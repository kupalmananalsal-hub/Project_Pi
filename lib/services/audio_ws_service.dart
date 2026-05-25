import '../models/audio_frame.dart';
import '../models/app_settings.dart';
import 'reconnecting_web_socket_service.dart';

class AudioWsService extends ReconnectingWebSocketService<AudioFrame> {
  AudioWsService({required String host, required int port})
    : super(
        uri: Uri(
          scheme: 'ws',
          host: host,
          port: AppSettings.normalizeBackendPort(port),
          path: '/ws/audio',
        ),
        parser: AudioFrame.fromMessage,
      );
}
