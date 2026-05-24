import 'package:dio/dio.dart';

import '../models/alert_event.dart';
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

  Future<void> postAlert({
    required String keyword,
    double confidence = 0.95,
  }) async {
    await _dio.post<void>(
      '/api/alerts',
      data: {
        'event': 'keyword_detected',
        'keyword': keyword,
        'confidence': confidence,
      },
    );
  }

  Future<List<AlertEvent>> fetchAlerts() async {
    final response = await _dio.get<Map<String, dynamic>>('/api/alerts');
    final history = response.data?['history'];
    if (history is! List) {
      return const [];
    }
    return history
        .whereType<Map<String, dynamic>>()
        .map(AlertEvent.fromMessage)
        .toList(growable: false);
  }

  Future<void> clearAlerts() async {
    await _dio.delete<void>('/api/alerts');
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

  Future<Map<String, dynamic>> refreshServices({
    bool gitPull = false,
    bool restartBackend = false,
  }) async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/api/refresh',
      data: {
        'git_pull': gitPull,
        'restart_backend': restartBackend,
      },
      options: Options(receiveTimeout: const Duration(seconds: 130)),
    );
    return Map<String, dynamic>.from(response.data ?? const {});
  }
}
