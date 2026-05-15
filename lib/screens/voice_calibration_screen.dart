import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/voice_calibration_provider.dart';

class VoiceCalibrationScreen extends ConsumerWidget {
  const VoiceCalibrationScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(voiceCalibrationProvider);
    final controller = ref.read(voiceCalibrationProvider.notifier);
    final recommendation = state.recommendation;

    return Scaffold(
      appBar: AppBar(title: const Text('Voice Calibration')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            'Tap Start Calibration and say "tulong" or "help" toward the Pi three times in your normal voice.',
            style: Theme.of(context).textTheme.bodyLarge,
          ),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: state.running ? null : controller.startCalibration,
            icon: const Icon(Icons.mic_rounded),
            label: Text(state.running ? 'Calibrating...' : 'Start Calibration'),
          ),
          const SizedBox(height: 16),
          for (var index = 0; index < 3; index++)
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(
                state.sampleComplete[index]
                    ? Icons.check_circle_rounded
                    : state.running && state.currentSample == index + 1
                    ? Icons.graphic_eq_rounded
                    : Icons.radio_button_unchecked_rounded,
                color: state.sampleComplete[index] ? Colors.greenAccent : null,
              ),
              title: Text('Sample ${index + 1}'),
              subtitle: Text(
                state.sampleComplete[index]
                    ? 'Recorded'
                    : state.running && state.currentSample == index + 1
                    ? 'Recording... speak now'
                    : 'Waiting',
              ),
            ),
          if (recommendation != null) ...[
            const SizedBox(height: 16),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Voice Profile Detected',
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                    const SizedBox(height: 12),
                    Text('Pitch Range: ${recommendation.pitchLabel}'),
                    Text('Volume: ${recommendation.volumeLabel}'),
                    Text('Clarity: ${recommendation.clarityLabel}'),
                    const SizedBox(height: 16),
                    Text(
                      'Recommended Settings',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'Strength: ${recommendation.strength.toStringAsFixed(2)}',
                    ),
                    Text(
                      'Sensitivity: ${recommendation.sensitivity.toStringAsFixed(2)}',
                    ),
                    Text(
                      'Snowboy Sensitivity: ${recommendation.snowboySensitivity.toStringAsFixed(2)}',
                    ),
                    const SizedBox(height: 16),
                    FilledButton.icon(
                      onPressed: controller.applyRecommendation,
                      icon: const Icon(Icons.tune_rounded),
                      label: const Text('Apply Settings'),
                    ),
                  ],
                ),
              ),
            ),
          ],
          if (state.error != null) ...[
            const SizedBox(height: 12),
            Text(
              state.error!,
              style: Theme.of(
                context,
              ).textTheme.bodyMedium?.copyWith(color: Colors.redAccent),
            ),
          ],
        ],
      ),
    );
  }
}
