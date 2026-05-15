import 'package:dio/dio.dart';

import '../models/noise_suppression_settings.dart';

class NoiseSuppressionService {
  NoiseSuppressionService({required this.host, required this.port, Dio? dio})
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

  Future<NoiseSuppressionSettings> fetchSettings() async {
    final response = await _dio.get<Map<String, dynamic>>(
      '/api/audio/noise-suppression',
    );
    return NoiseSuppressionSettings.fromJson(response.data ?? const {});
  }

  Future<NoiseSuppressionSettings> updateSettings(
    NoiseSuppressionSettings settings,
  ) async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/api/audio/noise-suppression',
      data: settings.toRequestJson(),
    );
    final payload = response.data?['settings'];
    if (payload is Map<String, dynamic>) {
      return NoiseSuppressionSettings.fromJson(payload);
    }
    return fetchSettings();
  }
}
