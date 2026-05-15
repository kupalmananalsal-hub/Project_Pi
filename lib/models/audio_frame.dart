import 'dart:convert';

class AudioFrame {
  const AudioFrame({
    required this.leftRms,
    required this.rightRms,
    required this.timestamp,
    this.direction = 'center',
  });

  final double leftRms;
  final double rightRms;
  final String direction;
  final DateTime timestamp;

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
        timestamp: timestamp,
      );
    }
    throw FormatException('Unsupported audio payload: $message');
  }

  double get normalizedLeft => _normalize(leftRms);

  double get normalizedRight => _normalize(rightRms);

  static double _asDouble(dynamic value) {
    if (value is num) {
      return value.toDouble();
    }
    if (value is String) {
      return double.tryParse(value) ?? 0;
    }
    return 0;
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
}
