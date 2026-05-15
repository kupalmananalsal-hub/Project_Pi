import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/noise_suppression_settings.dart';
import '../providers/audio_provider.dart';
import '../providers/noise_suppression_provider.dart';

class NoiseSuppressionPanel extends ConsumerWidget {
  const NoiseSuppressionPanel({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(noiseSuppressionProvider);
    final audio = ref.watch(audioProvider);
    final controller = ref.read(noiseSuppressionProvider.notifier);
    final settings = state.settings;
    final live = audio.latest;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    'Noise Suppression',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                ),
                if (state.loading || state.saving)
                  const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Active'),
              subtitle: const Text(
                'Turn filtering on or off without SSH or restarting the app.',
              ),
              value: settings.active,
              onChanged: state.isConnected
                  ? (value) {
                      controller.update(active: value);
                    }
                  : null,
            ),
            const SizedBox(height: 8),
            _LabeledSlider(
              label: 'Strength',
              value: settings.strength,
              leading: 'Light',
              trailing: 'Strong',
              onChanged: state.isConnected
                  ? (value) => controller.update(strength: value)
                  : null,
            ),
            const SizedBox(height: 12),
            _LabeledSlider(
              label: 'Sensitivity',
              value: settings.sensitivity,
              leading: 'Strict',
              trailing: 'Lenient',
              onChanged: state.isConnected
                  ? (value) => controller.update(sensitivity: value)
                  : null,
            ),
            const SizedBox(height: 16),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _MetricChip(
                  label: 'Current Noise Floor',
                  value:
                      '${(live?.noiseLevelDb ?? settings.noiseFloorDb).toStringAsFixed(1)} dB',
                ),
                _MetricChip(
                  label: 'Estimated SNR',
                  value:
                      '${(live?.snrDb ?? settings.snrEstimate).toStringAsFixed(1)} dB',
                ),
                _MetricChip(
                  label: 'Reduction',
                  value:
                      '${(live?.noiseReductionDb ?? settings.reductionDb).toStringAsFixed(1)} dB',
                ),
              ],
            ),
            const SizedBox(height: 16),
            Text('Presets', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final preset in NoiseSuppressionPreset.values)
                  FilledButton.tonal(
                    onPressed: state.isConnected
                        ? () => controller.applyPreset(preset)
                        : null,
                    child: Text(preset.label),
                  ),
              ],
            ),
            if (state.error != null) ...[
              const SizedBox(height: 12),
              Text(
                state.error!,
                style: Theme.of(
                  context,
                ).textTheme.bodyMedium?.copyWith(color: Colors.redAccent),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _LabeledSlider extends StatelessWidget {
  const _LabeledSlider({
    required this.label,
    required this.value,
    required this.leading,
    required this.trailing,
    required this.onChanged,
  });

  final String label;
  final double value;
  final String leading;
  final String trailing;
  final ValueChanged<double>? onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(child: Text(label)),
            Text('${(value * 100).round()}%'),
          ],
        ),
        Slider(value: value, onChanged: onChanged),
        Row(
          children: [
            Expanded(
              child: Text(
                leading,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ),
            Text(trailing, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ],
    );
  }
}

class _MetricChip extends StatelessWidget {
  const _MetricChip({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Chip(label: Text('$label: $value'));
  }
}
