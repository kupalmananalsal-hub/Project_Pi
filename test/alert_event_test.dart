import 'package:flutter_test/flutter_test.dart';
import 'package:thermal_audio_monitor/models/alert_event.dart';

void main() {
  test('parses help alert direction', () {
    final event = AlertEvent.fromMessage({
      'event': 'keyword_detected',
      'keyword': 'help',
      'confidence': 0.95,
      'direction': 'left',
      'source': 'snowboy',
      'final_confidence': 0.9,
      'alert_level': 'full_alert',
      'human_detected': true,
      'body_coverage': 0.18,
      'detected_part': 'torso_or_full_face',
      'thermal_confidence_boost': 0.15,
      'decision_factors': {
        'noise_penalty': 0.05,
        'noise_level_db': -38.2,
        'snr_db': 14.6,
      },
      'timestamp': '2026-05-15T01:00:00Z',
    });

    expect(event.isEmergencyKeyword, isTrue);
    expect(event.displayKeyword, 'HELP');
    expect(event.direction, 'left');
    expect(event.directionLabel, 'LEFT');
    expect(event.source, 'snowboy');
    expect(event.displayedConfidence, 0.9);
    expect(event.shouldVibrate, isTrue);
    expect(event.detectedPartLabel, 'Torso or full face');
    expect(event.noiseLevelDb, closeTo(-38.2, 0.01));
    expect(event.isRecognizedConfiguredKeyword, isTrue);
  });

  test('thermal-only events are not recognized KWS keywords', () {
    final event = AlertEvent.fromMessage({
      'event': 'keyword_detected',
      'keyword': 'thermal',
      'confidence': 0,
      'source': 'thermal',
      'direction': 'front',
      'alert_modality': 'thermal_only',
      'decision_state': 'advisory',
      'timestamp': '2026-08-21T00:00:00Z',
    });
    expect(event.isRecognizedConfiguredKeyword, isFalse);
  });
}
