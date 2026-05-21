class VoiceSample {
  const VoiceSample({
    required this.sampleId,
    required this.filename,
    required this.keyword,
    required this.speakerName,
    required this.durationSeconds,
    required this.sampleRate,
    required this.channels,
    required this.timestamp,
    this.message,
  });

  final String sampleId;
  final String filename;
  final String keyword;
  final String speakerName;
  final double durationSeconds;
  final int sampleRate;
  final int channels;
  final DateTime timestamp;
  final String? message;

  factory VoiceSample.fromJson(Map<String, dynamic> json) {
    return VoiceSample(
      sampleId: json['sample_id']?.toString() ?? '',
      filename: json['filename']?.toString() ?? '',
      keyword: json['keyword']?.toString() ?? 'unknown',
      speakerName: json['speaker_name']?.toString() ?? 'unknown',
      durationSeconds: _asDouble(json['duration_seconds']),
      sampleRate: _asInt(json['sample_rate']),
      channels: _asInt(json['channels']),
      timestamp:
          DateTime.tryParse(json['timestamp']?.toString() ?? '') ??
          DateTime.now(),
      message: json['message']?.toString(),
    );
  }

  static double _asDouble(dynamic value) {
    if (value is num) {
      return value.toDouble();
    }
    if (value is String) {
      return double.tryParse(value) ?? 0;
    }
    return 0;
  }

  static int _asInt(dynamic value) {
    if (value is int) {
      return value;
    }
    if (value is num) {
      return value.round();
    }
    if (value is String) {
      return int.tryParse(value) ?? 0;
    }
    return 0;
  }
}

class VoiceTrainingStats {
  const VoiceTrainingStats({
    required this.tulongSamples,
    required this.helpSamples,
    required this.uniqueSpeakers,
    required this.totalSamples,
    required this.readyForTraining,
    required this.message,
  });

  const VoiceTrainingStats.empty()
    : tulongSamples = 0,
      helpSamples = 0,
      uniqueSpeakers = 0,
      totalSamples = 0,
      readyForTraining = false,
      message = 'No samples loaded';

  final int tulongSamples;
  final int helpSamples;
  final int uniqueSpeakers;
  final int totalSamples;
  final bool readyForTraining;
  final String message;

  factory VoiceTrainingStats.fromJson(Map<String, dynamic> json) {
    return VoiceTrainingStats(
      tulongSamples: VoiceSample._asInt(json['tulong_samples']),
      helpSamples: VoiceSample._asInt(json['help_samples']),
      uniqueSpeakers: VoiceSample._asInt(json['unique_speakers']),
      totalSamples: VoiceSample._asInt(json['total_samples']),
      readyForTraining: json['ready_for_training'] == true,
      message: json['message']?.toString() ?? '',
    );
  }
}

class VoiceCalibrationFromSamples {
  const VoiceCalibrationFromSamples({
    required this.avgVolume,
    required this.pitchRange,
    required this.clarityScore,
    required this.noiseSuppressionStrength,
    required this.noiseSuppressionSensitivity,
    required this.snowboySensitivity,
    required this.gainBoost,
    required this.samplesAnalyzed,
    required this.readyForProduction,
  });

  final double avgVolume;
  final List<double?> pitchRange;
  final double clarityScore;
  final double noiseSuppressionStrength;
  final double noiseSuppressionSensitivity;
  final double snowboySensitivity;
  final double gainBoost;
  final int samplesAnalyzed;
  final bool readyForProduction;

  factory VoiceCalibrationFromSamples.fromJson(Map<String, dynamic> json) {
    final profile = json['voice_profile'] is Map<String, dynamic>
        ? json['voice_profile'] as Map<String, dynamic>
        : const <String, dynamic>{};
    final settings = json['recommended_settings'] is Map<String, dynamic>
        ? json['recommended_settings'] as Map<String, dynamic>
        : const <String, dynamic>{};
    final pitch = profile['pitch_range_hz'];
    return VoiceCalibrationFromSamples(
      avgVolume: VoiceSample._asDouble(profile['avg_volume']),
      pitchRange: pitch is List
          ? pitch
                .map((value) => value is num ? value.toDouble() : null)
                .toList()
          : const [null, null],
      clarityScore: VoiceSample._asDouble(profile['clarity_score']),
      noiseSuppressionStrength: VoiceSample._asDouble(
        settings['noise_suppression_strength'],
      ),
      noiseSuppressionSensitivity: VoiceSample._asDouble(
        settings['noise_suppression_sensitivity'],
      ),
      snowboySensitivity: VoiceSample._asDouble(
        settings['snowboy_sensitivity'],
      ),
      gainBoost: VoiceSample._asDouble(settings['gain_boost']),
      samplesAnalyzed: VoiceSample._asInt(json['samples_analyzed']),
      readyForProduction: json['ready_for_production'] == true,
    );
  }
}
