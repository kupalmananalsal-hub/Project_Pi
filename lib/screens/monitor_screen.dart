import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/app_settings.dart';
import '../models/thermal_frame.dart';
import '../providers/connection_provider.dart';
import '../providers/monitor_provider.dart';
import '../providers/settings_provider.dart';
import '../providers/thermal_provider.dart';
import '../widgets/audio_meter.dart';
import '../widgets/connection_indicator.dart';
import '../widgets/direction_compass.dart';
import '../widgets/noise_suppression_panel.dart';
import '../widgets/status_card.dart';
import '../widgets/thermal_display.dart';

class MonitorScreen extends ConsumerWidget {
  const MonitorScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final monitor = ref.watch(monitorProvider);
    final thermal = ref.watch(thermalProvider);
    final audio = monitor.audioFrame;
    final connection = ref.watch(connectionProvider);

    return ListView(
      padding: const EdgeInsets.all(14),
      children: [
        _ConnectionStrip(connection: connection),
        const SizedBox(height: 10),
        _ThermalPanel(thermal: thermal),
        const SizedBox(height: 10),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Voice Monitor',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 12),
                AudioMeter(
                  label: 'Left Mic',
                  value: audio?.normalizedLeft ?? 0,
                  color: Colors.cyanAccent,
                ),
                const SizedBox(height: 14),
                AudioMeter(
                  label: 'Right Mic',
                  value: audio?.normalizedRight ?? 0,
                  color: Colors.orangeAccent,
                ),
                const SizedBox(height: 14),
                LayoutBuilder(
                  builder: (context, constraints) {
                    final wide = constraints.maxWidth > 420;
                    final compass = DirectionCompass(
                      direction: monitor.direction,
                      size: wide ? 190 : 170,
                    );
                    final facts = _VoiceFacts(
                      directionLabel: monitor.direction.label,
                      distanceMeters: monitor.direction.distanceMeters,
                      noiseLevelDb: audio?.noiseLevelDb ?? -90,
                      snrDb: audio?.snrDb ?? 0,
                      audioSocketStatus: monitor.audioSocketStatus,
                    );
                    if (wide) {
                      return Row(
                        children: [
                          compass,
                          const SizedBox(width: 16),
                          Expanded(child: facts),
                        ],
                      );
                    }
                    return Column(children: [compass, facts]);
                  },
                ),
                const SizedBox(height: 12),
                SizedBox(
                  height: 130,
                  child: AudioHistoryChart(history: monitor.audioHistory),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 10),
        const NoiseSuppressionPanel(),
      ],
    );
  }
}

class _ConnectionStrip extends ConsumerWidget {
  const _ConnectionStrip({required this.connection});

  final PiConnectionState connection;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final settings = ref.watch(settingsProvider);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Monitor',
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Pi ${connection.host}:${connection.port}',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ],
              ),
            ),
            ConnectionIndicator(
              connected: connection.isConnected,
              connecting: connection.isConnecting,
            ),
            const SizedBox(width: 8),
            FilledButton.tonalIcon(
              onPressed: connection.isConnecting
                  ? null
                  : connection.isConnected
                  ? ref.read(connectionProvider.notifier).disconnect
                  : () {
                      ref
                          .read(connectionProvider.notifier)
                          .connect(host: settings.host, port: settings.port);
                    },
              icon: Icon(
                connection.isConnected
                    ? Icons.link_off_rounded
                    : Icons.link_rounded,
              ),
              label: Text(connection.isConnected ? 'Disconnect' : 'Connect'),
            ),
          ],
        ),
      ),
    );
  }
}

class _ThermalPanel extends ConsumerWidget {
  const _ThermalPanel({required this.thermal});

  final ThermalState thermal;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Thermal Camera',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                ),
                DropdownButton<ThermalColorMap>(
                  value: thermal.colorMap,
                  items: [
                    for (final map in ThermalColorMap.values)
                      DropdownMenuItem(value: map, child: Text(map.label)),
                  ],
                  onChanged: (value) {
                    if (value != null) {
                      ref.read(thermalProvider.notifier).setColorMap(value);
                    }
                  },
                ),
              ],
            ),
            const SizedBox(height: 10),
            ThermalDisplay(
              frame: thermal.frame,
              colorMap: thermal.colorMap,
              minTemp: thermal.displayMinTemp,
              maxTemp: thermal.displayMaxTemp,
              selectedX: thermal.selectedX,
              selectedY: thermal.selectedY,
              onPixelSelected: ref.read(thermalProvider.notifier).selectPixel,
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                Chip(
                  avatar: const Icon(Icons.device_thermostat_rounded),
                  label: Text(
                    '${thermal.displayMinTemp.toStringAsFixed(1)} C - '
                    '${thermal.displayMaxTemp.toStringAsFixed(1)} C',
                  ),
                ),
                Chip(
                  avatar: Icon(
                    thermal.humanDetected
                        ? Icons.accessibility_new_rounded
                        : Icons.radio_button_checked_rounded,
                  ),
                  label: Text(
                    thermal.humanDetected
                        ? '${thermal.humanDetection.detectedPartLabel} '
                              '${(thermal.humanDetection.bodyCoverage * 100).toStringAsFixed(1)}%'
                        : 'Monitoring',
                  ),
                ),
                Chip(
                  avatar: const Icon(Icons.speed_rounded),
                  label: Text('${thermal.fps.toStringAsFixed(0)} fps'),
                ),
              ],
            ),
            if (thermal.selectedTemperature != null) ...[
              const SizedBox(height: 8),
              StatusCard(
                title: 'Selected Pixel',
                value:
                    '${thermal.selectedTemperature!.toStringAsFixed(2)} C '
                    'at ${thermal.selectedX},${thermal.selectedY}',
                icon: Icons.ads_click_rounded,
                accentColor: Colors.greenAccent,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _VoiceFacts extends StatelessWidget {
  const _VoiceFacts({
    required this.directionLabel,
    required this.distanceMeters,
    required this.noiseLevelDb,
    required this.snrDb,
    required this.audioSocketStatus,
  });

  final String directionLabel;
  final double? distanceMeters;
  final double noiseLevelDb;
  final double snrDb;
  final String audioSocketStatus;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        Chip(
          avatar: const Icon(Icons.explore_rounded),
          label: Text('Direction $directionLabel'),
        ),
        Chip(
          avatar: const Icon(Icons.social_distance_rounded),
          label: Text(
            distanceMeters == null
                ? 'Distance unknown'
                : 'Distance ~${distanceMeters!.toStringAsFixed(1)}m',
          ),
        ),
        Chip(
          avatar: const Icon(Icons.graphic_eq_rounded),
          label: Text('Noise ${noiseLevelDb.toStringAsFixed(1)} dB'),
        ),
        Chip(
          avatar: const Icon(Icons.tune_rounded),
          label: Text('SNR ${snrDb.toStringAsFixed(1)} dB'),
        ),
        Chip(
          avatar: const Icon(Icons.sensors_rounded),
          label: Text('Audio $audioSocketStatus'),
        ),
      ],
    );
  }
}
