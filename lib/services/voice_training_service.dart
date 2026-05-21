import 'dart:io';

import 'package:dio/dio.dart';

import '../models/voice_sample.dart';

class VoiceTrainingService {
  VoiceTrainingService({required this.host, required this.port, Dio? dio})
    : _dio =
          dio ??
          Dio(
            BaseOptions(
              baseUrl: 'http://$host:$port',
              connectTimeout: const Duration(seconds: 4),
              sendTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 10),
            ),
          );

  final String host;
  final int port;
  final Dio _dio;

  Future<VoiceSample> uploadSample({
    required File file,
    required String keyword,
    required String speakerName,
  }) async {
    final bytes = await file.readAsBytes();
    final response = await _dio.post<Map<String, dynamic>>(
      '/api/voice/sample',
      queryParameters: {
        'keyword': keyword,
        'speaker_name': speakerName.trim().isEmpty
            ? 'mobile_user'
            : speakerName.trim(),
      },
      data: Stream.fromIterable([bytes]),
      options: Options(
        contentType: 'audio/wav',
        headers: {'Content-Length': bytes.length},
      ),
    );
    return VoiceSample.fromJson(response.data ?? const {});
  }

  Future<List<VoiceSample>> fetchSamples({String? keyword}) async {
    final response = await _dio.get<Map<String, dynamic>>(
      '/api/voice/samples',
      queryParameters: {
        if (keyword != null && keyword.isNotEmpty) 'keyword': keyword,
      },
    );
    final samples = response.data?['samples'];
    if (samples is! List) {
      return const [];
    }
    return samples
        .whereType<Map<String, dynamic>>()
        .map(VoiceSample.fromJson)
        .toList();
  }

  Future<VoiceTrainingStats> fetchStats() async {
    final response = await _dio.get<Map<String, dynamic>>('/api/voice/stats');
    return VoiceTrainingStats.fromJson(response.data ?? const {});
  }

  Future<VoiceCalibrationFromSamples> calibrate() async {
    final response = await _dio.post<Map<String, dynamic>>(
      '/api/voice/calibrate',
    );
    return VoiceCalibrationFromSamples.fromJson(response.data ?? const {});
  }
}
