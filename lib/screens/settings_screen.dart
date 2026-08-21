import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/app_settings.dart';
import '../providers/connection_provider.dart';
import '../providers/settings_provider.dart';
import '../widgets/status_card.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  late final TextEditingController _hostController;
  late final TextEditingController _portController;
  late final FocusNode _hostFocusNode;

  @override
  void initState() {
    super.initState();
    _hostController = TextEditingController(text: AppSettings.defaultHost);
    _portController = TextEditingController(
      text: AppSettings.defaultPort.toString(),
    );
    _hostFocusNode = FocusNode();
  }

  @override
  void dispose() {
    _hostFocusNode.dispose();
    _hostController.dispose();
    _portController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final settings = ref.watch(settingsProvider);
    final connection = ref.watch(connectionProvider);
    if (!_hostFocusNode.hasFocus && _hostController.text != settings.host) {
      _hostController.text = settings.host;
    }
    final portText = settings.port.toString();
    if (_portController.text != portText) {
      _portController.text = portText;
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            'Raspberry Pi Connection',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 12),
          TextField(
            key: const ValueKey('pi-host-field'),
            controller: _hostController,
            focusNode: _hostFocusNode,
            keyboardType: TextInputType.url,
            decoration: const InputDecoration(
              labelText: 'Pi IP / Hostname',
              prefixIcon: Icon(Icons.lan_rounded),
              border: OutlineInputBorder(),
            ),
            onSubmitted: (_) => _connect(context),
          ),
          const SizedBox(height: 12),
          TextField(
            key: const ValueKey('pi-port-field'),
            controller: _portController,
            readOnly: true,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(
              labelText: 'Port',
              prefixIcon: Icon(Icons.numbers_rounded),
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          _ConnectionStatusRow(connection: connection),
          if (connection.error != null) ...[
            const SizedBox(height: 8),
            Text(
              connection.error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: connection.isConnected
                ? OutlinedButton.icon(
                    key: const ValueKey('pi-disconnect-button'),
                    onPressed: _disconnect,
                    icon: const Icon(Icons.link_off_rounded),
                    label: const Text('Disconnect'),
                  )
                : FilledButton.icon(
                    key: const ValueKey('pi-connect-button'),
                    onPressed: connection.isConnecting
                        ? null
                        : () => _connect(context),
                    icon: const Icon(Icons.link_rounded),
                    label: Text(
                      connection.isConnecting ? 'Connecting...' : 'Connect',
                    ),
                  ),
          ),
          const SizedBox(height: 28),
          DropdownButtonFormField<AlertSound>(
            initialValue: settings.alertSound,
            decoration: const InputDecoration(
              labelText: 'Alert sound',
              prefixIcon: Icon(Icons.volume_up_rounded),
              border: OutlineInputBorder(),
            ),
            items: [
              for (final sound in AlertSound.values)
                DropdownMenuItem(value: sound, child: Text(sound.label)),
            ],
            onChanged: (value) {
              if (value != null) {
                ref.read(settingsProvider.notifier).setAlertSound(value);
              }
            },
          ),
          const SizedBox(height: 8),
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            secondary: const Icon(Icons.dark_mode_rounded),
            title: const Text('Dark theme'),
            value: settings.darkMode,
            onChanged: (value) {
              ref.read(settingsProvider.notifier).setDarkMode(value);
            },
          ),
          const SizedBox(height: 18),
          StatusCard(
            title: 'Default Pi',
            value: '${AppSettings.defaultHost}:${AppSettings.defaultPort}',
            icon: Icons.router_rounded,
            accentColor: Colors.lightBlueAccent,
            subtitle:
                'Fallbacks: ${AppSettings.fallbackHost}, ${AppSettings.mdnsFallbackHost}',
          ),
          const StatusCard(
            title: 'About',
            value: 'Raspberry Pi 5 thermal and voice alert monitor',
            icon: Icons.info_outline_rounded,
            accentColor: Colors.greenAccent,
            subtitle:
                'MLX90640 thermal stream, ReSpeaker dual mic levels, keyword alerts, and Pi controls.',
          ),
        ],
      ),
    );
  }

  Future<void> _connect(BuildContext context) async {
    FocusScope.of(context).unfocus();
    final host = _hostController.text.trim();
    if (host.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Pi IP or hostname is required.')),
      );
      return;
    }
    await ref
        .read(connectionProvider.notifier)
        .connect(
          host: host,
          port: int.tryParse(_portController.text) ?? AppSettings.defaultPort,
        );
    if (!context.mounted) {
      return;
    }
    final connection = ref.read(connectionProvider);
    if (connection.connectionStatus == PiConnectionStatus.error &&
        connection.error != null) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(connection.error!)));
    }
  }

  void _disconnect() {
    ref.read(connectionProvider.notifier).disconnect();
  }

}

class _ConnectionStatusRow extends StatelessWidget {
  const _ConnectionStatusRow({required this.connection});

  final PiConnectionState connection;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final statusColor = switch (connection.connectionStatus) {
      PiConnectionStatus.connected => Colors.greenAccent,
      PiConnectionStatus.connecting => colorScheme.primary,
      PiConnectionStatus.error => colorScheme.error,
      PiConnectionStatus.disconnected => colorScheme.onSurfaceVariant,
    };

    return Row(
      children: [
        Text(
          'Connection Status:',
          style: Theme.of(context).textTheme.titleSmall,
        ),
        const SizedBox(width: 8),
        Icon(Icons.circle, size: 10, color: statusColor),
        const SizedBox(width: 8),
        Text(connection.connectionStatusLabel),
      ],
    );
  }
}
