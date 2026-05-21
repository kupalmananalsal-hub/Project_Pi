import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/audio_frame.dart';
import '../models/thermal_frame.dart';
import '../models/voice_direction.dart';
import '../utils/human_detector.dart';
import 'audio_provider.dart';
import 'direction_provider.dart';
import 'thermal_provider.dart';

final monitorProvider = Provider<MonitorState>((ref) {
  final thermal = ref.watch(thermalProvider);
  final audio = ref.watch(audioProvider);
  final direction = ref.watch(directionProvider);

  return MonitorState(
    thermalFrame: thermal.frame,
    humanDetection: thermal.humanDetection,
    audioFrame: audio.latest,
    audioHistory: audio.history,
    direction: direction,
    thermalFps: thermal.fps,
    thermalSocketStatus: thermal.socketStatus.name,
    audioSocketStatus: audio.socketStatus.name,
  );
});

class MonitorState {
  const MonitorState({
    required this.thermalFrame,
    required this.humanDetection,
    required this.audioFrame,
    required this.audioHistory,
    required this.direction,
    required this.thermalFps,
    required this.thermalSocketStatus,
    required this.audioSocketStatus,
  });

  final ThermalFrame? thermalFrame;
  final HumanDetectionResult humanDetection;
  final AudioFrame? audioFrame;
  final List<AudioFrame> audioHistory;
  final VoiceDirection direction;
  final double thermalFps;
  final String thermalSocketStatus;
  final String audioSocketStatus;

  bool get humanDetected => humanDetection.detected;
}
