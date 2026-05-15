import 'dart:convert';

class AlertEvent {
  const AlertEvent({
    required this.keyword,
    required this.confidence,
    required this.timestamp,
    this.direction = 'center',
    this.source,
    this.event = 'keyword_detected',
  });

  final String event;
  final String keyword;
  final double confidence;
  final String direction;
  final String? source;
  final DateTime timestamp;

  factory AlertEvent.fromMessage(dynamic message) {
    final decoded = message is String ? jsonDecode(message) : message;
    if (decoded is Map<String, dynamic>) {
      return AlertEvent(
        event: decoded['event']?.toString() ?? 'keyword_detected',
        keyword: decoded['keyword']?.toString() ?? 'unknown',
        confidence: _asDouble(decoded['confidence']),
        direction: _normalizeDirection(decoded['direction']),
        source: decoded['source']?.toString(),
        timestamp:
            DateTime.tryParse(decoded['timestamp']?.toString() ?? '') ??
            DateTime.now(),
      );
    }
    throw FormatException('Unsupported alert payload: $message');
  }

  bool get isEmergencyKeyword {
    return isHelpKeyword || isTulongKeyword;
  }

  bool get isHelpKeyword => _keywordWords.contains('help');

  bool get isTulongKeyword => _keywordWords.contains('tulong');

  String get displayKeyword {
    if (isHelpKeyword) {
      return 'HELP';
    }
    if (isTulongKeyword) {
      return 'TULONG';
    }
    final trimmed = keyword.trim();
    return trimmed.isEmpty ? 'UNKNOWN' : trimmed.toUpperCase();
  }

  String get directionLabel {
    switch (direction) {
      case 'left':
        return 'LEFT';
      case 'right':
        return 'RIGHT';
      default:
        return 'CENTER';
    }
  }

  String get emergencyTitle =>
      isEmergencyKeyword ? '$displayKeyword detected' : 'Keyword detected';

  Set<String> get _keywordWords {
    final normalized = keyword.trim().toLowerCase().replaceAll(
      RegExp(r'[^a-z0-9]+'),
      ' ',
    );
    return normalized
        .split(RegExp(r'\s+'))
        .where((word) => word.isNotEmpty)
        .toSet();
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

  static String _normalizeDirection(dynamic value) {
    final normalized = value?.toString().trim().toLowerCase();
    if (normalized == 'left' || normalized == 'right') {
      return normalized!;
    }
    return 'center';
  }
}
