import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/alerts_provider.dart';
import '../providers/connection_provider.dart';
import '../services/pi_api_service.dart';
import '../widgets/app_page.dart';

class HistoryScreen extends ConsumerWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final alerts = ref.watch(alertsProvider);
    final connection = ref.watch(connectionProvider);

    return AppPage(
      children: [
        Wrap(
          spacing: 16,
          runSpacing: 12,
          crossAxisAlignment: WrapCrossAlignment.center,
          alignment: WrapAlignment.spaceBetween,
          children: [
            Text(
              'History',
              style: Theme.of(
                context,
              ).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700),
            ),
            FilledButton.tonalIcon(
              onPressed: connection.isConnected
                  ? () => _confirmClearHistory(context, ref, connection)
                  : null,
              icon: const Icon(Icons.delete_sweep_rounded),
              label: const Text('Clear history'),
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
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 32),
                    child: Center(
                      child: Column(
                        children: [
                          Icon(
                            Icons.history_rounded,
                            size: 40,
                            color: Theme.of(
                              context,
                            ).colorScheme.onSurfaceVariant,
                          ),
                          const SizedBox(height: 16),
                          Text(
                            'No alerts yet',
                            style: Theme.of(context).textTheme.titleMedium,
                          ),
                          const SizedBox(height: 8),
                          Text(
                            'Received alerts will appear here.',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: Theme.of(
                                context,
                              ).colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ),
                    ),
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
                      title: Text(event.historyTitle),
                      subtitle: Text(
                        event.isResidentManual
                            ? _formatTimestamp(event.timestamp)
                            : '${_formatTimestamp(event.timestamp)} - '
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
          content: const Text(
            'This removes all stored alert records from the Pi.',
          ),
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
      final api = PiApiService(host: connection.host, port: connection.port);
      await api.clearAlerts();
      final refreshedHistory = await api.fetchAlerts();
      ref.read(alertsProvider.notifier).replaceHistory(refreshedHistory);
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Detection history cleared.')),
        );
      }
    } catch (error) {
      if (context.mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Clear history failed: $error')));
      }
    }
  }
}
