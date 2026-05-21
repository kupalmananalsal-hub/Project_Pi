import 'dart:async';
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';

import '../models/voice_sample.dart';
import '../providers/connection_provider.dart';
import '../providers/noise_suppression_provider.dart';
import '../services/voice_training_service.dart';

final voiceTrainingProvider =
    NotifierProvider<VoiceTrainingController, VoiceTrainingState>(
      VoiceTrainingController.new,
    );

class VoiceTrainingState {
  const VoiceTrainingState({
    this.keyword = 'tulong',
    this.speakerName = 'mobile_user',
    this.recording = false,
    this.uploading = false,
    this.loading = false,
    this.calibrating = false,
    this.localRecordingPath,
    this.lastUploadedSample,
    this.samples = const [],
    this.stats = const VoiceTrainingStats.empty(),
    this.calibration,
    this.waveform = const [],
    this.error,
    this.message,
  });

  final String keyword;
  final String speakerName;
  final bool recording;
  final bool uploading;
  final bool loading;
  final bool calibrating;
  final String? localRecordingPath;
  final VoiceSample? lastUploadedSample;
  final List<VoiceSample> samples;
  final VoiceTrainingStats stats;
  final VoiceCalibrationFromSamples? calibration;
  final List<double> waveform;
  final String? error;
  final String? message;

  VoiceTrainingState copyWith({
    String? keyword,
    String? speakerName,
    bool? recording,
    bool? uploading,
    bool? loading,
    bool? calibrating,
    Object? localRecordingPath = _unset,
    Object? lastUploadedSample = _unset,
    List<VoiceSample>? samples,
    VoiceTrainingStats? stats,
    Object? calibration = _unset,
    List<double>? waveform,
    Object? error = _unset,
    Object? message = _unset,
  }) {
    return VoiceTrainingState(
      keyword: keyword ?? this.keyword,
      speakerName: speakerName ?? this.speakerName,
      recording: recording ?? this.recording,
      uploading: uploading ?? this.uploading,
      loading: loading ?? this.loading,
      calibrating: calibrating ?? this.calibrating,
      localRecordingPath: localRecordingPath == _unset
          ? this.localRecordingPath
          : localRecordingPath as String?,
      lastUploadedSample: lastUploadedSample == _unset
          ? this.lastUploadedSample
          : lastUploadedSample as VoiceSample?,
      samples: samples ?? this.samples,
      stats: stats ?? this.stats,
      calibration: calibration == _unset
          ? this.calibration
          : calibration as VoiceCalibrationFromSamples?,
      waveform: waveform ?? this.waveform,
      error: error == _unset ? this.error : error as String?,
      message: message == _unset ? this.message : message as String?,
    );
  }
}

class VoiceTrainingController extends Notifier<VoiceTrainingState> {
  final _recorder = AudioRecorder();
  Timer? _amplitudeTimer;
  Timer? _stopTimer;

  @override
  VoiceTrainingState build() {
    ref.onDispose(() {
      _amplitudeTimer?.cancel();
      _stopTimer?.cancel();
      _recorder.dispose();
    });
    Future.microtask(refresh);
    return const VoiceTrainingState();
  }

  void setKeyword(String keyword) {
    state = state.copyWith(keyword: keyword, error: null, message: null);
  }

  void setSpeakerName(String value) {
    state = state.copyWith(speakerName: value, error: null, message: null);
  }

  Future<void> refresh() async {
    final service = _serviceOrNull();
    if (service == null) {
      return;
    }
    state = state.copyWith(loading: true, error: null);
    try {
      final results = await Future.wait([
        service.fetchStats(),
        service.fetchSamples(),
      ]);
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(
        loading: false,
        stats: results[0] as VoiceTrainingStats,
        samples: results[1] as List<VoiceSample>,
      );
    } catch (error) {
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(loading: false, error: error.toString());
    }
  }

  Future<void> startRecording() async {
    final permission = await Permission.microphone.request();
    if (!permission.isGranted) {
      state = state.copyWith(error: 'Microphone permission is required.');
      return;
    }
    if (!await _recorder.hasPermission()) {
      state = state.copyWith(error: 'Recorder permission was denied.');
      return;
    }

    final directory = await getTemporaryDirectory();
    final path =
        '${directory.path}/project_pi_${state.keyword}_${DateTime.now().millisecondsSinceEpoch}.wav';
    state = state.copyWith(
      recording: true,
      localRecordingPath: path,
      waveform: const [],
      error: null,
      message: 'Recording ${state.keyword.toUpperCase()}...',
    );

    await _recorder.start(
      const RecordConfig(
        encoder: AudioEncoder.wav,
        sampleRate: 16000,
        numChannels: 1,
      ),
      path: path,
    );
    _startAmplitudeCapture();
    _stopTimer?.cancel();
    _stopTimer = Timer(const Duration(seconds: 3), stopRecording);
  }

  Future<void> stopRecording() async {
    _stopTimer?.cancel();
    _amplitudeTimer?.cancel();
    if (await _recorder.isRecording()) {
      await _recorder.stop();
    }
    if (!ref.mounted) {
      return;
    }
    state = state.copyWith(
      recording: false,
      message: 'Recording ready to send',
    );
  }

  Future<void> uploadRecording() async {
    final service = _serviceOrNull();
    final path = state.localRecordingPath;
    if (service == null || path == null) {
      state = state.copyWith(
        error: 'Connect to the Pi and record a sample first.',
      );
      return;
    }
    final file = File(path);
    if (!await file.exists()) {
      state = state.copyWith(error: 'Recorded WAV file is missing.');
      return;
    }

    state = state.copyWith(uploading: true, error: null);
    try {
      final sample = await service.uploadSample(
        file: file,
        keyword: state.keyword,
        speakerName: state.speakerName,
      );
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(
        uploading: false,
        lastUploadedSample: sample,
        message: sample.message,
      );
      await refresh();
    } catch (error) {
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(uploading: false, error: error.toString());
    }
  }

  Future<void> calibrateFromSamples() async {
    final service = _serviceOrNull();
    if (service == null) {
      state = state.copyWith(error: 'Connect to the Pi first.');
      return;
    }
    state = state.copyWith(calibrating: true, error: null);
    try {
      final calibration = await service.calibrate();
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(
        calibrating: false,
        calibration: calibration,
        message: 'Calibration generated from stored samples.',
      );
      await ref
          .read(noiseSuppressionProvider.notifier)
          .update(
            active: true,
            strength: calibration.noiseSuppressionStrength,
            sensitivity: calibration.noiseSuppressionSensitivity,
            snowboySensitivity: calibration.snowboySensitivity,
          );
    } catch (error) {
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(calibrating: false, error: error.toString());
    }
  }

  void _startAmplitudeCapture() {
    _amplitudeTimer?.cancel();
    _amplitudeTimer = Timer.periodic(const Duration(milliseconds: 120), (
      _,
    ) async {
      if (!await _recorder.isRecording()) {
        return;
      }
      final amplitude = await _recorder.getAmplitude();
      if (!ref.mounted) {
        return;
      }
      final level = ((amplitude.current + 60) / 60).clamp(0.0, 1.0).toDouble();
      final waveform = [...state.waveform, level];
      if (waveform.length > 36) {
        waveform.removeRange(0, waveform.length - 36);
      }
      state = state.copyWith(waveform: waveform);
    });
  }

  VoiceTrainingService? _serviceOrNull() {
    final connection = ref.read(connectionProvider);
    if (!connection.isConnected) {
      return null;
    }
    return VoiceTrainingService(host: connection.host, port: connection.port);
  }
}

const _unset = Object();
