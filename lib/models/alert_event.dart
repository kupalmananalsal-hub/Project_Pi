import 'dart:convert';

class AlertEvent {
  const AlertEvent({
    required this.keyword,
    required this.confidence,
    required this.timestamp,
    this.event = 'keyword_detected',
  });

  final String event;
  final String keyword;
  final double confidence;
  final DateTime timestamp;

  factory AlertEvent.fromMessage(dynamic message) {
    final decoded = message is String ? jsonDecode(message) : message;
    if (decoded is Map<String, dynamic>) {
      return AlertEvent(
        event: decoded['event']?.toString() ?? 'keyword_detected',
        keyword: decoded['keyword']?.toString() ?? 'unknown',
        confidence: _asDouble(decoded['confidence']),
        timestamp:
            DateTime.tryParse(decoded['timestamp']?.toString() ?? '') ??
            DateTime.now(),
      );
    }
    throw FormatException('Unsupported alert payload: $message');
  }

  bool get isEmergencyKeyword {
    final normalized = keyword.trim().toLowerCase();
    return normalized == 'help' || normalized == 'tulong';
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
}
