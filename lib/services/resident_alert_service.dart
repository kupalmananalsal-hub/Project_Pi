import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/app_settings.dart';

class ResidentAlertService {
  ResidentAlertService({Dio? dio, String? host, int? port})
    : _dio =
          dio ??
          Dio(
            BaseOptions(
              connectTimeout: const Duration(seconds: 3),
              receiveTimeout: const Duration(seconds: 5),
              sendTimeout: const Duration(seconds: 3),
            ),
          ),
      _host = host,
      _port = port;

  final Dio _dio;
  final String? _host;
  final int? _port;

  Future<bool> sendManualAlert({
    String keyword = 'manual',
    double confidence = 1.0,
    String source = 'manual_button',
    String? hostOverride,
    int? portOverride,
  }) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final host =
          hostOverride ??
          _host ??
          prefs.getString('host') ??
          AppSettings.defaultHost;
      final port =
          portOverride ??
          _port ??
          prefs.getInt('port') ??
          AppSettings.defaultPort;

      final url =
          'http://$host:${AppSettings.normalizeBackendPort(port)}/api/alerts/manual';
      final response = await _dio.post<Map<String, dynamic>>(
        url,
        data: {
          'keyword': keyword,
          'confidence': confidence,
          'source': source,
        },
      );

      final statusCode = response.statusCode ?? 0;
      return statusCode >= 200 && statusCode < 300;
    } catch (e) {
      debugPrint('Error sending manual alert: $e');
      return false;
    }
  }
}
