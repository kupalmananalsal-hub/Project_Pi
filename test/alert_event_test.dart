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
      'timestamp': '2026-05-15T01:00:00Z',
    });

    expect(event.isEmergencyKeyword, isTrue);
    expect(event.displayKeyword, 'HELP');
    expect(event.direction, 'left');
    expect(event.directionLabel, 'LEFT');
    expect(event.source, 'snowboy');
  });
}
