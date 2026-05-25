import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/app_settings.dart';
import '../providers/settings_provider.dart';
import '../widgets/status_card.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

Future<void> _applyConnection(WidgetRef ref, {String? host, int? port}) async {
  final notifier = ref.read(settingsProvider.notifier);
  if (host != null) {
    await notifier.updateHost(host);
  }
  if (port != null) {
    await notifier.updatePort(port);
  }
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
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
    final settings = ref.watch(settingsProvider);
    if (_hostController.text != settings.host) {
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
          TextField(
            controller: _hostController,
            decoration: const InputDecoration(
              labelText: 'Pi IP or hostname',
              prefixIcon: Icon(Icons.lan_rounded),
              border: OutlineInputBorder(),
            ),
            onSubmitted: (value) => _applyConnection(ref, host: value),
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
            onSubmitted: (value) => _applyConnection(
              ref,
              port: int.tryParse(value) ?? AppSettings.defaultPort,
            ),
          ),
          const SizedBox(height: 12),
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
}
