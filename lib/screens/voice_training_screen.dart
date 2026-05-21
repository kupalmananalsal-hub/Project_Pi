import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/connection_provider.dart';
import '../providers/voice_training_provider.dart';
import '../widgets/audio_recorder_widget.dart';
import '../widgets/status_card.dart';

class VoiceTrainingScreen extends ConsumerStatefulWidget {
  const VoiceTrainingScreen({super.key});

  @override
  ConsumerState<VoiceTrainingScreen> createState() =>
      _VoiceTrainingScreenState();
}

class _VoiceTrainingScreenState extends ConsumerState<VoiceTrainingScreen> {
  late final TextEditingController _speakerController;

  @override
  void initState() {
    super.initState();
    _speakerController = TextEditingController(text: 'mobile_user');
  }

  @override
  void dispose() {
    _speakerController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(voiceTrainingProvider);
    final controller = ref.read(voiceTrainingProvider.notifier);
    final connection = ref.watch(connectionProvider);

    if (_speakerController.text != state.speakerName) {
      _speakerController.text = state.speakerName;
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Voice Training')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(
                value: 'tulong',
                label: Text('Tulong'),
                icon: Icon(Icons.record_voice_over_rounded),
              ),
              ButtonSegment(
                value: 'help',
                label: Text('Help'),
                icon: Icon(Icons.hearing_rounded),
              ),
            ],
            selected: {state.keyword},
            onSelectionChanged: (values) {
              controller.setKeyword(values.first);
            },
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _speakerController,
            decoration: const InputDecoration(
              labelText: 'Speaker name',
              prefixIcon: Icon(Icons.person_rounded),
              border: OutlineInputBorder(),
            ),
            onChanged: controller.setSpeakerName,
          ),
          const SizedBox(height: 12),
          AudioRecorderWidget(
            keyword: state.keyword,
            recording: state.recording,
            uploading: state.uploading,
            waveform: state.waveform,
            hasRecording: state.localRecordingPath != null,
            onRecord: connection.isConnected ? controller.startRecording : null,
            onStop: controller.stopRecording,
            onUpload: controller.uploadRecording,
          ),
          if (!connection.isConnected)
            const StatusCard(
              title: 'Pi connection',
              value: 'Connect to the Pi before recording samples',
              icon: Icons.link_off_rounded,
            ),
          if (state.message != null)
            StatusCard(
              title: 'Voice sample',
              value: state.message!,
              icon: Icons.check_circle_rounded,
              accentColor: Colors.greenAccent,
            ),
          if (state.error != null)
            StatusCard(
              title: 'Voice training error',
              value: state.error!,
              icon: Icons.error_outline_rounded,
              accentColor: Colors.redAccent,
            ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: StatusCard(
                  title: 'Tulong Samples',
                  value: '${state.stats.tulongSamples}/3',
                  icon: Icons.translate_rounded,
                  accentColor: state.stats.tulongSamples >= 3
                      ? Colors.greenAccent
                      : Colors.amberAccent,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: StatusCard(
                  title: 'Help Samples',
                  value: '${state.stats.helpSamples}/3',
                  icon: Icons.hearing_rounded,
                  accentColor: state.stats.helpSamples >= 3
                      ? Colors.greenAccent
                      : Colors.amberAccent,
                ),
              ),
            ],
          ),
          FilledButton.tonalIcon(
            onPressed: state.loading ? null : controller.refresh,
            icon: state.loading
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.refresh_rounded),
            label: const Text('Refresh samples'),
          ),
          const SizedBox(height: 10),
          FilledButton.icon(
            onPressed: state.calibrating
                ? null
                : controller.calibrateFromSamples,
            icon: state.calibrating
                ? const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.tune_rounded),
            label: const Text('Calibrate from samples'),
          ),
          if (state.calibration != null) ...[
            const SizedBox(height: 12),
            StatusCard(
              title: 'Calibration Result',
              value:
                  'Strength ${state.calibration!.noiseSuppressionStrength.toStringAsFixed(2)}, '
                  'Sensitivity ${state.calibration!.noiseSuppressionSensitivity.toStringAsFixed(2)}, '
                  'Snowboy ${state.calibration!.snowboySensitivity.toStringAsFixed(2)}',
              icon: Icons.settings_voice_rounded,
              accentColor: Colors.lightBlueAccent,
              subtitle:
                  '${state.calibration!.samplesAnalyzed} samples analyzed, '
                  'clarity ${(state.calibration!.clarityScore * 100).round()}%',
            ),
          ],
          const SizedBox(height: 16),
          Text(
            'Previous Recordings',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 8),
          if (state.samples.isEmpty)
            const StatusCard(
              title: 'No samples yet',
              value: 'Record and send at least 3 samples per keyword',
              icon: Icons.mic_none_rounded,
            )
          else
            for (final sample in state.samples.reversed.take(10))
              Card(
                child: ListTile(
                  leading: const Icon(Icons.audio_file_rounded),
                  title: Text('${sample.keyword} - ${sample.speakerName}'),
                  subtitle: Text(
                    '${sample.durationSeconds.toStringAsFixed(1)}s, '
                    '${sample.sampleRate} Hz, ${sample.channels} ch',
                  ),
                  trailing: Text(
                    sample.timestamp.hour.toString().padLeft(2, '0'),
                  ),
                ),
              ),
        ],
      ),
    );
  }
}
