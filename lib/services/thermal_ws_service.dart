import '../models/thermal_frame.dart';
import 'reconnecting_web_socket_service.dart';

class ThermalWsService extends ReconnectingWebSocketService<ThermalFrame> {
  ThermalWsService({required String host, required int port})
    : super(
        uri: Uri(scheme: 'ws', host: host, port: port, path: '/ws/thermal'),
        parser: ThermalFrame.fromMessage,
      );
}
