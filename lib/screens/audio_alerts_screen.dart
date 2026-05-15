import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/alerts_provider.dart';
import '../providers/audio_provider.dart';
import '../providers/connection_provider.dart';
import '../services/pi_api_service.dart';
import '../widgets/audio_meter.dart';
import '../widgets/status_card.dart';

class AudioAlertsScreen extends ConsumerWidget {
  const AudioAlertsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final audio = ref.watch(audioProvider);
    final alerts = ref.watch(alertsProvider);
    final connection = ref.watch(connectionProvider);
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
                const SizedBox(height: 12),
                DirectionIndicator(direction: latest?.direction ?? 'center'),
                const SizedBox(height: 12),
                NoiseLevelSummary(
                  noiseLevelDb: latest?.noiseLevelDb ?? -90,
                  snrDb: latest?.snrDb ?? 0,
                  suppressionActive: latest?.noiseSuppressionActive ?? false,
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
        FilledButton.icon(
          onPressed: connection.isConnected
              ? () async {
                  try {
                    await PiApiService(
                      host: connection.host,
                      port: connection.port,
                    ).postAlert(keyword: 'tulong');
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Test alert sent')),
                      );
                    }
                  } catch (error) {
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text('Test alert failed: $error')),
                      );
                    }
                  }
                }
              : null,
          icon: const Icon(Icons.notification_add_rounded),
          label: const Text('Send Test Alert'),
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
                title: Text(event.displayKeyword),
                subtitle: Text(
                  '${_formatTimestamp(event.timestamp)} - '
                  'voice ${event.directionLabel.toLowerCase()} - '
                  '${event.detectedPartLabel.toLowerCase()}',
                ),
                trailing: Text('${(event.displayedConfidence * 100).round()}%'),
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
