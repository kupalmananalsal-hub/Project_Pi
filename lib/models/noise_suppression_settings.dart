class NoiseSuppressionSettings {
  const NoiseSuppressionSettings({
    required this.active,
    required this.strength,
    required this.sensitivity,
    required this.noiseFloorDb,
    required this.snrEstimate,
    required this.reductionDb,
    this.snowboySensitivity,
  });

  const NoiseSuppressionSettings.defaults()
    : active = true,
      strength = 0.5,
      sensitivity = 0.5,
      noiseFloorDb = -60.0,
      snrEstimate = 20.0,
      reductionDb = 0.0,
      snowboySensitivity = null;

  final bool active;
  final double strength;
  final double sensitivity;
  final double noiseFloorDb;
  final double snrEstimate;
  final double reductionDb;
  final double? snowboySensitivity;

  factory NoiseSuppressionSettings.fromJson(Map<String, dynamic> json) {
    return NoiseSuppressionSettings(
      active: _asBool(json['active'], fallback: true),
      strength: _asDouble(json['strength'], fallback: 0.5),
      sensitivity: _asDouble(json['sensitivity'], fallback: 0.5),
      noiseFloorDb: _asDouble(json['noise_floor_db'], fallback: -60.0),
      snrEstimate: _asDouble(json['snr_estimate'], fallback: 20.0),
      reductionDb: _asDouble(json['reduction_db'], fallback: 0.0),
      snowboySensitivity: _asNullableDouble(json['snowboy_sensitivity']),
    );
  }

  NoiseSuppressionSettings copyWith({
    bool? active,
    double? strength,
    double? sensitivity,
    double? noiseFloorDb,
    double? snrEstimate,
    double? reductionDb,
    Object? snowboySensitivity = _unset,
  }) {
    return NoiseSuppressionSettings(
      active: active ?? this.active,
      strength: strength ?? this.strength,
      sensitivity: sensitivity ?? this.sensitivity,
      noiseFloorDb: noiseFloorDb ?? this.noiseFloorDb,
      snrEstimate: snrEstimate ?? this.snrEstimate,
      reductionDb: reductionDb ?? this.reductionDb,
      snowboySensitivity: snowboySensitivity == _unset
          ? this.snowboySensitivity
          : snowboySensitivity as double?,
    );
  }

  Map<String, dynamic> toRequestJson() {
    return {
      'active': active,
      'strength': strength,
      'sensitivity': sensitivity,
      if (snowboySensitivity != null) 'snowboy_sensitivity': snowboySensitivity,
    };
  }

  static double _asDouble(dynamic value, {required double fallback}) {
    if (value is num) {
      return value.toDouble();
    }
    if (value is String) {
      return double.tryParse(value) ?? fallback;
    }
    return fallback;
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

  static bool _asBool(dynamic value, {required bool fallback}) {
    if (value is bool) {
      return value;
    }
    final normalized = value?.toString().trim().toLowerCase();
    if (normalized == null) {
      return fallback;
    }
    return normalized == 'true' ||
        normalized == '1' ||
        normalized == 'yes' ||
        normalized == 'on';
  }
}

enum NoiseSuppressionPreset { quietRoom, normal, noisy, off }

extension NoiseSuppressionPresetInfo on NoiseSuppressionPreset {
  String get label {
    switch (this) {
      case NoiseSuppressionPreset.quietRoom:
        return 'Quiet Room';
      case NoiseSuppressionPreset.normal:
        return 'Normal';
      case NoiseSuppressionPreset.noisy:
        return 'Noisy';
      case NoiseSuppressionPreset.off:
        return 'Off';
    }
  }

  NoiseSuppressionSettings build() {
    switch (this) {
      case NoiseSuppressionPreset.quietRoom:
        return const NoiseSuppressionSettings(
          active: true,
          strength: 0.2,
          sensitivity: 0.7,
          noiseFloorDb: -60.0,
          snrEstimate: 20.0,
          reductionDb: 0.0,
          snowboySensitivity: 0.42,
        );
      case NoiseSuppressionPreset.normal:
        return const NoiseSuppressionSettings(
          active: true,
          strength: 0.5,
          sensitivity: 0.5,
          noiseFloorDb: -55.0,
          snrEstimate: 14.0,
          reductionDb: 0.0,
          snowboySensitivity: 0.40,
        );
      case NoiseSuppressionPreset.noisy:
        return const NoiseSuppressionSettings(
          active: true,
          strength: 0.8,
          sensitivity: 0.3,
          noiseFloorDb: -45.0,
          snrEstimate: 8.0,
          reductionDb: 0.0,
          snowboySensitivity: 0.38,
        );
      case NoiseSuppressionPreset.off:
        return const NoiseSuppressionSettings(
          active: false,
          strength: 0.0,
          sensitivity: 1.0,
          noiseFloorDb: -60.0,
          snrEstimate: 20.0,
          reductionDb: 0.0,
          snowboySensitivity: 0.40,
        );
    }
  }
}

const _unset = Object();
