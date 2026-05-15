import '../models/thermal_frame.dart';

class HumanDetectionResult {
  const HumanDetectionResult({
    required this.detected,
    this.blob,
    this.averageTemperature,
    this.bodyCoverage = 0,
    this.detectedPart = 'no_human',
    this.confidenceBoost = 0,
    this.temperatureMin,
    this.temperatureMax,
  });

  final bool detected;
  final HumanBlob? blob;
  final double? averageTemperature;
  final double bodyCoverage;
  final String detectedPart;
  final double confidenceBoost;
  final double? temperatureMin;
  final double? temperatureMax;

  String get detectedPartLabel {
    switch (detectedPart) {
      case 'finger_detected':
        return 'Finger detected';
      case 'hand_or_partial_face':
        return 'Hand or partial face';
      case 'torso_or_full_face':
        return 'Torso or full face';
      case 'analysis_error':
        return 'Analysis error';
      default:
        return 'No human';
    }
  }
}

class HumanBlob {
  const HumanBlob({
    required this.x,
    required this.y,
    required this.width,
    required this.height,
    required this.pixelCount,
  });

  final int x;
  final int y;
  final int width;
  final int height;
  final int pixelCount;
}

class HumanDetector {
  static const double minTemp = 30.0;
  static const double maxTemp = 40.0;
  static const double fingerThreshold = 0.01;
  static const double handThreshold = 0.05;
  static const double fullBodyThreshold = 0.15;
  static const double minBlobSizePercent = 0.01;
  static const double maxBlobSizePercent = 0.40;

  static bool detectHuman(List<double> temperatures, int width, int height) {
    return analyze(temperatures, width, height).detected;
  }

  static HumanDetectionResult fromThermalFrame(ThermalFrame frame) {
    if (frame.hasConfidenceMetadata) {
      return HumanDetectionResult(
        detected: frame.humanDetected,
        averageTemperature: frame.humanTemperatureAverage,
        bodyCoverage: frame.bodyCoverage,
        detectedPart: frame.detectedPart,
        confidenceBoost: frame.confidenceBoost,
        temperatureMin: frame.humanTemperatureMin,
        temperatureMax: frame.humanTemperatureMax,
      );
    }
    return analyze(frame.pixels, frame.width, frame.height);
  }

  static HumanDetectionResult analyze(
    List<double> temperatures,
    int width,
    int height,
  ) {
    if (temperatures.length < width * height || width <= 0 || height <= 0) {
      return const HumanDetectionResult(detected: false);
    }

    final visited = List<bool>.filled(width * height, false);
    final totalPixels = width * height;
    var humanPixelCount = 0;
    HumanBlob? bestBlob;
    double? bestAverage;
    double? bestMin;
    double? bestMax;

    for (var index = 0; index < totalPixels; index++) {
      if (visited[index] || !_isBodyTemperature(temperatures[index])) {
        continue;
      }

      final result = _floodFill(temperatures, visited, width, height, index);
      humanPixelCount += result.blob.pixelCount;
      final blob = result.blob;
      final sizePercent = blob.pixelCount / totalPixels;
      final aspectRatio = blob.width == 0 ? 0 : blob.height / blob.width;
      final validSize =
          sizePercent >= minBlobSizePercent &&
          sizePercent <= maxBlobSizePercent;
      final validShape = aspectRatio >= 0.7 && aspectRatio <= 4.5;

      if (validSize && validShape) {
        if (bestBlob == null || blob.pixelCount > bestBlob.pixelCount) {
          bestBlob = blob;
          bestAverage = result.averageTemperature;
          bestMin = result.minTemperature;
          bestMax = result.maxTemperature;
        }
      }
    }

    final bodyCoverage = humanPixelCount / totalPixels;
    final detectedPart = _detectedPartForCoverage(bodyCoverage);
    final confidenceBoost = _confidenceBoostForCoverage(bodyCoverage);

    return HumanDetectionResult(
      detected: bodyCoverage >= fingerThreshold && bestBlob != null,
      blob: bestBlob,
      averageTemperature: bestAverage,
      bodyCoverage: bodyCoverage,
      detectedPart: detectedPart,
      confidenceBoost: confidenceBoost,
      temperatureMin: bestMin,
      temperatureMax: bestMax,
    );
  }

  static bool _isBodyTemperature(double value) {
    return value >= minTemp && value <= maxTemp;
  }

  static String _detectedPartForCoverage(double coverage) {
    if (coverage < fingerThreshold) {
      return 'no_human';
    }
    if (coverage < handThreshold) {
      return 'finger_detected';
    }
    if (coverage < fullBodyThreshold) {
      return 'hand_or_partial_face';
    }
    return 'torso_or_full_face';
  }

  static double _confidenceBoostForCoverage(double coverage) {
    if (coverage < fingerThreshold) {
      return 0.0;
    }
    if (coverage < handThreshold) {
      return 0.05;
    }
    if (coverage < fullBodyThreshold) {
      return 0.10;
    }
    return 0.15;
  }

  static _FloodFillResult _floodFill(
    List<double> temperatures,
    List<bool> visited,
    int width,
    int height,
    int start,
  ) {
    final queue = <int>[start];
    visited[start] = true;

    var minX = width;
    var minY = height;
    var maxX = 0;
    var maxY = 0;
    var pixelCount = 0;
    var tempSum = 0.0;
    var tempMin = double.infinity;
    var tempMax = double.negativeInfinity;

    while (queue.isNotEmpty) {
      final index = queue.removeLast();
      final x = index % width;
      final y = index ~/ width;
      minX = x < minX ? x : minX;
      minY = y < minY ? y : minY;
      maxX = x > maxX ? x : maxX;
      maxY = y > maxY ? y : maxY;
      pixelCount++;
      final temperature = temperatures[index];
      tempSum += temperature;
      tempMin = temperature < tempMin ? temperature : tempMin;
      tempMax = temperature > tempMax ? temperature : tempMax;

      void visit(int nx, int ny) {
        if (nx < 0 || ny < 0 || nx >= width || ny >= height) {
          return;
        }
        final next = (ny * width) + nx;
        if (visited[next] || !_isBodyTemperature(temperatures[next])) {
          return;
        }
        visited[next] = true;
        queue.add(next);
      }

      visit(x - 1, y);
      visit(x + 1, y);
      visit(x, y - 1);
      visit(x, y + 1);
    }

    return _FloodFillResult(
      blob: HumanBlob(
        x: minX,
        y: minY,
        width: (maxX - minX) + 1,
        height: (maxY - minY) + 1,
        pixelCount: pixelCount,
      ),
      averageTemperature: tempSum / pixelCount,
      minTemperature: tempMin,
      maxTemperature: tempMax,
    );
  }
}

class _FloodFillResult {
  const _FloodFillResult({
    required this.blob,
    required this.averageTemperature,
    required this.minTemperature,
    required this.maxTemperature,
  });

  final HumanBlob blob;
  final double averageTemperature;
  final double minTemperature;
  final double maxTemperature;
}
