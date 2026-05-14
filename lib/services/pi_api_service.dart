import 'package:dio/dio.dart';

import '../models/button_event.dart';
import '../models/system_status.dart';

class PiApiService {
  PiApiService({required this.host, required this.port, Dio? dio})
    : _dio =
          dio ??
          Dio(
            BaseOptions(
              baseUrl: 'http://$host:$port',
              connectTimeout: const Duration(seconds: 3),
              receiveTimeout: const Duration(seconds: 5),
              sendTimeout: const Duration(seconds: 3),
            ),
          );

  final String host;
  final int port;
  final Dio _dio;

  Future<SystemStatus> fetchStatus() async {
    final response = await _dio.get<Map<String, dynamic>>('/api/status');
    return SystemStatus.fromJson(response.data ?? const {});
  }

  Future<void> setLed({
    required int led,
    required int r,
    required int g,
    required int b,
  }) async {
    await _dio.post<void>(
      '/api/leds',
      data: {
        'led': led,
        'r': r.clamp(0, 255),
        'g': g.clamp(0, 255),
        'b': b.clamp(0, 255),
      },
    );
  }

  Future<ButtonEvent> fetchButton() async {
    final response = await _dio.get<Map<String, dynamic>>('/api/button');
    return ButtonEvent.fromJson(response.data ?? const {});
  }

  Future<void> shutdown() async {
    await _dio.post<void>('/api/shutdown');
  }

  Future<void> reboot() async {
    await _dio.post<void>('/api/reboot');
  }
}
