import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:thermal_audio_monitor/models/alert_event.dart';
import 'package:thermal_audio_monitor/models/app_settings.dart';
import 'package:thermal_audio_monitor/services/alert_runtime_service.dart';

class TestRuntime extends AlertRuntimeService {
  TestRuntime() : super(operationTimeout: const Duration(milliseconds: 30));
  Completer<void>? notificationGate;
  Completer<void>? preparationGate;
  int stops = 0;
  @override
  Future<void> stopAudio() async {
    stops++;
  }

  @override
  Future<void> stopVibration() async {}
  @override
  Future<void> cancelNotification() async {}
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
    await notificationGate?.future;
  }

  @override
  Future<void> stopSoftAudio() async {}
  @override
  Future<void> prepareAudio(AlertSound sound) async {
    await preparationGate?.future;
  }

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

class RecoveringAudioRuntime extends TestRuntime {
  int configurations = 0;
  Completer<void>? configurationGate;
  @override
  Future<void> configureAudioSession() async {
    configurations++;
    await configurationGate?.future;
    if (configurations == 1) throw StateError('transient_audio_plugin_failure');
  }

  @override
  Future<void> prepareAudio(AlertSound sound) => configureAudio();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test('audio configuration failure retries on next emergency', () async {
    final runtime = RecoveringAudioRuntime();
    final event = AlertEvent(
      keyword: 'help',
      confidence: .99,
      timestamp: DateTime.now(),
      eventId: 'audio-recovery',
    );
    await runtime.startEmergency(event, AlertSound.values.first);
    expect(runtime.configurations, 1);
    expect(runtime.audioStarts, 0);
    await runtime.startEmergency(event, AlertSound.values.first);
    expect(runtime.configurations, 2);
    expect(runtime.audioStarts, 1);
    await runtime.configureAudio();
    expect(runtime.configurations, 2);
    runtime.playback.complete();
  });
  test(
    'concurrent audio callers share failure and one successful retry',
    () async {
      final runtime = RecoveringAudioRuntime()
        ..configurationGate = Completer<void>();
      final first = runtime.configureAudio();
      final concurrent = runtime.configureAudio();
      expect(identical(first, concurrent), isTrue);
      final checked = expectLater(first, throwsStateError);
      runtime.configurationGate!.complete();
      await checked;
      runtime.configurationGate = Completer<void>();
      final retry = runtime.configureAudio();
      expect(identical(retry, runtime.configureAudio()), isTrue);
      runtime.configurationGate!.complete();
      await retry;
      expect(runtime.configurations, 2);
    },
  );
  test(
    'dismiss bypasses stalled startup and late preparation cannot play',
    () async {
      final runtime = TestRuntime()
        ..notificationGate = Completer<void>()
        ..preparationGate = Completer<void>();
      final event = AlertEvent(
        keyword: 'help',
        confidence: .99,
        timestamp: DateTime.now(),
        eventId: 'stalled',
      );
      final starting = runtime.startEmergency(event, AlertSound.values.first);
      await Future<void>.delayed(Duration.zero);
      await runtime.stopEmergency().timeout(const Duration(milliseconds: 100));
      expect(runtime.stops, 1);
      runtime.preparationGate!.complete();
      await starting;
      expect(runtime.audioStarts, 0);
      runtime.preparationGate = null;
      runtime.notificationGate = null;
      await runtime.startEmergency(event, AlertSound.values.first);
      expect(runtime.audioStarts, 1);
      runtime.playback.complete();
    },
  );
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
