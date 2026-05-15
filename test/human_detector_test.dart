import 'package:flutter_test/flutter_test.dart';
import 'package:thermal_audio_monitor/utils/human_detector.dart';

void main() {
  test('detects a warm vertical human-like blob', () {
    const width = 32;
    const height = 24;
    final pixels = List<double>.filled(width * height, 24);

    for (var y = 3; y < 21; y++) {
      for (var x = 12; x < 20; x++) {
        pixels[(y * width) + x] = 34;
      }
    }

    final result = HumanDetector.analyze(pixels, width, height);

    expect(result.detected, isTrue);
    expect(result.averageTemperature, closeTo(34, 0.1));
  });

  test('rejects small warm noise', () {
    const width = 32;
    const height = 24;
    final pixels = List<double>.filled(width * height, 24);

    for (var y = 3; y < 6; y++) {
      for (var x = 12; x < 15; x++) {
        pixels[(y * width) + x] = 34;
      }
    }

    expect(HumanDetector.detectHuman(pixels, width, height), isFalse);
  });
}
