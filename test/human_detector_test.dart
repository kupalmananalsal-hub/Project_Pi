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
    expect(result.bodyCoverage, greaterThan(0.15));
    expect(result.detectedPart, 'torso_or_full_face');
    expect(result.confidenceBoost, 0.15);
  });

  test('rejects small warm noise', () {
    const width = 32;
    const height = 24;
    final pixels = List<double>.filled(width * height, 24);

    for (var y = 3; y < 5; y++) {
      for (var x = 12; x < 15; x++) {
        pixels[(y * width) + x] = 34;
      }
    }

    expect(HumanDetector.detectHuman(pixels, width, height), isFalse);
  });

  test('scores small warm region as finger-like coverage', () {
    const width = 32;
    const height = 24;
    final pixels = List<double>.filled(width * height, 24);

    for (var y = 10; y < 14; y++) {
      for (var x = 14; x < 18; x++) {
        pixels[(y * width) + x] = 33;
      }
    }

    final result = HumanDetector.analyze(pixels, width, height);

    expect(result.bodyCoverage, greaterThan(0.01));
    expect(result.detectedPart, 'finger_detected');
    expect(result.confidenceBoost, 0.05);
  });
}
