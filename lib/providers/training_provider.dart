import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';

import '../models/training_job.dart';
import '../models/training_keyword.dart';
import '../models/training_statistics.dart';
import '../services/pi_api_service.dart';
import '../services/wav_converter.dart';
import 'connection_provider.dart';

enum TrainingRecordingStatus {
  idle,
  recording,
  stopping,
  uploading,
  success,
  error,
}

class TrainingRecordingUpload {
  const TrainingRecordingUpload({
    required this.filePath,
    required this.keyword,
    required this.speakerId,
    required this.ageGroup,
    required this.gender,
    required this.distanceM,
    required this.noiseCondition,
  });

  final String filePath;
  final String keyword;
  final String speakerId;
  final String ageGroup;
  final String gender;
  final double distanceM;
  final String noiseCondition;
}

class TrainingWavInfo {
  const TrainingWavInfo({
    required this.sampleRate,
    required this.channels,
    required this.bitsPerSample,
    required this.audioFormat,
    required this.duration,
    required this.fileSizeBytes,
  });

  final int sampleRate;
  final int channels;
  final int bitsPerSample;
  final int audioFormat;
  final Duration duration;
  final int fileSizeBytes;

  bool get matchesBackendFormat =>
      sampleRate == 16000 &&
      channels == 1 &&
      bitsPerSample == 16 &&
      audioFormat == 1 &&
      duration >= const Duration(seconds: 1) &&
      duration <= const Duration(seconds: 5);

  String get summary {
    final seconds = (duration.inMilliseconds / 1000).toStringAsFixed(2);
    final format = audioFormat == 1 ? 'PCM' : 'format $audioFormat';
    return '$sampleRate Hz, $channels channel(s), $bitsPerSample-bit $format, ${seconds}s, $fileSizeBytes bytes';
  }
}

/// State for the training tab.
class TrainingState {
  const TrainingState({
    this.keywords = const [],
    this.statistics,
    this.recordings = const [],
    this.activeJob,
    this.isLoading = false,
    this.errorMessage,
    this.recordingStatus = TrainingRecordingStatus.idle,
    this.recordingPath,
    this.lastUploadPath,
    this.recordingStartedAt,
    this.recordingElapsed = Duration.zero,
    this.microphonePermissionDenied = false,
    this.lastWavInfo,
  });

  final List<TrainingKeyword> keywords;
  final TrainingStatistics? statistics;
  final List<Map<String, dynamic>> recordings;
  final TrainingJob? activeJob;
  final bool isLoading;
  final String? errorMessage;
  final TrainingRecordingStatus recordingStatus;
  final String? recordingPath;
  final String? lastUploadPath;
  final DateTime? recordingStartedAt;
  final Duration recordingElapsed;
  final bool microphonePermissionDenied;
  final TrainingWavInfo? lastWavInfo;

  bool get isRecording => recordingStatus == TrainingRecordingStatus.recording;
  bool get isRecordingBusy =>
      recordingStatus == TrainingRecordingStatus.stopping ||
      recordingStatus == TrainingRecordingStatus.uploading;

  TrainingState copyWith({
    List<TrainingKeyword>? keywords,
    TrainingStatistics? statistics,
    List<Map<String, dynamic>>? recordings,
    TrainingJob? activeJob,
    bool? isLoading,
    String? errorMessage,
    TrainingRecordingStatus? recordingStatus,
    String? recordingPath,
    String? lastUploadPath,
    Object? recordingStartedAt = _unset,
    Duration? recordingElapsed,
    bool? microphonePermissionDenied,
    Object? lastWavInfo = _unset,
  }) {
    return TrainingState(
      keywords: keywords ?? this.keywords,
      statistics: statistics ?? this.statistics,
      recordings: recordings ?? this.recordings,
      activeJob: activeJob ?? this.activeJob,
      isLoading: isLoading ?? this.isLoading,
      errorMessage: errorMessage,
      recordingStatus: recordingStatus ?? this.recordingStatus,
      recordingPath: recordingPath ?? this.recordingPath,
      lastUploadPath: lastUploadPath ?? this.lastUploadPath,
      recordingStartedAt: recordingStartedAt == _unset
          ? this.recordingStartedAt
          : recordingStartedAt as DateTime?,
      recordingElapsed: recordingElapsed ?? this.recordingElapsed,
      microphonePermissionDenied:
          microphonePermissionDenied ?? this.microphonePermissionDenied,
      lastWavInfo: lastWavInfo == _unset
          ? this.lastWavInfo
          : lastWavInfo as TrainingWavInfo?,
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
  Timer? _recordingTimer;
  final AudioRecorder _recorder = AudioRecorder();
  TrainingRecordingUpload? _pendingUpload;

  @override
  TrainingState build() {
    ref.onDispose(() {
      _pollTimer?.cancel();
      _recordingTimer?.cancel();
      _recorder.dispose();
    });
    return const TrainingState();
  }

  Future<bool> startRecording() async {
    if (state.isRecording || state.isRecordingBusy || state.isLoading) {
      return false;
    }

    try {
      if (!await _requestMicrophonePermission()) {
        return false;
      }

      final directory = await getTemporaryDirectory();
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final path = '${directory.path}/project_pi_keyword_$timestamp.wav';
      await _recorder.start(
        const RecordConfig(
          encoder: AudioEncoder.wav,
          sampleRate: 16000,
          numChannels: 1,
        ),
        path: path,
      );
      final startedAt = DateTime.now();
      _startRecordingTimer(startedAt);
      state = state.copyWith(
        recordingStatus: TrainingRecordingStatus.recording,
        recordingPath: path,
        lastUploadPath: path,
        recordingStartedAt: startedAt,
        recordingElapsed: Duration.zero,
        microphonePermissionDenied: false,
        errorMessage: null,
      );
      return true;
    } catch (e) {
      state = state.copyWith(
        recordingStatus: TrainingRecordingStatus.error,
        errorMessage: e.toString(),
      );
      return false;
    }
  }

  Future<bool> stopRecordingAndUpload({
    required String keyword,
    required String speakerId,
    required String ageGroup,
    required String gender,
    required double distanceM,
    required String noiseCondition,
  }) async {
    if (!state.isRecording) {
      return false;
    }

    state = state.copyWith(
      recordingStatus: TrainingRecordingStatus.stopping,
      errorMessage: null,
      microphonePermissionDenied: false,
    );
    try {
      _recordingTimer?.cancel();
      _recordingTimer = null;
      final path = await _recorder.stop();
      if (path == null || path.isEmpty) {
        state = state.copyWith(
          recordingStatus: TrainingRecordingStatus.error,
          errorMessage: 'Recording failed: no WAV file was produced.',
        );
        return false;
      }

      final wavInfo = await _inspectRecordedWav(path);
      if (wavInfo == null) {
        state = state.copyWith(
          recordingStatus: TrainingRecordingStatus.error,
          errorMessage:
              'Recording failed: saved file is not a readable WAV. Path: $path',
          recordingPath: path,
          lastUploadPath: path,
          lastWavInfo: null,
        );
        return false;
      }
      state = state.copyWith(lastWavInfo: wavInfo);

      // ── Auto-convert if the recorded WAV doesn't match backend format ──
      String uploadPath = path;
      if (!wavInfo.matchesBackendFormat) {
        debugPrint(
          'Training recording WAV format mismatch – converting: '
          '${wavInfo.summary}',
        );
        try {
          final result = await WavConverter.convert(path);
          uploadPath = result.outputPath;
          if (result.converted) {
            debugPrint('WAV conversion complete: ${result.summary}');
            // Re-inspect after conversion to update the displayed info.
            final convertedInfo = await _inspectRecordedWav(uploadPath);
            if (convertedInfo != null) {
              state = state.copyWith(lastWavInfo: convertedInfo);
            }
          }
        } catch (e) {
          debugPrint('WAV conversion failed: $e');
          state = state.copyWith(
            recordingStatus: TrainingRecordingStatus.error,
            errorMessage:
                'Audio format conversion failed: $e. '
                'Original WAV: ${wavInfo.summary}',
          );
          return false;
        }
      }

      _pendingUpload = TrainingRecordingUpload(
        filePath: uploadPath,
        keyword: keyword,
        speakerId: speakerId,
        ageGroup: ageGroup,
        gender: gender,
        distanceM: distanceM,
        noiseCondition: noiseCondition,
      );
      return _uploadPendingRecording();
    } catch (e) {
      state = state.copyWith(
        recordingStatus: TrainingRecordingStatus.error,
        errorMessage: _uploadErrorWithWavInfo(e.toString()),
      );
      return false;
    }
  }

  Future<bool> retryUpload() async {
    if (_pendingUpload == null) {
      state = state.copyWith(
        recordingStatus: TrainingRecordingStatus.error,
        errorMessage: 'No recorded sample is available to retry.',
      );
      return false;
    }
    return _uploadPendingRecording();
  }

  Future<bool> _uploadPendingRecording() async {
    final upload = _pendingUpload;
    if (upload == null) return false;

    state = state.copyWith(
      recordingStatus: TrainingRecordingStatus.uploading,
      isLoading: true,
      errorMessage: null,
      recordingPath: upload.filePath,
      lastUploadPath: upload.filePath,
      microphonePermissionDenied: false,
    );
    final ok = await uploadRecording(
      filePath: upload.filePath,
      keyword: upload.keyword,
      speakerId: upload.speakerId,
      ageGroup: upload.ageGroup,
      gender: upload.gender,
      distanceM: upload.distanceM,
      noiseCondition: upload.noiseCondition,
    );
    if (ok) {
      _pendingUpload = null;
      state = state.copyWith(
        recordingStatus: TrainingRecordingStatus.success,
        isLoading: false,
        errorMessage: null,
        recordingPath: upload.filePath,
        lastUploadPath: upload.filePath,
        recordingStartedAt: null,
        recordingElapsed: Duration.zero,
        microphonePermissionDenied: false,
        lastWavInfo: state.lastWavInfo,
      );
    } else {
      state = state.copyWith(
        recordingStatus: TrainingRecordingStatus.error,
        isLoading: false,
        errorMessage: _uploadErrorWithWavInfo(state.errorMessage ?? ''),
      );
    }
    return ok;
  }

  Future<bool> _requestMicrophonePermission() async {
    final current = await Permission.microphone.status;
    final requested = current.isGranted
        ? current
        : await Permission.microphone.request();
    if (!requested.isGranted) {
      state = state.copyWith(
        recordingStatus: TrainingRecordingStatus.error,
        errorMessage: requested.isPermanentlyDenied
            ? 'Microphone permission is disabled. Enable microphone access in phone Settings to record keyword samples.'
            : 'Microphone permission is required to record keyword samples.',
        microphonePermissionDenied: true,
      );
      return false;
    }

    final recorderReady = await _recorder.hasPermission();
    if (!recorderReady) {
      state = state.copyWith(
        recordingStatus: TrainingRecordingStatus.error,
        errorMessage:
            'Microphone permission is required. Enable microphone access in phone Settings and try again.',
        microphonePermissionDenied: true,
      );
      return false;
    }
    return true;
  }

  Future<void> openMicrophoneSettings() async {
    await openAppSettings();
  }

  void _startRecordingTimer(DateTime startedAt) {
    _recordingTimer?.cancel();
    _recordingTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!state.isRecording) return;
      state = state.copyWith(
        recordingElapsed: DateTime.now().difference(startedAt),
      );
    });
  }

  Future<TrainingWavInfo?> _inspectRecordedWav(String path) async {
    final file = File(path);
    if (!await file.exists()) return null;
    final bytes = await file.readAsBytes();
    if (bytes.length < 44) return null;
    final data = ByteData.sublistView(bytes);
    if (_fourCc(bytes, 0) != 'RIFF' || _fourCc(bytes, 8) != 'WAVE') {
      return null;
    }

    int offset = 12;
    int? audioFormat;
    int? channels;
    int? sampleRate;
    int? bitsPerSample;
    int? dataSize;
    while (offset + 8 <= bytes.length) {
      final chunkId = _fourCc(bytes, offset);
      final chunkSize = data.getUint32(offset + 4, Endian.little);
      final chunkDataOffset = offset + 8;
      if (chunkDataOffset + chunkSize > bytes.length) break;
      if (chunkId == 'fmt ' && chunkSize >= 16) {
        audioFormat = data.getUint16(chunkDataOffset, Endian.little);
        channels = data.getUint16(chunkDataOffset + 2, Endian.little);
        sampleRate = data.getUint32(chunkDataOffset + 4, Endian.little);
        bitsPerSample = data.getUint16(chunkDataOffset + 14, Endian.little);
      } else if (chunkId == 'data') {
        dataSize = chunkSize;
      }
      offset = chunkDataOffset + chunkSize + (chunkSize.isOdd ? 1 : 0);
    }

    if (audioFormat == null ||
        channels == null ||
        sampleRate == null ||
        bitsPerSample == null ||
        dataSize == null ||
        channels == 0 ||
        sampleRate == 0 ||
        bitsPerSample == 0) {
      return null;
    }

    final bytesPerFrame = channels * (bitsPerSample / 8);
    final durationSeconds = dataSize / bytesPerFrame / sampleRate;
    return TrainingWavInfo(
      sampleRate: sampleRate,
      channels: channels,
      bitsPerSample: bitsPerSample,
      audioFormat: audioFormat,
      duration: Duration(milliseconds: (durationSeconds * 1000).round()),
      fileSizeBytes: bytes.length,
    );
  }

  String _fourCc(Uint8List bytes, int offset) {
    if (offset + 4 > bytes.length) return '';
    return String.fromCharCodes(bytes.sublist(offset, offset + 4));
  }

  String _uploadErrorWithWavInfo(String error) {
    final wavInfo = state.lastWavInfo;
    if (wavInfo == null) return error;
    final prefix = error.isEmpty ? 'Upload failed.' : error;
    return '$prefix Recorded WAV: ${wavInfo.summary}.';
  }

  /// Load keywords and statistics from the Pi.
  Future<void> refresh() async {
    state = state.copyWith(isLoading: true, errorMessage: null);
    try {
      final api = _api;
      final keywords = await _loadKeywords(api);
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
      state = state.copyWith(
        keywords: state.keywords.isEmpty ? fallbackTrainingKeywords : null,
        isLoading: false,
        errorMessage:
            'Could not load training data from the Pi. Using local keyword list. $e',
      );
    }
  }

  Future<List<TrainingKeyword>> _loadKeywords(PiApiService api) async {
    try {
      final kwResponse = await api.fetchTrainingKeywords();
      final keywords = kwResponse
          .map((json) => TrainingKeyword.fromJson(json))
          .where((kw) => kw.keyword.isNotEmpty)
          .toList(growable: false);
      return keywords.isEmpty ? fallbackTrainingKeywords : keywords;
    } catch (_) {
      return fallbackTrainingKeywords;
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

final trainingProvider = NotifierProvider<TrainingNotifier, TrainingState>(
  TrainingNotifier.new,
);

const _unset = Object();
