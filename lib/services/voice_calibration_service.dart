class VoiceCalibrationSample {
  const VoiceCalibrationSample({
    required this.pitchHz,
    required this.signalLevel,
    required this.noiseFloorDb,
    required this.snrDb,
  });

  final double? pitchHz;
  final double signalLevel;
  final double noiseFloorDb;
  final double snrDb;
}

class VoiceCalibrationRecommendation {
  const VoiceCalibrationRecommendation({
    required this.pitchLabel,
    required this.volumeLabel,
    required this.clarityLabel,
    required this.strength,
    required this.sensitivity,
    required this.snowboySensitivity,
  });

  final String pitchLabel;
  final String volumeLabel;
  final String clarityLabel;
  final double strength;
  final double sensitivity;
  final double snowboySensitivity;
}

class VoiceCalibrationService {
  VoiceCalibrationRecommendation analyze(List<VoiceCalibrationSample> samples) {
    if (samples.isEmpty) {
      return const VoiceCalibrationRecommendation(
        pitchLabel: 'Unknown',
        volumeLabel: 'Unknown',
        clarityLabel: 'Unknown',
        strength: 0.5,
        sensitivity: 0.5,
        snowboySensitivity: 0.40,
      );
    }

    final pitches = samples
        .map((sample) => sample.pitchHz)
        .whereType<double>()
        .toList(growable: false);
    final avgPitch = pitches.isEmpty
        ? null
        : pitches.reduce((a, b) => a + b) / pitches.length;
    final avgSignal =
        samples.map((sample) => sample.signalLevel).reduce((a, b) => a + b) /
        samples.length;
    final avgNoiseFloor =
        samples.map((sample) => sample.noiseFloorDb).reduce((a, b) => a + b) /
        samples.length;
    final avgSnr =
        samples.map((sample) => sample.snrDb).reduce((a, b) => a + b) /
        samples.length;

    final pitchLabel = _pitchLabel(avgPitch);
    final volumeLabel = avgSignal > 0.06
        ? 'Strong'
        : avgSignal > 0.03
        ? 'Medium'
        : 'Soft';
    final clarityLabel = avgSnr >= 18
        ? 'Good'
        : avgSnr >= 10
        ? 'Fair'
        : 'Needs cleaner input';

    var strength = avgNoiseFloor > -45
        ? 0.75
        : avgNoiseFloor > -55
        ? 0.5
        : 0.25;
    var sensitivity = avgSignal < 0.03
        ? 0.72
        : avgSignal < 0.05
        ? 0.60
        : 0.48;
    var snowboySensitivity = avgSignal < 0.03 ? 0.44 : 0.40;

    if (avgPitch != null && avgPitch >= 220) {
      strength -= 0.08;
      sensitivity += 0.10;
      snowboySensitivity += 0.03;
    }

    if (avgSnr < 10) {
      strength += 0.10;
      sensitivity -= 0.08;
      snowboySensitivity -= 0.02;
    }

    return VoiceCalibrationRecommendation(
      pitchLabel: pitchLabel,
      volumeLabel: volumeLabel,
      clarityLabel: clarityLabel,
      strength: strength.clamp(0.0, 1.0),
      sensitivity: sensitivity.clamp(0.0, 1.0),
      snowboySensitivity: snowboySensitivity.clamp(0.20, 0.95),
    );
  }

  String _pitchLabel(double? pitchHz) {
    if (pitchHz == null) {
      return 'Unknown';
    }
    if (pitchHz < 165) {
      return '${pitchHz.round()} Hz (Low)';
    }
    if (pitchHz < 255) {
      return '${pitchHz.round()} Hz (Adult)';
    }
    return '${pitchHz.round()} Hz (High)';
  }
}
