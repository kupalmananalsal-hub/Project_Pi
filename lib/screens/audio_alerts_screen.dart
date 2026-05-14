import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/alerts_provider.dart';
import '../providers/audio_provider.dart';
import '../widgets/audio_meter.dart';
import '../widgets/status_card.dart';

class AudioAlertsScreen extends ConsumerWidget {
  const AudioAlertsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final audio = ref.watch(audioProvider);
    final alerts = ref.watch(alertsProvider);
    final latest = audio.latest;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          'Audio and Alerts',
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const SizedBox(height: 14),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                AudioMeter(
                  label: 'Mic Left',
                  value: latest?.normalizedLeft ?? 0,
                  color: Colors.cyanAccent,
                ),
                const SizedBox(height: 18),
                AudioMeter(
                  label: 'Mic Right',
                  value: latest?.normalizedRight ?? 0,
                  color: Colors.orangeAccent,
                ),
                const SizedBox(height: 18),
                SizedBox(
                  height: 180,
                  child: AudioHistoryChart(history: audio.history),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        StatusCard(
          title: 'Audio Socket',
          value: audio.socketStatus.name,
          icon: Icons.graphic_eq_rounded,
          accentColor: Colors.cyanAccent,
        ),
        StatusCard(
          title: 'Alert Socket',
          value: alerts.socketStatus.name,
          icon: Icons.notification_important_rounded,
          accentColor: Colors.redAccent,
        ),
        const SizedBox(height: 10),
        Text('Keyword Log', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        if (alerts.history.isEmpty)
          const StatusCard(
            title: 'No alerts yet',
            value: 'Listening for Help and Tulong',
            icon: Icons.hearing_rounded,
          )
        else
          for (final event in alerts.history.take(12))
            Card(
              child: ListTile(
                leading: Icon(
                  event.isEmergencyKeyword
                      ? Icons.warning_rounded
                      : Icons.record_voice_over_rounded,
                  color: event.isEmergencyKeyword ? Colors.redAccent : null,
                ),
                title: Text(event.keyword.toUpperCase()),
                subtitle: Text(_formatTimestamp(event.timestamp)),
                trailing: Text('${(event.confidence * 100).round()}%'),
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
    final second = value.second.toString().padLeft(2, '0');
    return '$month/$day $hour:$minute:$second';
  }
}
