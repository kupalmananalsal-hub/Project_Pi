import 'dart:convert';

class AlertEvent {
  const AlertEvent({
    required this.keyword,
    required this.confidence,
    required this.timestamp,
    this.direction = 'center',
    this.source,
    this.event = 'keyword_detected',
    this.finalConfidence,
    this.alertLevel = 'visual_only',
    this.humanDetected = false,
    this.bodyCoverage = 0,
    this.detectedPart = 'no_human',
    this.thermalConfidenceBoost = 0,
    this.noisePenalty = 0,
    this.noiseLevelDb,
    this.signalLevelDb,
    this.snrDb,
  });

  final String event;
  final String keyword;
  final double confidence;
  final String direction;
  final String? source;
  final DateTime timestamp;
  final double? finalConfidence;
  final String alertLevel;
  final bool humanDetected;
  final double bodyCoverage;
  final String detectedPart;
  final double thermalConfidenceBoost;
  final double noisePenalty;
  final double? noiseLevelDb;
  final double? signalLevelDb;
  final double? snrDb;

  factory AlertEvent.fromMessage(dynamic message) {
    final decoded = message is String ? jsonDecode(message) : message;
    if (decoded is Map<String, dynamic>) {
      final factors = decoded['decision_factors'];
      final decisionFactors = factors is Map<String, dynamic>
          ? factors
          : const <String, dynamic>{};
      final parsedConfidence = _asDouble(decoded['confidence']);
      final parsedFinalConfidence =
          _asNullableDouble(decoded['final_confidence']) ??
          _asNullableDouble(decisionFactors['final_confidence']);
      return AlertEvent(
        event: decoded['event']?.toString() ?? 'keyword_detected',
        keyword: decoded['keyword']?.toString() ?? 'unknown',
        confidence: parsedConfidence,
        direction: _normalizeDirection(decoded['direction']),
        source: decoded['source']?.toString(),
        finalConfidence: parsedFinalConfidence,
        alertLevel:
            decoded['alert_level']?.toString() ??
            _alertLevelForConfidence(parsedFinalConfidence ?? parsedConfidence),
        humanDetected: _asBool(
          decoded['human_detected'] ?? decisionFactors['human_detected'],
        ),
        bodyCoverage:
            _asNullableDouble(
              decoded['body_coverage'] ?? decisionFactors['body_coverage'],
            ) ??
            0,
        detectedPart:
            decoded['detected_part']?.toString() ??
            decisionFactors['detected_part']?.toString() ??
            'no_human',
        thermalConfidenceBoost:
            _asNullableDouble(
              decoded['thermal_confidence_boost'] ??
                  decisionFactors['thermal_boost'],
            ) ??
            0,
        noisePenalty: _asNullableDouble(decisionFactors['noise_penalty']) ?? 0,
        noiseLevelDb: _asNullableDouble(
          decoded['noise_level_db'] ?? decisionFactors['noise_level_db'],
        ),
        signalLevelDb: _asNullableDouble(
          decoded['signal_level_db'] ?? decisionFactors['signal_level_db'],
        ),
        snrDb: _asNullableDouble(
          decoded['snr_db'] ?? decisionFactors['snr_db'],
        ),
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

  double get displayedConfidence => finalConfidence ?? confidence;

  bool get shouldVibrate => alertLevel == 'full_alert';

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

  String get detectedPartLabel {
    switch (detectedPart) {
      case 'finger_detected':
        return 'Finger detected';
      case 'hand_or_partial_face':
        return 'Hand or partial face';
      case 'torso_or_full_face':
        return 'Torso or full face';
      case 'analysis_error':
        return 'Thermal analysis error';
      default:
        return 'No human detected';
    }
  }

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

  static double? _asNullableDouble(dynamic value) {
    if (value is num) {
      return value.toDouble();
    }
    if (value is String) {
      return double.tryParse(value);
    }
    return null;
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

  static String _alertLevelForConfidence(double confidence) {
    if (confidence >= 0.85) {
      return 'full_alert';
    }
    if (confidence >= 0.70) {
      return 'visual_only';
    }
    return 'none';
  }
}
