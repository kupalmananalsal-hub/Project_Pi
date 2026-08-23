import 'package:dio/dio.dart';

import '../models/alert_event.dart';
import '../models/app_settings.dart';
import '../models/button_event.dart';
import '../models/system_status.dart';

class PiApiService {
  PiApiService({required this.host, required int port, Dio? dio})
    : port = AppSettings.normalizeBackendPort(port),
      _dio =
          dio ??
          Dio(
            BaseOptions(
              baseUrl:
                  'http://$host:${AppSettings.normalizeBackendPort(port)}',
              connectTimeout: const Duration(seconds: 3),
              receiveTimeout: const Duration(seconds: 5),
              sendTimeout: const Duration(seconds: 3),
            ),
          );

  final String host;
  final int port;
  final Dio _dio;

  String get _backendBaseUrl =>
      'http://$host:${AppSettings.normalizeBackendPort(port)}';

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
    await _dio.post<void>('$_backendBaseUrl/api/shutdown');
  }

  Future<void> reboot() async {
    await _dio.post<void>('$_backendBaseUrl/api/reboot');
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

  // ── Training API ─────────────────────────────────────────────────────

  Future<List<Map<String, dynamic>>> fetchTrainingKeywords() async {
    final response = await _dio.get<Map<String, dynamic>>('/api/training/keywords');
    final keywords = response.data?['keywords'];
    if (keywords is! List) return const [];
    return keywords.cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> fetchTrainingStatistics() async {
    final response = await _dio.get<Map<String, dynamic>>('/api/training/statistics');
    return Map<String, dynamic>.from(response.data ?? const {});
  }

  Future<List<Map<String, dynamic>>> fetchTrainingRecordings() async {
    final response = await _dio.get<Map<String, dynamic>>('/api/training/recordings');
    final recordings = response.data?['recordings'];
    if (recordings is! List) return const [];
    return recordings.cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> uploadTrainingRecording({
    required String filePath,
    required String keyword,
    required String speakerId,
    required String ageGroup,
    required String gender,
    required double distanceM,
    required String noiseCondition,
  }) async {
    final formData = FormData.fromMap({
      'file': await MultipartFile.fromFile(filePath, filename: 'recording.wav'),
      'keyword': keyword,
      'speaker_id': speakerId,
      'age_group': ageGroup,
      'gender': gender,
      'distance_m': distanceM,
      'noise_condition': noiseCondition,
    });
    final response = await _dio.post<Map<String, dynamic>>(
      '/api/training/record',
      data: formData,
      options: Options(receiveTimeout: const Duration(seconds: 30)),
    );
    return Map<String, dynamic>.from(response.data ?? const {});
  }

  Future<void> deleteTrainingRecording(String recordingId) async {
    await _dio.delete<void>('/api/training/recordings/$recordingId');
  }

  Future<Map<String, dynamic>> startTrainingValidation() async {
    final response = await _dio.post<Map<String, dynamic>>('/api/training/validate');
    return Map<String, dynamic>.from(response.data ?? const {});
  }

  Future<Map<String, dynamic>> startTrainingAugmentation({
    int copiesPerFile = 2,
  }) async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/api/training/augment',
      queryParameters: {'copies_per_file': copiesPerFile},
    );
    return Map<String, dynamic>.from(response.data ?? const {});
  }

  Future<Map<String, dynamic>> startTrainingExport() async {
    final response = await _dio.post<Map<String, dynamic>>('/api/training/export');
    return Map<String, dynamic>.from(response.data ?? const {});
  }

  Future<Map<String, dynamic>> startTrainingTrain({int seed = 1337}) async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/api/training/train',
      queryParameters: {'seed': seed},
    );
    return Map<String, dynamic>.from(response.data ?? const {});
  }

  Future<Map<String, dynamic>> fetchTrainingJob(String jobId) async {
    final response = await _dio.get<Map<String, dynamic>>('/api/training/jobs/$jobId');
    return Map<String, dynamic>.from(response.data ?? const {});
  }

  Future<Map<String, dynamic>> fetchTrainingEvaluation({
    double threshold = 0.5,
  }) async {
    final response = await _dio.get<Map<String, dynamic>>(
      '/api/training/evaluate',
      queryParameters: {'threshold': threshold},
    );
    return Map<String, dynamic>.from(response.data ?? const {});
  }
}
