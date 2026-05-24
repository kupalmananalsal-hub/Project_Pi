import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/alerts_provider.dart';
import '../providers/connection_provider.dart';
import '../services/pi_api_service.dart';
import '../widgets/status_card.dart';

class HistoryScreen extends ConsumerWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final alerts = ref.watch(alertsProvider);
    final connection = ref.watch(connectionProvider);

    return ListView(
      padding: const EdgeInsets.all(14),
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                'History',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
            ),
            FilledButton.tonalIcon(
              onPressed: alerts.history.isEmpty
                  ? null
                  : () => _confirmClearHistory(context, ref, connection),
              icon: const Icon(Icons.delete_sweep_rounded),
              label: const Text('Clear Detection History'),
            ),
          ],
        ),
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

  Future<void> _confirmClearHistory(
    BuildContext context,
    WidgetRef ref,
    PiConnectionState connection,
  ) async {
    if (!connection.isConnected) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Connect to the Pi before clearing history.'),
        ),
      );
      return;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Clear detection history?'),
          content: const Text('This removes all stored alert records from the Pi.'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Clear'),
            ),
          ],
        );
      },
    );

    if (confirmed != true) {
      return;
    }

    try {
      await PiApiService(
        host: connection.host,
        port: connection.port,
      ).clearAlerts();
      ref.read(alertsProvider.notifier).clearHistory();
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Detection history cleared.')),
        );
      }
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Clear history failed: $error')),
        );
      }
    }
  }
}
