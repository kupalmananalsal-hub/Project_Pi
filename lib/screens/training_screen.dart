import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/training_keyword.dart';
import '../providers/connection_provider.dart';
import '../providers/training_provider.dart';

/// Training data collection and pipeline management screen.
class TrainingScreen extends ConsumerStatefulWidget {
  const TrainingScreen({super.key});

  @override
  ConsumerState<TrainingScreen> createState() => _TrainingScreenState();
}

class _TrainingScreenState extends ConsumerState<TrainingScreen> {
  String? _selectedKeyword;
  final _speakerController = TextEditingController(text: 'speaker_01');
  final _distanceController = TextEditingController(text: '1.0');
  String _ageGroup = 'adult';
  String _gender = 'male';
  String _noiseCondition = 'quiet';

  @override
  void initState() {
    super.initState();
    Future.microtask(() {
      if (ref.read(connectionProvider).isConnected) {
        ref.read(trainingProvider.notifier).refresh();
      }
    });
  }

  @override
  void dispose() {
    _speakerController.dispose();
    _distanceController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final training = ref.watch(trainingProvider);
    final isConnected = ref.watch(
      connectionProvider.select((c) => c.isConnected),
    );
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    if (!isConnected) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off_rounded, size: 64, color: Colors.grey),
            SizedBox(height: 16),
            Text('Connect to Pi to access training'),
          ],
        ),
      );
    }

    if (!training.isLoading &&
        training.keywords.isEmpty &&
        training.statistics == null &&
        training.errorMessage == null) {
      Future.microtask(() => ref.read(trainingProvider.notifier).refresh());
    }

    return RefreshIndicator(
      onRefresh: () => ref.read(trainingProvider.notifier).refresh(),
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── Error Banner ──
          if (training.errorMessage != null)
            Card(
              color: colorScheme.errorContainer,
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Row(
                  children: [
                    Icon(Icons.error_outline, color: colorScheme.error),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        training.errorMessage!,
                        style: TextStyle(color: colorScheme.onErrorContainer),
                      ),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close),
                      onPressed: () =>
                          ref.read(trainingProvider.notifier).clearError(),
                    ),
                  ],
                ),
              ),
            ),

          // ── Loading Indicator ──
          if (training.isLoading) const LinearProgressIndicator(),

          // ── Dataset Overview ──
          _SectionHeader(
            title: 'Dataset Overview',
            icon: Icons.dataset_rounded,
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              _StatChip(
                label: 'Recordings',
                value: '${training.statistics?.totalRecordings ?? 0}',
                icon: Icons.mic,
              ),
              const SizedBox(width: 8),
              _StatChip(
                label: 'Speakers',
                value: '${training.statistics?.bySpeaker.length ?? 0}',
                icon: Icons.people,
              ),
              const SizedBox(width: 8),
              _StatChip(
                label: 'Keywords',
                value: '${training.keywords.length}',
                icon: Icons.label,
              ),
            ],
          ),
          const SizedBox(height: 16),

          // ── Keyword Grid ──
          if (training.keywords.isNotEmpty) ...[
            _SectionHeader(title: 'Keywords', icon: Icons.translate_rounded),
            const SizedBox(height: 8),
            _KeywordGrid(
              keywords: training.keywords,
              counts: training.statistics?.byKeyword ?? const {},
            ),
            const SizedBox(height: 16),
          ],

          // ── Record Section ──
          _SectionHeader(title: 'Record Sample', icon: Icons.mic_rounded),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  DropdownButtonFormField<String>(
                    initialValue: _selectedKeyword,
                    decoration: const InputDecoration(
                      labelText: 'Keyword',
                      helperText: 'Choose one of the 17 deployed keywords.',
                      border: OutlineInputBorder(),
                    ),
                    hint: Text(
                      training.isLoading && training.keywords.isEmpty
                          ? 'Loading keywords...'
                          : 'Select keyword',
                    ),
                    items: training.keywords
                        .map(
                          (kw) => DropdownMenuItem(
                            value: kw.keyword,
                            child: Text('${kw.keyword} (${kw.language})'),
                          ),
                        )
                        .toList(),
                    onChanged: training.keywords.isEmpty
                        ? null
                        : (v) => setState(() => _selectedKeyword = v),
                  ),
                  if (training.keywords.isEmpty && !training.isLoading) ...[
                    const SizedBox(height: 8),
                    OutlinedButton.icon(
                      onPressed: () =>
                          ref.read(trainingProvider.notifier).refresh(),
                      icon: const Icon(Icons.refresh_rounded),
                      label: const Text('Retry Loading Keywords'),
                    ),
                  ],
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: TextField(
                          controller: _speakerController,
                          decoration: const InputDecoration(
                            labelText: 'Speaker ID',
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: TextField(
                          controller: _distanceController,
                          keyboardType: TextInputType.number,
                          decoration: const InputDecoration(
                            labelText: 'Distance (m)',
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          initialValue: _ageGroup,
                          decoration: const InputDecoration(
                            labelText: 'Age Group',
                            border: OutlineInputBorder(),
                          ),
                          items: const [
                            DropdownMenuItem(
                              value: 'child',
                              child: Text('Child'),
                            ),
                            DropdownMenuItem(
                              value: 'teen',
                              child: Text('Teen'),
                            ),
                            DropdownMenuItem(
                              value: 'adult',
                              child: Text('Adult'),
                            ),
                            DropdownMenuItem(
                              value: 'elder',
                              child: Text('Elder'),
                            ),
                          ],
                          onChanged: (v) =>
                              setState(() => _ageGroup = v ?? 'adult'),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: DropdownButtonFormField<String>(
                          initialValue: _gender,
                          decoration: const InputDecoration(
                            labelText: 'Gender',
                            border: OutlineInputBorder(),
                          ),
                          items: const [
                            DropdownMenuItem(
                              value: 'male',
                              child: Text('Male'),
                            ),
                            DropdownMenuItem(
                              value: 'female',
                              child: Text('Female'),
                            ),
                            DropdownMenuItem(
                              value: 'other',
                              child: Text('Other'),
                            ),
                          ],
                          onChanged: (v) =>
                              setState(() => _gender = v ?? 'male'),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    initialValue: _noiseCondition,
                    decoration: const InputDecoration(
                      labelText: 'Noise Condition',
                      border: OutlineInputBorder(),
                    ),
                    items: const [
                      DropdownMenuItem(value: 'quiet', child: Text('Quiet')),
                      DropdownMenuItem(value: 'normal', child: Text('Normal')),
                      DropdownMenuItem(value: 'noisy', child: Text('Noisy')),
                    ],
                    onChanged: (v) =>
                        setState(() => _noiseCondition = v ?? 'quiet'),
                  ),
                  const SizedBox(height: 16),
                  _RecordingStatusBanner(
                    status: training.recordingStatus,
                    elapsed: training.recordingElapsed,
                  ),
                  if (training.recordingStatus ==
                      TrainingRecordingStatus.error) ...[
                    const SizedBox(height: 8),
                    if (training.microphonePermissionDenied)
                      OutlinedButton.icon(
                        onPressed: () => ref
                            .read(trainingProvider.notifier)
                            .openMicrophoneSettings(),
                        icon: const Icon(Icons.settings_rounded),
                        label: const Text('Open App Settings'),
                      )
                    else
                      OutlinedButton.icon(
                        onPressed: training.isLoading
                            ? null
                            : () => ref
                                  .read(trainingProvider.notifier)
                                  .retryUpload(),
                        icon: const Icon(Icons.refresh_rounded),
                        label: const Text('Retry Upload'),
                      ),
                  ],
                  const SizedBox(height: 12),
                  FilledButton.icon(
                    onPressed: training.isRecordingBusy || training.isLoading
                        ? null
                        : () => _handleRecordButton(training),
                    icon: Icon(
                      training.isRecording
                          ? Icons.stop_circle_rounded
                          : Icons.mic_rounded,
                    ),
                    label: Text(switch (training.recordingStatus) {
                      TrainingRecordingStatus.recording => 'Stop and Upload',
                      TrainingRecordingStatus.stopping => 'Stopping...',
                      TrainingRecordingStatus.uploading => 'Uploading...',
                      _ => 'Record Sample',
                    }),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // ── Pipeline Actions ──
          _SectionHeader(
            title: 'Pipeline',
            icon: Icons.play_circle_outline_rounded,
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _PipelineButton(
                label: 'Validate',
                icon: Icons.check_circle_outline,
                color: Colors.blue,
                onPressed: training.isLoading
                    ? null
                    : () => ref
                          .read(trainingProvider.notifier)
                          .startJob('validation'),
              ),
              _PipelineButton(
                label: 'Augment',
                icon: Icons.auto_fix_high,
                color: Colors.purple,
                onPressed: training.isLoading
                    ? null
                    : () => ref
                          .read(trainingProvider.notifier)
                          .startJob('augmentation'),
              ),
              _PipelineButton(
                label: 'Export',
                icon: Icons.archive_outlined,
                color: Colors.teal,
                onPressed: training.isLoading
                    ? null
                    : () => ref
                          .read(trainingProvider.notifier)
                          .startJob('export'),
              ),
              _PipelineButton(
                label: 'Train',
                icon: Icons.model_training,
                color: Colors.orange,
                onPressed: training.isLoading
                    ? null
                    : () => ref
                          .read(trainingProvider.notifier)
                          .startJob('training'),
              ),
            ],
          ),
          const SizedBox(height: 16),

          // ── Active Job Status ──
          if (training.activeJob != null) ...[
            _SectionHeader(
              title: 'Job Status',
              icon: Icons.pending_actions_rounded,
            ),
            const SizedBox(height: 8),
            _JobStatusCard(job: training.activeJob!),
            const SizedBox(height: 16),
          ],

          // ── Speaker Distribution ──
          if (training.statistics != null &&
              training.statistics!.bySpeaker.isNotEmpty) ...[
            _SectionHeader(
              title: 'Speaker Distribution',
              icon: Icons.bar_chart_rounded,
            ),
            const SizedBox(height: 8),
            _DistributionCard(
              data: training.statistics!.bySpeaker,
              color: Colors.indigo,
            ),
          ],

          const SizedBox(height: 32),
        ],
      ),
    );
  }

  Future<void> _handleRecordButton(TrainingState training) async {
    final notifier = ref.read(trainingProvider.notifier);
    if (training.isRecording) {
      final upload = _currentUploadRequest();
      if (upload == null) return;
      final uploaded = await notifier.stopRecordingAndUpload(
        keyword: upload.keyword,
        speakerId: upload.speakerId,
        ageGroup: upload.ageGroup,
        gender: upload.gender,
        distanceM: upload.distanceM,
        noiseCondition: upload.noiseCondition,
      );
      if (!mounted) return;
      final errorMessage = ref.read(trainingProvider).errorMessage;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            uploaded
                ? 'Recording uploaded.'
                : errorMessage ??
                      'Upload failed. Check the Pi backend and try again.',
          ),
        ),
      );
      return;
    }

    final upload = _currentUploadRequest();
    if (upload == null) return;
    final started = await notifier.startRecording();
    if (!mounted || started) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Could not start microphone recording.')),
    );
  }

  TrainingRecordingUpload? _currentUploadRequest() {
    final keyword = _selectedKeyword;
    if (keyword == null || keyword.isEmpty) {
      _showFormError('Select a keyword before recording.');
      return null;
    }
    final speakerId = _speakerController.text.trim();
    if (speakerId.isEmpty) {
      _showFormError('Enter a speaker ID before recording.');
      return null;
    }
    final distance = double.tryParse(_distanceController.text.trim());
    if (distance == null || distance <= 0) {
      _showFormError('Enter a valid recording distance.');
      return null;
    }
    return TrainingRecordingUpload(
      filePath: '',
      keyword: keyword,
      speakerId: speakerId,
      ageGroup: _ageGroup,
      gender: _gender,
      distanceM: distance,
      noiseCondition: _noiseCondition,
    );
  }

  void _showFormError(String message) {
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }
}

// ── Private Widgets ──────────────────────────────────────────────────────────

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.title, required this.icon});

  final String title;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 20, color: Theme.of(context).colorScheme.primary),
        const SizedBox(width: 8),
        Text(
          title,
          style: Theme.of(
            context,
          ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.bold),
        ),
      ],
    );
  }
}

class _StatChip extends StatelessWidget {
  const _StatChip({
    required this.label,
    required this.value,
    required this.icon,
  });

  final String label;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Card(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 8),
          child: Column(
            children: [
              Icon(icon, color: Theme.of(context).colorScheme.primary),
              const SizedBox(height: 4),
              Text(
                value,
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                ),
              ),
              Text(label, style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
        ),
      ),
    );
  }
}

class _KeywordGrid extends StatelessWidget {
  const _KeywordGrid({required this.keywords, required this.counts});

  final List<TrainingKeyword> keywords;
  final Map<String, int> counts;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: keywords.map((kw) {
        final count = counts[kw.slug] ?? 0;
        return Chip(
          avatar: CircleAvatar(
            backgroundColor: kw.language == 'fil'
                ? Colors.blue.shade100
                : Colors.green.shade100,
            child: Text(
              kw.language.toUpperCase(),
              style: const TextStyle(fontSize: 10, fontWeight: FontWeight.bold),
            ),
          ),
          label: Text('${kw.keyword} ($count)'),
        );
      }).toList(),
    );
  }
}

class _PipelineButton extends StatelessWidget {
  const _PipelineButton({
    required this.label,
    required this.icon,
    required this.color,
    required this.onPressed,
  });

  final String label;
  final IconData icon;
  final Color color;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return FilledButton.tonalIcon(
      onPressed: onPressed,
      icon: Icon(icon, color: color),
      label: Text(label),
    );
  }
}

class _RecordingStatusBanner extends StatelessWidget {
  const _RecordingStatusBanner({required this.status, required this.elapsed});

  final TrainingRecordingStatus status;
  final Duration elapsed;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final (IconData icon, String label, Color color) = switch (status) {
      TrainingRecordingStatus.recording => (
        Icons.fiber_manual_record_rounded,
        'Recording... ${_formatElapsed(elapsed)}',
        theme.colorScheme.error,
      ),
      TrainingRecordingStatus.stopping => (
        Icons.stop_circle_outlined,
        'Stopping recording...',
        theme.colorScheme.primary,
      ),
      TrainingRecordingStatus.uploading => (
        Icons.cloud_upload_outlined,
        'Uploading sample...',
        theme.colorScheme.primary,
      ),
      TrainingRecordingStatus.success => (
        Icons.check_circle_outline,
        'Sample uploaded.',
        Colors.green,
      ),
      TrainingRecordingStatus.error => (
        Icons.error_outline,
        'Recording or upload failed.',
        theme.colorScheme.error,
      ),
      TrainingRecordingStatus.idle => (
        Icons.mic_none_rounded,
        'Ready to record 16 kHz mono WAV.',
        theme.colorScheme.onSurfaceVariant,
      ),
    };

    return Row(
      children: [
        Icon(icon, color: color, size: 18),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            label,
            style: theme.textTheme.bodyMedium?.copyWith(color: color),
          ),
        ),
      ],
    );
  }

  String _formatElapsed(Duration duration) {
    final minutes = duration.inMinutes.remainder(60).toString().padLeft(2, '0');
    final seconds = duration.inSeconds.remainder(60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }
}

class _JobStatusCard extends StatelessWidget {
  const _JobStatusCard({required this.job});

  final dynamic job; // TrainingJob

  @override
  Widget build(BuildContext context) {
    final status = (job as dynamic).status as String;
    final type = (job as dynamic).type as String;
    final error = (job as dynamic).error as String?;
    final result = (job as dynamic).result as Map<String, dynamic>?;

    final (Color chipColor, IconData chipIcon) = switch (status) {
      'queued' => (Colors.orange, Icons.schedule),
      'running' => (Colors.blue, Icons.sync),
      'succeeded' => (Colors.green, Icons.check_circle),
      'failed' => (Colors.red, Icons.error),
      _ => (Colors.grey, Icons.help_outline),
    };

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(chipIcon, color: chipColor),
                const SizedBox(width: 8),
                Text(
                  type.toUpperCase(),
                  style: Theme.of(
                    context,
                  ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.bold),
                ),
                const Spacer(),
                Chip(
                  label: Text(status),
                  backgroundColor: chipColor.withValues(alpha: 0.15),
                  side: BorderSide(color: chipColor),
                ),
              ],
            ),
            if (status == 'running' || status == 'queued') ...[
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: job.progress > 0 && status == 'running'
                    ? LinearProgressIndicator(value: job.progress / 100.0)
                    : const LinearProgressIndicator(),
              ),
              if (job.progress > 0 && status == 'running')
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      if (job.message != null)
                        Expanded(
                          child: Text(
                            job.message!,
                            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                  color: Colors.grey.shade600,
                                ),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      Text(
                        '${job.progress}%',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              fontWeight: FontWeight.bold,
                              color: chipColor,
                            ),
                      ),
                    ],
                  ),
                )
              else if (job.message != null)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    job.message!,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Colors.grey.shade600,
                        ),
                  ),
                ),
            ],
            if (error != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  error,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ),
            if (result != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  result.entries.map((e) => '${e.key}: ${e.value}').join('\n'),
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _DistributionCard extends StatelessWidget {
  const _DistributionCard({required this.data, required this.color});

  final Map<String, int> data;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final sorted = data.entries.toList()
      ..sort((a, b) => b.value.compareTo(a.value));
    final maxVal = sorted.isEmpty ? 1 : sorted.first.value;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: sorted.map((entry) {
            return Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Row(
                children: [
                  SizedBox(
                    width: 100,
                    child: Text(
                      entry.key,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                  Expanded(
                    child: LinearProgressIndicator(
                      value: entry.value / maxVal,
                      color: color,
                      backgroundColor: color.withValues(alpha: 0.1),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    '${entry.value}',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            );
          }).toList(),
        ),
      ),
    );
  }
}
