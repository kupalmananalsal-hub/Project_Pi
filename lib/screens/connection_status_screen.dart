import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/app_settings.dart';
import '../providers/connection_provider.dart';
import '../providers/settings_provider.dart';
import '../services/pi_api_service.dart';
import '../widgets/connection_indicator.dart';
import '../widgets/status_card.dart';

class ConnectionStatusScreen extends ConsumerStatefulWidget {
  const ConnectionStatusScreen({super.key});

  @override
  ConsumerState<ConnectionStatusScreen> createState() =>
      _ConnectionStatusScreenState();
}

class _ConnectionStatusScreenState
    extends ConsumerState<ConnectionStatusScreen> {
  late final TextEditingController _hostController;
  late final TextEditingController _portController;

  @override
  void initState() {
    super.initState();
    _hostController = TextEditingController(text: AppSettings.defaultHost);
    _portController = TextEditingController(
      text: AppSettings.defaultPort.toString(),
    );
  }

  @override
  void dispose() {
    _hostController.dispose();
    _portController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(settingsProvider, (_, next) {
      if (_hostController.text != next.host) {
        _hostController.text = next.host;
      }
      final nextPort = next.port.toString();
      if (_portController.text != nextPort) {
        _portController.text = nextPort;
      }
    });

    final connection = ref.watch(connectionProvider);
    final status = connection.status;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                'Connection',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
            ),
            ConnectionIndicator(
              connected: connection.isConnected,
              connecting: connection.isConnecting,
            ),
          ],
        ),
        const SizedBox(height: 16),
        TextField(
          controller: _hostController,
          keyboardType: TextInputType.url,
          decoration: const InputDecoration(
            labelText: 'Pi IP or hostname',
            prefixIcon: Icon(Icons.lan_rounded),
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _portController,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            labelText: 'Port',
            prefixIcon: Icon(Icons.numbers_rounded),
            border: OutlineInputBorder(),
          ),
        ),
        const SizedBox(height: 14),
        Row(
          children: [
            Expanded(
              child: FilledButton.icon(
                onPressed: connection.isConnecting
                    ? null
                    : () {
                        ref
                            .read(connectionProvider.notifier)
                            .connect(
                              host: _hostController.text,
                              port:
                                  int.tryParse(_portController.text) ??
                                  AppSettings.defaultPort,
                            );
                      },
                icon: const Icon(Icons.link_rounded),
                label: const Text('Connect'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: OutlinedButton.icon(
                onPressed: connection.isConnected || connection.isConnecting
                    ? ref.read(connectionProvider.notifier).disconnect
                    : null,
                icon: const Icon(Icons.link_off_rounded),
                label: const Text('Disconnect'),
              ),
            ),
          ],
        ),
        if (connection.error != null) ...[
          const SizedBox(height: 14),
          MaterialBanner(
            padding: const EdgeInsets.all(12),
            leading: const Icon(Icons.info_outline_rounded),
            content: Text(connection.error!),
            actions: [
              TextButton(
                onPressed: () {
                  ref.read(connectionProvider.notifier).refreshStatus();
                },
                child: const Text('Refresh'),
              ),
            ],
          ),
        ],
        const SizedBox(height: 20),
        Text('System Status', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        StatusCard(
          title: 'CPU Temperature',
          value: status?.cpuTempC == null
              ? 'Unavailable'
              : '${status!.cpuTempC!.toStringAsFixed(1)} C',
          icon: Icons.device_thermostat_rounded,
          accentColor: Colors.deepOrangeAccent,
        ),
        StatusCard(
          title: 'RAM Usage',
          value: status?.ramUsagePercent == null
              ? 'Unavailable'
              : '${status!.ramUsagePercent!.toStringAsFixed(1)}%',
          icon: Icons.memory_rounded,
          accentColor: Colors.lightBlueAccent,
        ),
        StatusCard(
          title: 'Disk Usage',
          value: status?.diskUsagePercent == null
              ? 'Unavailable'
              : '${status!.diskUsagePercent!.toStringAsFixed(1)}%',
          icon: Icons.storage_rounded,
          accentColor: Colors.amberAccent,
        ),
        StatusCard(
          title: 'Uptime',
          value: status?.uptime ?? 'Unavailable',
          icon: Icons.schedule_rounded,
          accentColor: Colors.greenAccent,
          subtitle: connection.lastStatusAt == null
              ? null
              : 'Last checked ${_formatTime(connection.lastStatusAt!)}',
        ),
        StatusCard(
          title: 'I2C Devices',
          value: status?.i2cDevices.isEmpty ?? true
              ? 'No devices reported'
              : status!.i2cDevices.join(', '),
          icon: Icons.cable_rounded,
          accentColor: Colors.purpleAccent,
        ),
        StatusCard(
          title: 'Thermal Camera',
          value: status?.thermalAddress == null
              ? 'Unavailable'
              : '${status!.thermalAddress}'
                    '${status.thermalError == null ? ' ready' : ' error'}',
          icon: Icons.thermostat_rounded,
          accentColor: status?.thermalError == null
              ? Colors.greenAccent
              : Colors.redAccent,
          subtitle: status?.thermalError,
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: OutlinedButton.icon(
                onPressed: connection.isConnected
                    ? () => _confirmPowerAction(
                        context,
                        title: 'Restart Pi?',
                        message:
                            'The app will disconnect while the Pi restarts.',
                        successMessage: 'Restart command sent.',
                        action: () => PiApiService(
                          host: connection.host,
                          port: connection.port,
                        ).reboot(),
                      )
                    : null,
                icon: const Icon(Icons.restart_alt_rounded),
                label: const Text('Restart'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: FilledButton.icon(
                onPressed: connection.isConnected
                    ? () => _confirmPowerAction(
                        context,
                        title: 'Shutdown Pi?',
                        message:
                            'You will need physical access or power cycling to start it again.',
                        successMessage: 'Shutdown command sent.',
                        action: () => PiApiService(
                          host: connection.host,
                          port: connection.port,
                        ).shutdown(),
                      )
                    : null,
                icon: const Icon(Icons.power_settings_new_rounded),
                label: const Text('Shutdown'),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Future<void> _confirmPowerAction(
    BuildContext context, {
    required String title,
    required String message,
    required String successMessage,
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
      try {
        await action();
        if (context.mounted) {
          ScaffoldMessenger.of(
            context,
          ).showSnackBar(SnackBar(content: Text(successMessage)));
        }
      } catch (error) {
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('Power command failed: $error')),
          );
        }
      }
    }
  }

  String _formatTime(DateTime value) {
    final hour = value.hour.toString().padLeft(2, '0');
    final minute = value.minute.toString().padLeft(2, '0');
    final second = value.second.toString().padLeft(2, '0');
    return '$hour:$minute:$second';
  }
}
