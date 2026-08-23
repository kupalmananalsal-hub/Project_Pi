import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/training_job.dart';
import '../models/training_keyword.dart';
import '../models/training_statistics.dart';
import '../services/pi_api_service.dart';
import 'connection_provider.dart';

/// State for the training tab.
class TrainingState {
  const TrainingState({
    this.keywords = const [],
    this.statistics,
    this.recordings = const [],
    this.activeJob,
    this.isLoading = false,
    this.errorMessage,
  });

  final List<TrainingKeyword> keywords;
  final TrainingStatistics? statistics;
  final List<Map<String, dynamic>> recordings;
  final TrainingJob? activeJob;
  final bool isLoading;
  final String? errorMessage;

  TrainingState copyWith({
    List<TrainingKeyword>? keywords,
    TrainingStatistics? statistics,
    List<Map<String, dynamic>>? recordings,
    TrainingJob? activeJob,
    bool? isLoading,
    String? errorMessage,
  }) {
    return TrainingState(
      keywords: keywords ?? this.keywords,
      statistics: statistics ?? this.statistics,
      recordings: recordings ?? this.recordings,
      activeJob: activeJob ?? this.activeJob,
      isLoading: isLoading ?? this.isLoading,
      errorMessage: errorMessage,
    );
  }
}

/// Notifier for the training workflow.
class TrainingNotifier extends Notifier<TrainingState> {
  PiApiService get _api {
    final conn = ref.read(connectionProvider);
    return PiApiService(host: conn.host, port: conn.port);
  }

  Timer? _pollTimer;

  @override
  TrainingState build() => const TrainingState();

  /// Load keywords and statistics from the Pi.
  Future<void> refresh() async {
    state = state.copyWith(isLoading: true, errorMessage: null);
    try {
      final api = _api;
      final kwResponse = await api.fetchTrainingKeywords();
      final keywords = kwResponse
          .map((json) => TrainingKeyword.fromJson(json))
          .toList(growable: false);
      final statsJson = await api.fetchTrainingStatistics();
      final stats = TrainingStatistics.fromJson(statsJson);
      final recordings = await api.fetchTrainingRecordings();
      state = state.copyWith(
        keywords: keywords,
        statistics: stats,
        recordings: recordings,
        isLoading: false,
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, errorMessage: e.toString());
    }
  }

  /// Upload a recorded WAV file.
  Future<bool> uploadRecording({
    required String filePath,
    required String keyword,
    required String speakerId,
    required String ageGroup,
    required String gender,
    required double distanceM,
    required String noiseCondition,
  }) async {
    state = state.copyWith(isLoading: true, errorMessage: null);
    try {
      await _api.uploadTrainingRecording(
        filePath: filePath,
        keyword: keyword,
        speakerId: speakerId,
        ageGroup: ageGroup,
        gender: gender,
        distanceM: distanceM,
        noiseCondition: noiseCondition,
      );
      await refresh();
      return true;
    } catch (e) {
      state = state.copyWith(isLoading: false, errorMessage: e.toString());
      return false;
    }
  }

  /// Start a pipeline job and begin polling for completion.
  Future<void> startJob(String jobType) async {
    state = state.copyWith(isLoading: true, errorMessage: null);
    try {
      final Map<String, dynamic> result;
      switch (jobType) {
        case 'validation':
          result = await _api.startTrainingValidation();
        case 'augmentation':
          result = await _api.startTrainingAugmentation();
        case 'export':
          result = await _api.startTrainingExport();
        case 'training':
          result = await _api.startTrainingTrain();
        default:
          throw ArgumentError('Unknown job type: $jobType');
      }
      final jobId = result['job_id'] as String?;
      if (jobId != null) {
        final job = TrainingJob.fromJson(result);
        state = state.copyWith(activeJob: job, isLoading: false);
        _startPolling(jobId);
      }
    } catch (e) {
      state = state.copyWith(isLoading: false, errorMessage: e.toString());
    }
  }

  void _startPolling(String jobId) {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(const Duration(seconds: 2), (_) async {
      try {
        final jobJson = await _api.fetchTrainingJob(jobId);
        final job = TrainingJob.fromJson(jobJson);
        state = state.copyWith(activeJob: job);
        if (!job.isRunning) {
          _pollTimer?.cancel();
          _pollTimer = null;
          await refresh();
        }
      } catch (_) {
        _pollTimer?.cancel();
        _pollTimer = null;
      }
    });
  }

  /// Delete a recording by ID.
  Future<void> deleteRecording(String recordingId) async {
    try {
      await _api.deleteTrainingRecording(recordingId);
      await refresh();
    } catch (e) {
      state = state.copyWith(errorMessage: e.toString());
    }
  }

  void clearError() {
    state = state.copyWith(errorMessage: null);
  }
}

final trainingProvider =
    NotifierProvider<TrainingNotifier, TrainingState>(TrainingNotifier.new);
