import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:thermal_audio_monitor/models/training_keyword.dart';
import 'package:thermal_audio_monitor/models/training_statistics.dart';
import 'package:thermal_audio_monitor/providers/training_provider.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
      const MethodChannel('com.llfbandit.record/messages'),
      (MethodCall methodCall) async {
        return null;
      },
    );
  });

  group('TrainingProvider speaker ID & verification workflow', () {
    test('getNextSpeakerId auto-generates saklolo_01 when no recordings exist', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      final notifier = container.read(trainingProvider.notifier);
      expect(notifier.getNextSpeakerId('saklolo'), equals('saklolo_01'));
      expect(notifier.getNextSpeakerId('aray'), equals('aray_01'));
      expect(notifier.getNextSpeakerId('help me'), equals('help_me_01'));
    });

    test('getNextSpeakerId increments to highest existing number for that keyword', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      // Set up existing recordings in state
      final notifier = container.read(trainingProvider.notifier);
      container.read(trainingProvider.notifier).state = TrainingState(
        keywords: fallbackTrainingKeywords,
        recordings: [
          {'keyword': 'saklolo', 'speaker_id': 'saklolo_01'},
          {'keyword': 'saklolo', 'speaker_id': 'saklolo_02'},
          {'keyword': 'aray', 'speaker_id': 'aray_01'},
        ],
        statistics: const TrainingStatistics(
          totalRecordings: 3,
          byKeyword: {'saklolo': 2, 'aray': 1},
          bySpeaker: {'saklolo_01': 1, 'saklolo_02': 1, 'aray_01': 1},
          byAgeGroup: {'adult': 3},
        ),
      );

      // saklolo has 01 and 02 -> should return saklolo_03
      expect(notifier.getNextSpeakerId('saklolo'), equals('saklolo_03'));

      // aray has 01 -> should return aray_02
      expect(notifier.getNextSpeakerId('aray'), equals('aray_02'));

      // tulong has no recordings -> should return tulong_01
      expect(notifier.getNextSpeakerId('tulong'), equals('tulong_01'));
    });

    test('TrainingState.isRecorded reflects TrainingRecordingStatus.recorded', () {
      const state = TrainingState(
        recordingStatus: TrainingRecordingStatus.recorded,
      );
      expect(state.isRecorded, isTrue);
      expect(state.isRecording, isFalse);
      expect(state.isRecordingBusy, isFalse);
    });
  });
}
