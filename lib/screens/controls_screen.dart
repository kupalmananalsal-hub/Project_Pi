import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/connection_provider.dart';
import '../providers/controls_provider.dart';
import '../widgets/led_control.dart';
import '../widgets/status_card.dart';

class ControlsScreen extends ConsumerWidget {
  const ControlsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final controls = ref.watch(controlsProvider);
    final connection = ref.watch(connectionProvider);
    final button = controls.buttonEvent;
    final status = connection.status;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Controls', style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 14),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'System Status',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    Chip(
                      avatar: const Icon(Icons.device_thermostat_rounded),
                      label: Text(
                        status?.cpuTempC == null
                            ? 'CPU unavailable'
                            : 'CPU ${status!.cpuTempC!.toStringAsFixed(1)} C',
                      ),
                    ),
                    Chip(
                      avatar: const Icon(Icons.memory_rounded),
                      label: Text(
                        status?.ramUsagePercent == null
                            ? 'RAM unavailable'
                            : 'RAM ${status!.ramUsagePercent!.toStringAsFixed(1)}%',
                      ),
                    ),
                    Chip(
                      avatar: const Icon(Icons.storage_rounded),
                      label: Text(
                        status?.diskUsagePercent == null
                            ? 'Disk unavailable'
                            : 'Disk ${status!.diskUsagePercent!.toStringAsFixed(1)}%',
                      ),
                    ),
                    Chip(
                      avatar: const Icon(Icons.schedule_rounded),
                      label: Text('Uptime ${status?.uptime ?? 'Unavailable'}'),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                StatusCard(
                  title: 'I2C Devices',
                  value: status?.i2cDevices.isEmpty ?? true
                      ? 'No devices reported'
                      : status!.i2cDevices.join(', '),
                  icon: Icons.cable_rounded,
                  accentColor: Colors.purpleAccent,
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: LedControl(
              selectedLed: controls.selectedLed,
              ledColors: controls.ledColors,
              brightness: controls.brightness,
              pattern: controls.pattern,
              onLedSelected: ref.read(controlsProvider.notifier).selectLed,
              onColorChanged: (color) {
                ref.read(controlsProvider.notifier).setLedColor(color);
              },
              onBrightnessChanged: (value) {
                ref.read(controlsProvider.notifier).setBrightness(value);
              },
              onPatternChanged: (pattern) {
                ref.read(controlsProvider.notifier).setPattern(pattern);
              },
            ),
          ),
        ),
        if (controls.error != null) ...[
          const SizedBox(height: 8),
          StatusCard(
            title: 'Control Error',
            value: controls.error!,
            icon: Icons.error_outline_rounded,
            accentColor: Colors.redAccent,
          ),
        ],
        const SizedBox(height: 12),
        StatusCard(
          title: 'User Button',
          value: button == null
              ? 'No button events'
              : button.pressed
              ? 'Pressed'
              : 'Released',
          icon: Icons.radio_button_checked_rounded,
          accentColor: button?.pressed ?? false
              ? Colors.greenAccent
              : Colors.blueGrey,
          subtitle: button?.lastPressedAt == null
              ? null
              : 'Last pressed ${_formatTimestamp(button!.lastPressedAt!)}',
        ),
        const SizedBox(height: 14),
        FilledButton.tonalIcon(
          onPressed: !connection.isConnected || controls.isBusy
              ? null
              : () => _confirm(
                  context,
                  title: 'Refresh keyword spotting?',
                  message:
                      'Reinstalls kws-alert.service from the repo and restarts the KWS service. Use this instead of SSH when detection needs a restart.',
                  action: () async {
                    final ok = await ref
                        .read(controlsProvider.notifier)
                        .refreshKws();
                    if (!context.mounted) {
                      return;
                    }
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(
                          ok
                              ? 'KWS service refreshed successfully.'
                              : ref.read(controlsProvider).error ??
                                    'Refresh failed.',
                        ),
                      ),
                    );
                  },
                ),
          icon: controls.isBusy
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.refresh_rounded),
          label: const Text('Refresh KWS Service'),
        ),
        const SizedBox(height: 10),
        OutlinedButton.icon(
          onPressed: !connection.isConnected || controls.isBusy
              ? null
              : () => _confirm(
                  context,
                  title: 'Pull code and refresh?',
                  message:
                      'Runs git pull on the Pi, updates kws-alert.service, and restarts keyword spotting. Requires git credentials on the Pi.',
                  action: () async {
                    final ok = await ref
                        .read(controlsProvider.notifier)
                        .refreshKws(gitPull: true);
                    if (!context.mounted) {
                      return;
                    }
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text(
                          ok
                              ? 'Code pulled and KWS refreshed.'
                              : ref.read(controlsProvider).error ??
                                    'Refresh failed.',
                        ),
                      ),
                    );
                  },
                ),
          icon: const Icon(Icons.cloud_download_rounded),
          label: const Text('Pull GitHub + Refresh KWS'),
        ),
        const SizedBox(height: 14),
        Row(
          children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: !connection.isConnected || controls.isBusy
                    ? null
                    : () => _confirm(
                        context,
                        title: 'Reboot Pi?',
                        message:
                            'The backend will disconnect while the Pi restarts.',
                        action: () =>
                            ref.read(controlsProvider.notifier).reboot(),
                      ),
                icon: const Icon(Icons.restart_alt_rounded),
                label: const Text('Reboot Pi'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: FilledButton.icon(
                style: FilledButton.styleFrom(
                  backgroundColor: Theme.of(context).colorScheme.error,
                ),
                onPressed: !connection.isConnected || controls.isBusy
                    ? null
                    : () => _confirm(
                        context,
                        title: 'Shutdown Pi?',
                        message:
                            'You will need physical access or power cycling to start it again.',
                        action: () =>
                            ref.read(controlsProvider.notifier).shutdown(),
                      ),
                icon: const Icon(Icons.power_settings_new_rounded),
                label: const Text('Shutdown'),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Future<void> _confirm(
    BuildContext context, {
    required String title,
    required String message,
    required Future<void> Function() action,
  }) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: Text(title),
          content: Text(message),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Confirm'),
            ),
          ],
        );
      },
    );
    if (confirmed == true) {
      await action();
    }
  }

  String _formatTimestamp(DateTime value) {
    final hour = value.hour.toString().padLeft(2, '0');
    final minute = value.minute.toString().padLeft(2, '0');
    final second = value.second.toString().padLeft(2, '0');
    return '$hour:$minute:$second';
  }
}
