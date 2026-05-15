import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';

enum ThermalColorMap { jet, inferno, magma, hot, bone }

extension ThermalColorMapLabel on ThermalColorMap {
  String get label {
    switch (this) {
      case ThermalColorMap.jet:
        return 'Jet';
      case ThermalColorMap.inferno:
        return 'Inferno';
      case ThermalColorMap.magma:
        return 'Magma';
      case ThermalColorMap.hot:
        return 'Hot';
      case ThermalColorMap.bone:
        return 'Bone';
    }
  }
}

class ThermalFrame {
  const ThermalFrame({
    required this.width,
    required this.height,
    required this.pixels,
    required this.timestamp,
    this.humanDetected = false,
    this.bodyCoverage = 0,
    this.detectedPart = 'no_human',
    this.confidenceBoost = 0,
    this.humanTemperatureAverage,
    this.humanTemperatureMin,
    this.humanTemperatureMax,
    this.hasConfidenceMetadata = false,
  });

  final int width;
  final int height;
  final List<double> pixels;
  final DateTime timestamp;
  final bool humanDetected;
  final double bodyCoverage;
  final String detectedPart;
  final double confidenceBoost;
  final double? humanTemperatureAverage;
  final double? humanTemperatureMin;
  final double? humanTemperatureMax;
  final bool hasConfidenceMetadata;

  factory ThermalFrame.fromMessage(dynamic message) {
    final decoded = message is String ? jsonDecode(message) : message;
    if (decoded is List) {
      return _fromSamples(decoded);
    }
    if (decoded is Map<String, dynamic>) {
      final width = _asInt(decoded['width'], fallback: 32);
      final height = _asInt(decoded['height'], fallback: 24);
      final samples =
          decoded['temperatures'] ??
          decoded['thermal'] ??
          decoded['frame'] ??
          decoded['pixels'] ??
          decoded['data'] ??
          decoded['array'];
      final timestamp =
          DateTime.tryParse(decoded['timestamp']?.toString() ?? '') ??
          DateTime.now();
      final hasConfidenceMetadata =
          decoded.containsKey('human_detected') ||
          decoded.containsKey('body_coverage') ||
          decoded.containsKey('confidence_boost');
      return _fromSamples(samples, width: width, height: height).copyWith(
        timestamp: timestamp,
        humanDetected: _asBool(decoded['human_detected']),
        bodyCoverage: _asDouble(decoded['body_coverage']) ?? 0,
        detectedPart: decoded['detected_part']?.toString() ?? 'no_human',
        confidenceBoost: _asDouble(decoded['confidence_boost']) ?? 0,
        humanTemperatureAverage: _asDouble(
          decoded['human_temp_avg'] ?? decoded['average_temperature'],
        ),
        humanTemperatureMin: _asDouble(decoded['human_temp_min']),
        humanTemperatureMax: _asDouble(decoded['human_temp_max']),
        hasConfidenceMetadata: hasConfidenceMetadata,
      );
    }
    throw FormatException('Unsupported thermal payload: $message');
  }

  double get minTemperature =>
      pixels.isEmpty ? 0 : pixels.reduce(math.min).toDouble();

  double get maxTemperature =>
      pixels.isEmpty ? 0 : pixels.reduce(math.max).toDouble();

  double get centerTemperature => temperatureAt(width ~/ 2, height ~/ 2);

  ({double min, double max}) clippedTemperatureRange({
    double clipPercent = 0.02,
  }) {
    if (pixels.isEmpty) {
      return (min: 20, max: 45);
    }
    final sorted = [...pixels]..sort();
    final lowerIndex = (sorted.length * clipPercent).floor().clamp(
      0,
      sorted.length - 1,
    );
    final upperIndex = (sorted.length * (1 - clipPercent)).ceil().clamp(
      0,
      sorted.length - 1,
    );
    final minValue = sorted[lowerIndex];
    final maxValue = sorted[upperIndex];
    if ((maxValue - minValue).abs() < 0.5) {
      return (min: minValue - 0.25, max: maxValue + 0.25);
    }
    return (min: minValue, max: maxValue);
  }

  double temperatureAt(int x, int y) {
    if (pixels.isEmpty) {
      return 0;
    }
    final clampedX = x.clamp(0, width - 1);
    final clampedY = y.clamp(0, height - 1);
    return pixels[(clampedY * width) + clampedX];
  }

  ThermalFrame copyWith({
    int? width,
    int? height,
    List<double>? pixels,
    DateTime? timestamp,
    bool? humanDetected,
    double? bodyCoverage,
    String? detectedPart,
    double? confidenceBoost,
    Object? humanTemperatureAverage = _unset,
    Object? humanTemperatureMin = _unset,
    Object? humanTemperatureMax = _unset,
    bool? hasConfidenceMetadata,
  }) {
    return ThermalFrame(
      width: width ?? this.width,
      height: height ?? this.height,
      pixels: pixels ?? this.pixels,
      timestamp: timestamp ?? this.timestamp,
      humanDetected: humanDetected ?? this.humanDetected,
      bodyCoverage: bodyCoverage ?? this.bodyCoverage,
      detectedPart: detectedPart ?? this.detectedPart,
      confidenceBoost: confidenceBoost ?? this.confidenceBoost,
      humanTemperatureAverage: humanTemperatureAverage == _unset
          ? this.humanTemperatureAverage
          : humanTemperatureAverage as double?,
      humanTemperatureMin: humanTemperatureMin == _unset
          ? this.humanTemperatureMin
          : humanTemperatureMin as double?,
      humanTemperatureMax: humanTemperatureMax == _unset
          ? this.humanTemperatureMax
          : humanTemperatureMax as double?,
      hasConfidenceMetadata:
          hasConfidenceMetadata ?? this.hasConfidenceMetadata,
    );
  }

  static ThermalFrame _fromSamples(
    dynamic samples, {
    int width = 32,
    int height = 24,
  }) {
    final pixels = _flattenSamples(samples);
    if (pixels.isEmpty) {
      throw const FormatException('Thermal payload did not contain pixels.');
    }

    var resolvedHeight = height;
    if (pixels.length != width * resolvedHeight && pixels.length % width == 0) {
      resolvedHeight = pixels.length ~/ width;
    }

    return ThermalFrame(
      width: width,
      height: resolvedHeight,
      pixels: pixels,
      timestamp: DateTime.now(),
    );
  }

  static List<double> _flattenSamples(dynamic samples) {
    if (samples is List) {
      final values = <double>[];
      for (final item in samples) {
        if (item is List) {
          values.addAll(_flattenSamples(item));
        } else {
          final value = _asDouble(item);
          if (value != null) {
            values.add(value);
          }
        }
      }
      return values;
    }
    return const [];
  }

  static int _asInt(dynamic value, {required int fallback}) {
    if (value is int) {
      return value;
    }
    if (value is num) {
      return value.round();
    }
    if (value is String) {
      return int.tryParse(value) ?? fallback;
    }
    return fallback;
  }

  static double? _asDouble(dynamic value) {
    if (value is num) {
      return value.toDouble();
    }
    if (value is String) {
      return double.tryParse(value);
    }
    return null;
  }

  static bool _asBool(dynamic value) {
    if (value is bool) {
      return value;
    }
    final normalized = value?.toString().trim().toLowerCase();
    return normalized == 'true' || normalized == '1' || normalized == 'yes';
  }
}

const _unset = Object();

Color thermalColorForValue(
  double value,
  double min,
  double max,
  ThermalColorMap colorMap,
) {
  final span = (max - min).abs() < 0.001 ? 1.0 : max - min;
  final t = ((value - min) / span).clamp(0.0, 1.0).toDouble();

  switch (colorMap) {
    case ThermalColorMap.jet:
      return _palette(t, const [
        Color(0xFF0015A8),
        Color(0xFF008BFF),
        Color(0xFF00FF70),
        Color(0xFFFFE600),
        Color(0xFFFF8A00),
        Color(0xFFFF2A00),
        Color(0xFF7A0000),
      ]);
    case ThermalColorMap.inferno:
      return _palette(t, const [
        Color(0xFF000004),
        Color(0xFF420A68),
        Color(0xFF932667),
        Color(0xFFDD513A),
        Color(0xFFFCA50A),
        Color(0xFFFCFFA4),
      ]);
    case ThermalColorMap.magma:
      return _palette(t, const [
        Color(0xFF000004),
        Color(0xFF3B0F70),
        Color(0xFF8C2981),
        Color(0xFFDE4968),
        Color(0xFFFE9F6D),
        Color(0xFFFCFDBF),
      ]);
    case ThermalColorMap.hot:
      return _palette(t, const [
        Color(0xFF120000),
        Color(0xFF960000),
        Color(0xFFFF4C00),
        Color(0xFFFFD400),
        Color(0xFFFFFFFF),
      ]);
    case ThermalColorMap.bone:
      return _palette(t, const [
        Color(0xFF03050A),
        Color(0xFF263447),
        Color(0xFF596F7D),
        Color(0xFFA2AAA4),
        Color(0xFFFFFFFF),
      ]);
  }
}

Color _palette(double t, List<Color> stops) {
  if (t <= 0) {
    return stops.first;
  }
  if (t >= 1) {
    return stops.last;
  }
  final scaled = t * (stops.length - 1);
  final index = scaled.floor();
  final localT = scaled - index;
  return Color.lerp(stops[index], stops[index + 1], localT) ?? stops[index];
}
