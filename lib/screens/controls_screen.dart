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

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('Controls', style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 14),
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
