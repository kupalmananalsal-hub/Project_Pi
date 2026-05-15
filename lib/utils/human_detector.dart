class HumanDetectionResult {
  const HumanDetectionResult({
    required this.detected,
    this.blob,
    this.averageTemperature,
  });

  final bool detected;
  final HumanBlob? blob;
  final double? averageTemperature;
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
  static const double minBlobSizePercent = 0.15;
  static const double maxBlobSizePercent = 0.40;

  static bool detectHuman(List<double> temperatures, int width, int height) {
    return analyze(temperatures, width, height).detected;
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
    HumanBlob? bestBlob;
    double? bestAverage;

    for (var index = 0; index < totalPixels; index++) {
      if (visited[index] || !_isBodyTemperature(temperatures[index])) {
        continue;
      }

      final result = _floodFill(temperatures, visited, width, height, index);
      final blob = result.blob;
      final sizePercent = blob.pixelCount / totalPixels;
      final aspectRatio = blob.height / blob.width;
      final validSize =
          sizePercent >= minBlobSizePercent &&
          sizePercent <= maxBlobSizePercent;
      final validShape = aspectRatio >= 1.5 && aspectRatio <= 4.0;

      if (validSize && validShape) {
        if (bestBlob == null || blob.pixelCount > bestBlob.pixelCount) {
          bestBlob = blob;
          bestAverage = result.averageTemperature;
        }
      }
    }

    return HumanDetectionResult(
      detected: bestBlob != null,
      blob: bestBlob,
      averageTemperature: bestAverage,
    );
  }

  static bool _isBodyTemperature(double value) {
    return value >= minTemp && value <= maxTemp;
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

    while (queue.isNotEmpty) {
      final index = queue.removeLast();
      final x = index % width;
      final y = index ~/ width;
      minX = x < minX ? x : minX;
      minY = y < minY ? y : minY;
      maxX = x > maxX ? x : maxX;
      maxY = y > maxY ? y : maxY;
      pixelCount++;
      tempSum += temperatures[index];

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
    );
  }
}

class _FloodFillResult {
  const _FloodFillResult({
    required this.blob,
    required this.averageTemperature,
  });

  final HumanBlob blob;
  final double averageTemperature;
}
