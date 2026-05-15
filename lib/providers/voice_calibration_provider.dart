import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/audio_frame.dart';
import '../providers/audio_provider.dart';
import '../providers/noise_suppression_provider.dart';
import '../services/voice_calibration_service.dart';

final voiceCalibrationProvider =
    NotifierProvider<VoiceCalibrationController, VoiceCalibrationState>(
      VoiceCalibrationController.new,
    );

class VoiceCalibrationState {
  const VoiceCalibrationState({
    this.running = false,
    this.currentSample = 0,
    this.sampleComplete = const [false, false, false],
    this.recommendation,
    this.error,
  });

  final bool running;
  final int currentSample;
  final List<bool> sampleComplete;
  final VoiceCalibrationRecommendation? recommendation;
  final String? error;

  VoiceCalibrationState copyWith({
    bool? running,
    int? currentSample,
    List<bool>? sampleComplete,
    Object? recommendation = _unset,
    Object? error = _unset,
  }) {
    return VoiceCalibrationState(
      running: running ?? this.running,
      currentSample: currentSample ?? this.currentSample,
      sampleComplete: sampleComplete ?? this.sampleComplete,
      recommendation: recommendation == _unset
          ? this.recommendation
          : recommendation as VoiceCalibrationRecommendation?,
      error: error == _unset ? this.error : error as String?,
    );
  }
}

class VoiceCalibrationController extends Notifier<VoiceCalibrationState> {
  final _service = VoiceCalibrationService();

  @override
  VoiceCalibrationState build() {
    Future.microtask(_loadSavedProfile);
    return const VoiceCalibrationState();
  }

  Future<void> startCalibration() async {
    state = const VoiceCalibrationState(running: true, currentSample: 0);
    final samples = <VoiceCalibrationSample>[];
    final sampleComplete = [false, false, false];

    try {
      for (var index = 0; index < 3; index++) {
        if (!ref.mounted) {
          return;
        }
        state = state.copyWith(currentSample: index + 1, error: null);
        final sample = await _captureSample(const Duration(seconds: 2));
        samples.add(sample);
        sampleComplete[index] = true;
        state = state.copyWith(sampleComplete: [...sampleComplete]);
        await Future<void>.delayed(const Duration(milliseconds: 450));
      }

      final recommendation = _service.analyze(samples);
      state = state.copyWith(
        running: false,
        recommendation: recommendation,
        error: null,
      );
      await _persistRecommendation(recommendation);
    } catch (error) {
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(running: false, error: error.toString());
    }
  }

  Future<void> applyRecommendation() async {
    final recommendation = state.recommendation;
    if (recommendation == null) {
      return;
    }
    await ref
        .read(noiseSuppressionProvider.notifier)
        .update(
          active: true,
          strength: recommendation.strength,
          sensitivity: recommendation.sensitivity,
          snowboySensitivity: recommendation.snowboySensitivity,
        );
  }

  Future<VoiceCalibrationSample> _captureSample(Duration duration) async {
    final collected = <AudioFrame>[];
    final endAt = DateTime.now().add(duration);
    while (DateTime.now().isBefore(endAt)) {
      final latest = ref.read(audioProvider).latest;
      if (latest != null) {
        collected.add(latest);
      }
      await Future<void>.delayed(const Duration(milliseconds: 120));
    }
    if (collected.isEmpty) {
      throw StateError('No Pi audio frames received during calibration.');
    }

    final avgSignal =
        collected
            .map((frame) => (frame.leftRms + frame.rightRms) / 2)
            .reduce((a, b) => a + b) /
        collected.length;
    final avgNoise =
        collected.map((frame) => frame.noiseLevelDb).reduce((a, b) => a + b) /
        collected.length;
    final avgSnr =
        collected.map((frame) => frame.snrDb).reduce((a, b) => a + b) /
        collected.length;
    final pitchSamples = collected
        .map((frame) => frame.estimatedPitchHz)
        .whereType<double>()
        .toList(growable: false);
    final avgPitch = pitchSamples.isEmpty
        ? null
        : pitchSamples.reduce((a, b) => a + b) / pitchSamples.length;

    return VoiceCalibrationSample(
      pitchHz: avgPitch,
      signalLevel: avgSignal,
      noiseFloorDb: avgNoise,
      snrDb: avgSnr,
    );
  }

  Future<void> _persistRecommendation(
    VoiceCalibrationRecommendation recommendation,
  ) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(
        'voiceCalibrationPitchLabel',
        recommendation.pitchLabel,
      );
      await prefs.setString(
        'voiceCalibrationVolumeLabel',
        recommendation.volumeLabel,
      );
      await prefs.setString(
        'voiceCalibrationClarityLabel',
        recommendation.clarityLabel,
      );
      await prefs.setDouble(
        'voiceCalibrationStrength',
        recommendation.strength,
      );
      await prefs.setDouble(
        'voiceCalibrationSensitivity',
        recommendation.sensitivity,
      );
      await prefs.setDouble(
        'voiceCalibrationSnowboySensitivity',
        recommendation.snowboySensitivity,
      );
    } catch (_) {
      // SharedPreferences can be unavailable in tests or partial desktop runs.
    }
  }

  Future<void> _loadSavedProfile() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      if (!ref.mounted) {
        return;
      }
      final strength = prefs.getDouble('voiceCalibrationStrength');
      final sensitivity = prefs.getDouble('voiceCalibrationSensitivity');
      final snowboySensitivity = prefs.getDouble(
        'voiceCalibrationSnowboySensitivity',
      );
      final pitchLabel = prefs.getString('voiceCalibrationPitchLabel');
      final volumeLabel = prefs.getString('voiceCalibrationVolumeLabel');
      final clarityLabel = prefs.getString('voiceCalibrationClarityLabel');
      if (strength == null ||
          sensitivity == null ||
          snowboySensitivity == null ||
          pitchLabel == null ||
          volumeLabel == null ||
          clarityLabel == null) {
        return;
      }
      state = state.copyWith(
        recommendation: VoiceCalibrationRecommendation(
          pitchLabel: pitchLabel,
          volumeLabel: volumeLabel,
          clarityLabel: clarityLabel,
          strength: strength,
          sensitivity: sensitivity,
          snowboySensitivity: snowboySensitivity,
        ),
      );
    } catch (_) {
      // SharedPreferences can be unavailable in tests or partial desktop runs.
    }
  }
}

const _unset = Object();
