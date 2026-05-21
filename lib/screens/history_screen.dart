import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/alerts_provider.dart';
import '../providers/voice_training_provider.dart';
import '../screens/voice_training_screen.dart';
import '../widgets/status_card.dart';

class HistoryScreen extends ConsumerWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final alerts = ref.watch(alertsProvider);
    final training = ref.watch(voiceTrainingProvider);
    final trainingController = ref.read(voiceTrainingProvider.notifier);

    return ListView(
      padding: const EdgeInsets.all(14),
      children: [
        Text('History', style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 12),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Recent Alerts',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 8),
                if (alerts.history.isEmpty)
                  const StatusCard(
                    title: 'No alerts yet',
                    value: 'Listening for tulong, help, and wake words',
                    icon: Icons.hearing_rounded,
                  )
                else
                  for (final event in alerts.history.take(12))
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: CircleAvatar(
                        backgroundColor: event.humanDetected
                            ? Colors.redAccent.withValues(alpha: 0.16)
                            : Colors.amberAccent.withValues(alpha: 0.16),
                        foregroundColor: event.humanDetected
                            ? Colors.redAccent
                            : Colors.amberAccent,
                        child: Icon(
                          event.humanDetected
                              ? Icons.warning_rounded
                              : Icons.report_gmailerrorred_rounded,
                        ),
                      ),
                      title: Text(
                        '${event.displayKeyword} - ${event.directionLabel}',
                      ),
                      subtitle: Text(
                        '${_formatTimestamp(event.timestamp)} - '
                        'confidence ${(event.displayedConfidence * 100).round()}% - '
                        'human ${event.humanDetected ? 'yes' : 'no'}',
                      ),
                    ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 10),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Voice Training',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 8),
                Text(
                  'Record new voice samples to improve detection accuracy.',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: FilledButton.tonalIcon(
                        onPressed: () {
                          trainingController.setKeyword('tulong');
                          Navigator.of(context).push(
                            MaterialPageRoute<void>(
                              builder: (_) => const VoiceTrainingScreen(),
                            ),
                          );
                        },
                        icon: const Icon(Icons.translate_rounded),
                        label: const Text('Record Tulong'),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: FilledButton.tonalIcon(
                        onPressed: () {
                          trainingController.setKeyword('help');
                          Navigator.of(context).push(
                            MaterialPageRoute<void>(
                              builder: (_) => const VoiceTrainingScreen(),
                            ),
                          );
                        },
                        icon: const Icon(Icons.hearing_rounded),
                        label: const Text('Record Help'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    Chip(
                      avatar: const Icon(Icons.translate_rounded),
                      label: Text('Tulong ${training.stats.tulongSamples}'),
                    ),
                    Chip(
                      avatar: const Icon(Icons.hearing_rounded),
                      label: Text('Help ${training.stats.helpSamples}'),
                    ),
                    Chip(
                      avatar: const Icon(Icons.people_alt_rounded),
                      label: Text(
                        '${training.stats.uniqueSpeakers} speaker profiles',
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  String _formatTimestamp(DateTime value) {
    final month = value.month.toString().padLeft(2, '0');
    final day = value.day.toString().padLeft(2, '0');
    final hour = value.hour.toString().padLeft(2, '0');
    final minute = value.minute.toString().padLeft(2, '0');
    return '$month/$day $hour:$minute';
  }
}
