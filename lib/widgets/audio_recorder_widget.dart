import 'package:flutter/material.dart';

class AudioRecorderWidget extends StatelessWidget {
  const AudioRecorderWidget({
    super.key,
    required this.keyword,
    required this.recording,
    required this.uploading,
    required this.waveform,
    required this.hasRecording,
    required this.onRecord,
    required this.onStop,
    required this.onUpload,
  });

  final String keyword;
  final bool recording;
  final bool uploading;
  final List<double> waveform;
  final bool hasRecording;
  final VoidCallback? onRecord;
  final VoidCallback? onStop;
  final VoidCallback? onUpload;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          children: [
            Icon(
              recording ? Icons.graphic_eq_rounded : Icons.mic_rounded,
              size: 46,
              color: recording ? Colors.redAccent : theme.colorScheme.primary,
            ),
            const SizedBox(height: 8),
            Text(
              recording
                  ? 'Recording ${keyword.toUpperCase()}'
                  : 'Ready to record',
              style: theme.textTheme.titleMedium,
            ),
            const SizedBox(height: 12),
            SizedBox(
              height: 54,
              child: CustomPaint(
                painter: _WaveformPainter(
                  levels: waveform,
                  color: recording
                      ? Colors.redAccent
                      : theme.colorScheme.primary,
                ),
                child: const SizedBox.expand(),
              ),
            ),
            const SizedBox(height: 14),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              alignment: WrapAlignment.center,
              children: [
                FilledButton.icon(
                  onPressed: recording ? onStop : onRecord,
                  icon: Icon(
                    recording
                        ? Icons.stop_rounded
                        : Icons.fiber_manual_record_rounded,
                  ),
                  label: Text(recording ? 'Stop' : 'Record 3s'),
                ),
                FilledButton.tonalIcon(
                  onPressed: uploading || recording || !hasRecording
                      ? null
                      : onUpload,
                  icon: uploading
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.cloud_upload_rounded),
                  label: Text(uploading ? 'Sending' : 'Send to Pi'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _WaveformPainter extends CustomPainter {
  const _WaveformPainter({required this.levels, required this.color});

  final List<double> levels;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color.withValues(alpha: 0.78)
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 4;
    final count = levels.isEmpty ? 18 : levels.length;
    final gap = size.width / count;
    for (var index = 0; index < count; index++) {
      final level = levels.isEmpty ? 0.08 : levels[index].clamp(0.04, 1.0);
      final x = (index + 0.5) * gap;
      final halfHeight = (size.height * level) / 2;
      canvas.drawLine(
        Offset(x, (size.height / 2) - halfHeight),
        Offset(x, (size.height / 2) + halfHeight),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _WaveformPainter oldDelegate) {
    return oldDelegate.levels != levels || oldDelegate.color != color;
  }
}
