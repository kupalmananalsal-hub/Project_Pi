import 'dart:convert';

import 'voice_direction.dart';

enum AlertDecisionState {
  suppressed,
  advisory,
  confirmed,
  critical,
  systemFault,
  unknown,
}

enum AlertModality {
  voiceOnly,
  voiceThermal,
  thermalOnly,
  sensorFault,
  unknown,
}

enum BackendThermalState {
  positive,
  negative,
  unavailable,
  stale,
  invalid,
  unknown,
}

class AlertEvent {
  const AlertEvent({
    this.eventId,
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
    this.directionAngleDegrees,
    this.directionConfidence,
    this.distanceEstimateMeters,
    this.phase = 'direction_guidance',
    this.streamType = 'live',
    this.message,
    this.rawDecisionState,
    this.decisionState = AlertDecisionState.unknown,
    this.decisionReason,
    this.rawAlertModality,
    this.alertModality = AlertModality.unknown,
    this.rawThermalState,
    this.backendThermalState = BackendThermalState.unknown,
    this.policyVersion,
    this.duplicateEvent = false,
  });

  final String? eventId;
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
  final double? directionAngleDegrees;
  final double? directionConfidence;
  final double? distanceEstimateMeters;
  final String phase;
  final String streamType;
  final String? message;
  final String? rawDecisionState;
  final AlertDecisionState decisionState;
  final String? decisionReason;
  final String? rawAlertModality;
  final AlertModality alertModality;
  final String? rawThermalState;
  final BackendThermalState backendThermalState;
  final String? policyVersion;
  final bool duplicateEvent;

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
      final rawDecisionState = _asNullableString(decoded['decision_state']);
      final rawAlertModality = _asNullableString(decoded['alert_modality']);
      final rawThermalState = _asNullableString(decoded['thermal_state']);
      return AlertEvent(
        eventId: _asNullableString(decoded['event_id']),
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
        directionAngleDegrees: _asNullableDouble(
          decoded['direction_angle'] ?? decoded['direction_angle_degrees'],
        ),
        directionConfidence: _asNullableDouble(decoded['direction_confidence']),
        distanceEstimateMeters: _asNullableDouble(
          decoded['distance_estimate_m'] ?? decoded['distance_m'],
        ),
        phase: decoded['phase']?.toString() ?? 'direction_guidance',
        streamType: decoded['type']?.toString() ?? 'live',
        message: decoded['message']?.toString(),
        rawDecisionState: rawDecisionState,
        decisionState: _parseDecisionState(rawDecisionState),
        decisionReason: _asNullableString(decoded['decision_reason']),
        rawAlertModality: rawAlertModality,
        alertModality: _parseAlertModality(rawAlertModality),
        rawThermalState: rawThermalState,
        backendThermalState: _parseThermalState(rawThermalState),
        policyVersion: _asNullableString(decoded['policy_version']),
        duplicateEvent: _asBool(decoded['duplicate_event']),
        timestamp:
            DateTime.tryParse(decoded['timestamp']?.toString() ?? '') ??
            DateTime.now(),
      );
    }
    throw FormatException('Unsupported alert payload: $message');
  }

  bool get isEmergencyKeyword {
    return _keywordWords.any(
      const {
        'help',
        'tulong',
        'save',
        'saklolo',
        'emergency',
        'ambulance',
      }.contains,
    );
  }

  bool get isLive => streamType == 'live';

  bool get isHistorical => streamType == 'historical';

  bool get isConnectionMessage => streamType == 'connected';

  bool get isKeywordDetection => event == 'keyword_detected';

  bool get isVoiceKeywordDetection {
    if (!isLive || duplicateEvent || !isKeywordDetection) {
      return false;
    }
    if (alertModality == AlertModality.thermalOnly ||
        alertModality == AlertModality.sensorFault) {
      return false;
    }
    final hasKeyword = keyword.trim().isNotEmpty && keyword != 'unknown';
    if (!hasKeyword) {
      return false;
    }
    if (alertModality == AlertModality.voiceOnly ||
        alertModality == AlertModality.voiceThermal) {
      return true;
    }
    final normalizedSource = source?.trim().toLowerCase() ?? '';
    return normalizedSource.contains('openwakeword') ||
        normalizedSource.contains('vosk') ||
        normalizedSource.contains('snowboy') ||
        normalizedSource.contains('wav2vec') ||
        normalizedSource.contains('keyword') ||
        normalizedSource.contains('voice');
  }

  bool get hasAuthoritativeDecision =>
      rawDecisionState != null && rawDecisionState!.trim().isNotEmpty;

  bool get isHelpKeyword => _keywordWords.contains('help');

  bool get isTulongKeyword => _keywordWords.contains('tulong');

  double get displayedConfidence => finalConfidence ?? confidence;

  bool get shouldVibrate {
    if (!hasAuthoritativeDecision) {
      return alertLevel == 'full_alert';
    }
    return decisionState == AlertDecisionState.confirmed ||
        decisionState == AlertDecisionState.critical;
  }

  bool get shouldShowDirectionGuidance {
    if (!isLive || !isKeywordDetection || duplicateEvent) {
      return false;
    }
    if (!hasAuthoritativeDecision) {
      return true;
    }
    return switch (decisionState) {
      AlertDecisionState.advisory ||
      AlertDecisionState.confirmed ||
      AlertDecisionState.critical => true,
      AlertDecisionState.suppressed ||
      AlertDecisionState.systemFault ||
      AlertDecisionState.unknown => false,
    };
  }

  VoiceDirection get voiceDirection {
    return VoiceDirection.fromPayload(
      direction: direction,
      angleDegrees: directionAngleDegrees,
      confidence: directionConfidence,
      distanceMeters: distanceEstimateMeters,
    );
  }

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
    return voiceDirection.label;
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
    final normalized = value?.toString().trim().toLowerCase().replaceAll(
      '_',
      '-',
    );
    if (const {
      'front',
      'front-left',
      'front-right',
      'left',
      'right',
      'back-left',
      'back-right',
      'back',
      'center',
    }.contains(normalized)) {
      return normalized!;
    }
    return 'front';
  }

  static bool _asBool(dynamic value) {
    if (value is bool) {
      return value;
    }
    final normalized = value?.toString().trim().toLowerCase();
    return normalized == 'true' || normalized == '1' || normalized == 'yes';
  }

  static String? _asNullableString(dynamic value) {
    final text = value?.toString();
    if (text == null || text.trim().isEmpty) {
      return null;
    }
    return text;
  }

  static AlertDecisionState _parseDecisionState(String? value) {
    switch (value?.trim().toLowerCase()) {
      case 'suppressed':
        return AlertDecisionState.suppressed;
      case 'advisory':
        return AlertDecisionState.advisory;
      case 'confirmed':
        return AlertDecisionState.confirmed;
      case 'critical':
        return AlertDecisionState.critical;
      case 'system_fault':
        return AlertDecisionState.systemFault;
      default:
        return AlertDecisionState.unknown;
    }
  }

  static AlertModality _parseAlertModality(String? value) {
    switch (value?.trim().toLowerCase()) {
      case 'voice_only':
        return AlertModality.voiceOnly;
      case 'voice_thermal':
        return AlertModality.voiceThermal;
      case 'thermal_only':
        return AlertModality.thermalOnly;
      case 'sensor_fault':
        return AlertModality.sensorFault;
      default:
        return AlertModality.unknown;
    }
  }

  static BackendThermalState _parseThermalState(String? value) {
    switch (value?.trim().toLowerCase()) {
      case 'positive':
        return BackendThermalState.positive;
      case 'negative':
        return BackendThermalState.negative;
      case 'unavailable':
        return BackendThermalState.unavailable;
      case 'stale':
        return BackendThermalState.stale;
      case 'invalid':
        return BackendThermalState.invalid;
      default:
        return BackendThermalState.unknown;
    }
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
