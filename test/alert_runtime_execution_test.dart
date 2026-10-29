import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:thermal_audio_monitor/models/alert_event.dart';
import 'package:thermal_audio_monitor/models/app_settings.dart';
import 'package:thermal_audio_monitor/services/alert_runtime_service.dart';

class TestRuntime extends AlertRuntimeService {
  final playback = Completer<void>();
  int vibrationStarts = 0;
  int audioStarts = 0;
  bool failNotification = false;
  @override
  Future<void> showEmergencyNotification(
    AlertEvent event, {
    required bool vibrate,
  }) async {
    if (failNotification) throw StateError('notification denied');
  }

  @override
  Future<void> stopSoftAudio() async {}
  @override
  Future<void> prepareAudio(AlertSound sound) async {}
  @override
  Future<void> playAudio() {
    audioStarts++;
    return playback.future;
  }

  @override
  Future<void> startVibration() async {
    vibrationStarts++;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  for (final failNotification in [false, true]) {
    test(
      'vibration starts during looping audio; notification failure=$failNotification',
      () async {
        final runtime = TestRuntime()..failNotification = failNotification;
        final event = AlertEvent(
          keyword: 'help',
          confidence: 0.95,
          timestamp: DateTime.now(),
          eventId: 'runtime-test',
        );
        await runtime
            .startEmergency(event, AlertSound.values.first)
            .timeout(const Duration(seconds: 2));
        expect(runtime.playback.isCompleted, isFalse);
        expect(runtime.audioStarts, 1);
        expect(runtime.vibrationStarts, 1);
        runtime.playback.complete();
      },
    );
  }
}
