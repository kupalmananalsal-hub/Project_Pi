import 'dart:convert';

class AudioFrame {
  const AudioFrame({
    required this.leftRms,
    required this.rightRms,
    required this.timestamp,
    this.direction = 'center',
    this.noiseLevelDb = -90,
    this.signalLevelDb = -90,
    this.snrDb = 0,
    this.noiseReductionDb = 0,
    this.noiseSuppressionActive = false,
    this.estimatedPitchHz,
  });

  final double leftRms;
  final double rightRms;
  final String direction;
  final DateTime timestamp;
  final double noiseLevelDb;
  final double signalLevelDb;
  final double snrDb;
  final double noiseReductionDb;
  final bool noiseSuppressionActive;
  final double? estimatedPitchHz;

  factory AudioFrame.fromMessage(dynamic message) {
    final decoded = message is String ? jsonDecode(message) : message;
    if (decoded is Map<String, dynamic>) {
      final rms = decoded['rms'] ?? decoded['channels'] ?? decoded['levels'];
      final timestamp =
          DateTime.tryParse(decoded['timestamp']?.toString() ?? '') ??
          DateTime.now();
      if (rms is List && rms.length >= 2) {
        return AudioFrame(
          leftRms: _asDouble(rms[0]),
          rightRms: _asDouble(rms[1]),
          direction: _normalizeDirection(decoded['direction']),
          noiseLevelDb: _asDouble(decoded['noise_level_db'], fallback: -90),
          signalLevelDb: _asDouble(decoded['signal_level_db'], fallback: -90),
          snrDb: _asDouble(decoded['snr_db']),
          noiseReductionDb: _asDouble(decoded['noise_reduction_db']),
          noiseSuppressionActive: _asBool(decoded['noise_suppression_active']),
          estimatedPitchHz: _asNullableDouble(decoded['estimated_pitch_hz']),
          timestamp: timestamp,
        );
      }
      return AudioFrame(
        leftRms: _asDouble(
          decoded['left'] ?? decoded['mic1'] ?? decoded['ch0'] ?? decoded['l'],
        ),
        rightRms: _asDouble(
          decoded['right'] ?? decoded['mic2'] ?? decoded['ch1'] ?? decoded['r'],
        ),
        direction: _normalizeDirection(decoded['direction']),
        noiseLevelDb: _asDouble(decoded['noise_level_db'], fallback: -90),
        signalLevelDb: _asDouble(decoded['signal_level_db'], fallback: -90),
        snrDb: _asDouble(decoded['snr_db']),
        noiseReductionDb: _asDouble(decoded['noise_reduction_db']),
        noiseSuppressionActive: _asBool(decoded['noise_suppression_active']),
        estimatedPitchHz: _asNullableDouble(decoded['estimated_pitch_hz']),
        timestamp: timestamp,
      );
    }
    throw FormatException('Unsupported audio payload: $message');
  }

  double get normalizedLeft => _normalize(leftRms);

  double get normalizedRight => _normalize(rightRms);

  static double _asDouble(dynamic value, {double fallback = 0}) {
    if (value is num) {
      return value.toDouble();
    }
    if (value is String) {
      return double.tryParse(value) ?? fallback;
    }
    return fallback;
  }

  static double _normalize(double value) {
    if (value <= 1) {
      return value.clamp(0.0, 1.0);
    }
    return (value / 100).clamp(0.0, 1.0);
  }

  static String _normalizeDirection(dynamic value) {
    final normalized = value?.toString().trim().toLowerCase();
    if (normalized == 'left' || normalized == 'right') {
      return normalized!;
    }
    return 'center';
  }

  static bool _asBool(dynamic value) {
    if (value is bool) {
      return value;
    }
    final normalized = value?.toString().trim().toLowerCase();
    return normalized == 'true' || normalized == '1' || normalized == 'yes';
  }

  static double? _asNullableDouble(dynamic value) {
    if (value is num) {
      return value.toDouble();
    }
    if (value is String) {
      return double.tryParse(value);
    }
    return null;
  }
}
