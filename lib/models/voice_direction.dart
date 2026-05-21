import 'dart:math' as math;

enum VoiceDirectionSector {
  front,
  frontRight,
  right,
  backRight,
  back,
  backLeft,
  left,
  frontLeft,
  unknown,
}

class VoiceDirection {
  const VoiceDirection({
    required this.sector,
    required this.angleDegrees,
    required this.confidence,
    this.distanceMeters,
  });

  const VoiceDirection.unknown()
    : sector = VoiceDirectionSector.unknown,
      angleDegrees = 0,
      confidence = 0,
      distanceMeters = null;

  final VoiceDirectionSector sector;
  final double angleDegrees;
  final double confidence;
  final double? distanceMeters;

  bool get isKnown => sector != VoiceDirectionSector.unknown;

  String get value {
    switch (sector) {
      case VoiceDirectionSector.front:
        return 'front';
      case VoiceDirectionSector.frontRight:
        return 'front-right';
      case VoiceDirectionSector.right:
        return 'right';
      case VoiceDirectionSector.backRight:
        return 'back-right';
      case VoiceDirectionSector.back:
        return 'back';
      case VoiceDirectionSector.backLeft:
        return 'back-left';
      case VoiceDirectionSector.left:
        return 'left';
      case VoiceDirectionSector.frontLeft:
        return 'front-left';
      case VoiceDirectionSector.unknown:
        return 'unknown';
    }
  }

  String get label {
    switch (sector) {
      case VoiceDirectionSector.front:
        return 'FRONT';
      case VoiceDirectionSector.frontRight:
        return 'FRONT-RIGHT';
      case VoiceDirectionSector.right:
        return 'RIGHT';
      case VoiceDirectionSector.backRight:
        return 'BACK-RIGHT';
      case VoiceDirectionSector.back:
        return 'BACK';
      case VoiceDirectionSector.backLeft:
        return 'BACK-LEFT';
      case VoiceDirectionSector.left:
        return 'LEFT';
      case VoiceDirectionSector.frontLeft:
        return 'FRONT-LEFT';
      case VoiceDirectionSector.unknown:
        return 'UNKNOWN';
    }
  }

  static VoiceDirection fromPayload({
    required String? direction,
    double? angleDegrees,
    double? confidence,
    double? distanceMeters,
    double? leftRms,
    double? rightRms,
  }) {
    final normalized = _normalizeDirection(direction);
    if (normalized != VoiceDirectionSector.unknown) {
      return VoiceDirection(
        sector: normalized,
        angleDegrees: angleDegrees ?? _defaultAngle(normalized),
        confidence: (confidence ?? _confidenceFromLevels(leftRms, rightRms))
            .clamp(0.0, 1.0),
        distanceMeters:
            distanceMeters ??
            (leftRms == null || rightRms == null
                ? null
                : estimateDistance(leftRms, rightRms)),
      );
    }
    return fromLevels(leftRms ?? 0, rightRms ?? 0);
  }

  static VoiceDirection fromLevels(double leftRms, double rightRms) {
    if (leftRms <= 0 && rightRms <= 0) {
      return const VoiceDirection.unknown();
    }
    final total = leftRms + rightRms;
    if (total <= 0) {
      return const VoiceDirection(
        sector: VoiceDirectionSector.front,
        angleDegrees: 0,
        confidence: 0,
      );
    }
    final ratio = (rightRms - leftRms) / total;
    final sector = _sectorFromRatio(ratio);
    return VoiceDirection(
      sector: sector,
      angleDegrees: _defaultAngle(sector),
      confidence: math.min(1.0, ratio.abs() * 2),
      distanceMeters: estimateDistance(leftRms, rightRms),
    );
  }

  static double estimateDistance(double leftRms, double rightRms) {
    final avgLevel = ((leftRms + rightRms) / 2).clamp(0.0, 1.0);
    return (1.0 / (avgLevel + 0.01) * 0.05).clamp(0.5, 10.0);
  }

  static VoiceDirectionSector _normalizeDirection(String? value) {
    final normalized = value?.trim().toLowerCase().replaceAll('_', '-');
    switch (normalized) {
      case 'front':
      case 'center':
        return VoiceDirectionSector.front;
      case 'front-right':
        return VoiceDirectionSector.frontRight;
      case 'right':
        return VoiceDirectionSector.right;
      case 'back-right':
        return VoiceDirectionSector.backRight;
      case 'back':
        return VoiceDirectionSector.back;
      case 'back-left':
        return VoiceDirectionSector.backLeft;
      case 'left':
        return VoiceDirectionSector.left;
      case 'front-left':
        return VoiceDirectionSector.frontLeft;
      default:
        return VoiceDirectionSector.unknown;
    }
  }

  static VoiceDirectionSector _sectorFromRatio(double ratio) {
    if (ratio >= -0.1 && ratio <= 0.1) {
      return VoiceDirectionSector.front;
    }
    if (ratio > 0.1 && ratio <= 0.3) {
      return VoiceDirectionSector.frontRight;
    }
    if (ratio > 0.3 && ratio <= 0.6) {
      return VoiceDirectionSector.right;
    }
    if (ratio > 0.6) {
      return VoiceDirectionSector.backRight;
    }
    if (ratio < -0.1 && ratio >= -0.3) {
      return VoiceDirectionSector.frontLeft;
    }
    if (ratio < -0.3 && ratio >= -0.6) {
      return VoiceDirectionSector.left;
    }
    return VoiceDirectionSector.backLeft;
  }

  static double _defaultAngle(VoiceDirectionSector sector) {
    switch (sector) {
      case VoiceDirectionSector.front:
        return 0;
      case VoiceDirectionSector.frontRight:
        return 45;
      case VoiceDirectionSector.right:
        return 90;
      case VoiceDirectionSector.backRight:
        return 135;
      case VoiceDirectionSector.back:
        return 180;
      case VoiceDirectionSector.backLeft:
        return -135;
      case VoiceDirectionSector.left:
        return -90;
      case VoiceDirectionSector.frontLeft:
        return -45;
      case VoiceDirectionSector.unknown:
        return 0;
    }
  }

  static double _confidenceFromLevels(double? leftRms, double? rightRms) {
    if (leftRms == null || rightRms == null) {
      return 0.5;
    }
    final total = leftRms + rightRms;
    if (total <= 0) {
      return 0;
    }
    return math.min(1.0, ((rightRms - leftRms) / total).abs() * 2);
  }
}
