import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/audio_frame.dart';
import '../models/thermal_frame.dart';
import '../models/voice_direction.dart';
import '../providers/alerts_provider.dart';
import '../providers/connection_provider.dart';
import '../providers/monitor_provider.dart';
import '../providers/thermal_provider.dart';
import '../widgets/app_page.dart';
import '../widgets/connection_indicator.dart';
import '../widgets/radar_compass.dart';
import '../widgets/thermal_display.dart';

class MonitorScreen extends ConsumerWidget {
  const MonitorScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final monitor = ref.watch(monitorProvider);
    final thermal = ref.watch(thermalProvider);
    final alerts = ref.watch(alertsProvider);
    final connection = ref.watch(connectionProvider);
    final colors = Theme.of(context).colorScheme;
    final audioAvailable =
        monitor.audioFrame != null &&
        monitor.audioFrame!.error == null &&
        !monitor.audioFrame!.remoteMicrophoneMuted &&
        monitor.audioSocketStatus == 'connected';
    final direction = _DirectionCard(
      direction:
          (monitor.audioFrame?.error != null ||
                  monitor.audioFrame?.remoteMicrophoneMuted == true) &&
              alerts.keywordNotice == null
          ? const VoiceDirection.unknown()
          : monitor.direction,
      keywordSpotted: alerts.keywordNotice != null,
      onDismissKeyword: () =>
          ref.read(alertsProvider.notifier).dismissKeywordNotice(),
      thermalSoftAlert: alerts.thermalSoftAlert,
      audioAvailable: audioAvailable,
    );
    final thermalCard = _ThermalCard(thermal: thermal);
    return AppPage(
      children: [
        Text(
          'Monitor',
          style: Theme.of(
            context,
          ).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 4),
        Text(
          'Thermal and acoustic overview',
          style: TextStyle(color: colors.onSurfaceVariant),
        ),
        const SizedBox(height: 20),
        _Panel(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              ConnectionIndicator(
                connected: connection.isConnected,
                connecting: connection.isConnecting,
              ),
              const SizedBox(height: 8),
              Text(
                connection.isConnecting
                    ? 'Connecting to the Pi. Waiting for live streams.'
                    : connection.isConnected
                    ? 'Pi status connected. Stream availability is shown below.'
                    : 'Connect to the Pi in Settings to receive live monitoring.',
                style: TextStyle(color: colors.onSurfaceVariant),
              ),
              if (connection.error != null) ...[
                const SizedBox(height: 8),
                Text(connection.error!, style: TextStyle(color: colors.error)),
              ],
            ],
          ),
        ),
        LayoutBuilder(
          builder: (context, constraints) {
            if (constraints.maxWidth >= 720) {
              return Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(flex: 6, child: thermalCard),
                  const SizedBox(width: 16),
                  Expanded(
                    flex: 5,
                    child: Column(
                      children: [
                        direction,
                        _MicrophoneCard(
                          audio: monitor.audioFrame,
                          socketStatus: monitor.audioSocketStatus,
                        ),
                      ],
                    ),
                  ),
                ],
              );
            }
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                direction,
                thermalCard,
                _MicrophoneCard(
                  audio: monitor.audioFrame,
                  socketStatus: monitor.audioSocketStatus,
                ),
              ],
            );
          },
        ),
      ],
    );
  }
}

class _Panel extends StatelessWidget {
  const _Panel({required this.child});
  final Widget child;
  @override
  Widget build(BuildContext context) => Card(
    child: Padding(padding: const EdgeInsets.all(20), child: child),
  );
}

class _DirectionCard extends StatelessWidget {
  const _DirectionCard({
    required this.direction,
    required this.keywordSpotted,
    required this.onDismissKeyword,
    required this.thermalSoftAlert,
    required this.audioAvailable,
  });
  final VoiceDirection direction;
  final bool keywordSpotted;
  final VoidCallback onDismissKeyword;
  final bool thermalSoftAlert;
  final bool audioAvailable;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final description = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _SectionTitle('DIRECTION'),
        const SizedBox(height: 14),
        _Badge(
          label: keywordSpotted
              ? 'Keyword Spotted!'
              : audioAvailable
              ? 'LISTENING'
              : 'WAITING FOR AUDIO',
          icon: keywordSpotted
              ? Icons.hearing_rounded
              : Icons.graphic_eq_rounded,
          color: keywordSpotted
              ? Colors.amber.shade200
              : colors.onSurfaceVariant,
        ),
        const SizedBox(height: 12),
        Text(
          'Voice direction',
          style: TextStyle(color: colors.onSurfaceVariant),
        ),
        if (thermalSoftAlert) ...[
          const SizedBox(height: 12),
          const _Badge(
            label: 'Thermal presence detected',
            icon: Icons.thermostat_rounded,
            color: Color(0xFFFFD180),
          ),
        ],
      ],
    );
    return _Panel(
      child: LayoutBuilder(
        builder: (context, constraints) {
          final radar = Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (keywordSpotted)
                TextButton(
                  onPressed: onDismissKeyword,
                  child: const Text(
                    'KEYWORD SPOTTED!',
                    style: TextStyle(
                      color: Colors.amber,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                ),
              RadarCompass(
                direction: direction,
                size: constraints.maxWidth < 400 ? 148 : 200,
              ),
            ],
          );
          if (constraints.maxWidth < 290 ||
              MediaQuery.textScalerOf(context).scale(1) > 1.3) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                description,
                const SizedBox(height: 16),
                Center(child: radar),
              ],
            );
          }
          return Row(
            children: [
              Expanded(child: description),
              const SizedBox(width: 12),
              radar,
            ],
          );
        },
      ),
    );
  }
}

class _ThermalCard extends ConsumerWidget {
  const _ThermalCard({required this.thermal});
  final ThermalState thermal;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = Theme.of(context).colorScheme;
    final frame = thermal.frame;
    final live =
        frame != null &&
        thermal.error == null &&
        thermal.socketStatus.name == 'connected';
    final min = thermal.displayMinTemp;
    final max = thermal.displayMaxTemp;
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const _SectionTitle('THERMAL'),
          const SizedBox(height: 10),
          Wrap(
            spacing: 12,
            runSpacing: 8,
            alignment: WrapAlignment.spaceBetween,
            children: [
              Text(
                'MLX90640 · ${frame?.width ?? 32}×${frame?.height ?? 24}',
                style: TextStyle(color: colors.onSurfaceVariant),
              ),
              _Badge(
                label: thermal.error != null
                    ? 'Sensor unavailable'
                    : !live
                    ? 'No live stream'
                    : thermal.humanDetected
                    ? 'Human present'
                    : 'Scanning',
                icon: !live ? Icons.sensors_off_rounded : Icons.sensors_rounded,
                color: live ? colors.primary : colors.onSurfaceVariant,
              ),
            ],
          ),
          const SizedBox(height: 16),
          ThermalDisplay(
            frame: frame,
            colorMap: thermal.colorMap,
            minTemp: min,
            maxTemp: max,
            selectedX: thermal.selectedX,
            selectedY: thermal.selectedY,
            onPixelSelected: ref.read(thermalProvider.notifier).selectPixel,
          ),
          const SizedBox(height: 12),
          Column(
            children: [
              Container(
                height: 8,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(4),
                  gradient: LinearGradient(
                    colors: List.generate(
                      12,
                      (i) => thermalColorForValue(
                        min + (max - min) * i / 11,
                        min,
                        max,
                        thermal.colorMap,
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '${min.toStringAsFixed(1)}°C',
                      style: Theme.of(context).textTheme.labelMedium,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      '${max.toStringAsFixed(1)}°C',
                      textAlign: TextAlign.right,
                      style: Theme.of(context).textTheme.labelMedium,
                    ),
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 18),
          Wrap(
            spacing: 24,
            runSpacing: 12,
            children: [
              _Reading(
                label: 'COVERAGE',
                value: live
                    ? '${(thermal.humanDetection.bodyCoverage * 100).toStringAsFixed(1)}%'
                    : '—',
              ),
              _Reading(
                label: 'BOOST',
                value: live
                    ? '${thermal.humanDetection.confidenceBoost >= 0 ? '+' : ''}${thermal.humanDetection.confidenceBoost.toStringAsFixed(2)}'
                    : '—',
              ),
              if (thermal.selectedTemperature != null)
                _Reading(
                  label: live ? 'SELECTED PIXEL' : 'LAST SELECTED PIXEL',
                  value: '${thermal.selectedTemperature!.toStringAsFixed(1)}°C',
                ),
            ],
          ),
          if (!live) ...[
            const SizedBox(height: 14),
            Text(
              frame != null && thermal.error != null
                  ? 'Thermal sensor unavailable. Showing the last received frame.'
                  : frame == null
                  ? 'Waiting for thermal stream'
                  : 'Stream disconnected. Showing the last received frame.',
              style: TextStyle(color: colors.onSurfaceVariant),
            ),
          ],
          if (thermal.error != null) ...[
            const SizedBox(height: 10),
            Text(thermal.error!, style: TextStyle(color: colors.error)),
          ],
        ],
      ),
    );
  }
}

class _MicrophoneCard extends StatelessWidget {
  const _MicrophoneCard({required this.audio, required this.socketStatus});
  final AudioFrame? audio;
  final String socketStatus;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final live =
        audio != null &&
        audio!.error == null &&
        !audio!.remoteMicrophoneMuted &&
        socketStatus == 'connected';
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const _SectionTitle('MICROPHONES'),
          const SizedBox(height: 8),
          Text(
            audio?.remoteMicrophoneMuted == true
                ? 'Acoustic input withheld in this frame — not audio evidence'
                : audio?.error != null
                ? 'Microphone unavailable'
                : live
                ? 'Live input levels'
                : socketStatus == 'connecting'
                ? 'Connecting to audio stream…'
                : 'Waiting for microphone stream',
            style: TextStyle(color: colors.onSurfaceVariant),
          ),
          const SizedBox(height: 20),
          _MicLevel(label: 'MIC L', value: live ? audio!.normalizedLeft : null),
          const SizedBox(height: 18),
          _MicLevel(
            label: 'MIC R',
            value: live ? audio!.normalizedRight : null,
          ),
          if (audio?.error != null) ...[
            const SizedBox(height: 12),
            Text(audio!.error!, style: TextStyle(color: colors.error)),
          ],
        ],
      ),
    );
  }
}

class _MicLevel extends StatelessWidget {
  const _MicLevel({required this.label, required this.value});
  final String label;
  final double? value;
  @override
  Widget build(BuildContext context) => Semantics(
    label:
        '$label ${value == null ? 'unavailable' : '${(value! * 100).round()} percent'}',
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(child: Text(label)),
            Text(value == null ? '—' : '${(value! * 100).round()}%'),
          ],
        ),
        const SizedBox(height: 8),
        LinearProgressIndicator(
          value: value?.clamp(0, 1) ?? 0,
          minHeight: 8,
          borderRadius: BorderRadius.circular(4),
        ),
      ],
    ),
  );
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.label);
  final String label;
  @override
  Widget build(BuildContext context) => Text(
    label,
    style: Theme.of(context).textTheme.titleSmall?.copyWith(
      fontWeight: FontWeight.w700,
      letterSpacing: .8,
    ),
  );
}

class _Badge extends StatelessWidget {
  const _Badge({required this.label, required this.icon, required this.color});
  final String label;
  final IconData icon;
  final Color color;
  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Icon(icon, size: 18, color: color),
      const SizedBox(width: 6),
      Flexible(
        child: Text(
          label,
          style: Theme.of(context).textTheme.labelLarge?.copyWith(color: color),
        ),
      ),
    ],
  );
}

class _Reading extends StatelessWidget {
  const _Reading({required this.label, required this.value});
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(
        label,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
          color: Theme.of(context).colorScheme.onSurfaceVariant,
        ),
      ),
      const SizedBox(height: 6),
      Text(value, style: Theme.of(context).textTheme.titleMedium),
    ],
  );
}
