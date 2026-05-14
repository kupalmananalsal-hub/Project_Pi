import '../models/alert_event.dart';
import 'reconnecting_web_socket_service.dart';

class AlertWsService extends ReconnectingWebSocketService<AlertEvent> {
  AlertWsService({required String host, required int port})
    : super(
        uri: Uri(scheme: 'ws', host: host, port: port, path: '/ws/alerts'),
        parser: AlertEvent.fromMessage,
      );
}
