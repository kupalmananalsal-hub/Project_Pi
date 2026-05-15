import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../models/audio_frame.dart';

class AudioMeter extends StatefulWidget {
  const AudioMeter({
    super.key,
    required this.label,
    required this.value,
    required this.color,
    this.noiseFloor = 0.02,
  });

  final String label;
  final double value;
  final Color color;
  final double noiseFloor;

  @override
  State<AudioMeter> createState() => _AudioMeterState();
}

class _AudioMeterState extends State<AudioMeter> {
  double _smoothed = 0;

  @override
  void initState() {
    super.initState();
    _smoothed = widget.value.clamp(0.0, 1.0);
  }

  @override
  void didUpdateWidget(covariant AudioMeter oldWidget) {
    super.didUpdateWidget(oldWidget);
    final current = widget.value.clamp(0.0, 1.0);
    _smoothed = (current * 0.3) + (_smoothed * 0.7);
  }

  @override
  Widget build(BuildContext context) {
    final percent = _smoothed.clamp(0.0, 1.0);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                widget.label,
                style: Theme.of(context).textTheme.labelLarge,
              ),
            ),
            Text('${(percent * 100).round()}%'),
          ],
        ),
        const SizedBox(height: 8),
        ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: SizedBox(
            height: 18,
            child: Stack(
              fit: StackFit.expand,
              children: [
                LinearProgressIndicator(
                  value: percent,
                  minHeight: 18,
                  color: widget.color,
                  backgroundColor: widget.color.withValues(alpha: 0.16),
                ),
                CustomPaint(
                  painter: _NoiseFloorPainter(
                    position: widget.noiseFloor.clamp(0.0, 1.0),
                    color: Colors.grey.shade300,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _NoiseFloorPainter extends CustomPainter {
  const _NoiseFloorPainter({required this.position, required this.color});

  final double position;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final x = size.width * position;
    final paint = Paint()
      ..color = color
      ..strokeWidth = 1.5;
    var y = 0.0;
    while (y < size.height) {
      canvas.drawLine(Offset(x, y), Offset(x, y + 3), paint);
      y += 6;
    }
  }

  @override
  bool shouldRepaint(covariant _NoiseFloorPainter oldDelegate) {
    return oldDelegate.position != position || oldDelegate.color != color;
  }
}

class DirectionIndicator extends StatelessWidget {
  const DirectionIndicator({super.key, required this.direction});

  final String direction;

  @override
  Widget build(BuildContext context) {
    final normalized = direction.toLowerCase();
    final icon = switch (normalized) {
      'left' => Icons.keyboard_arrow_left_rounded,
      'right' => Icons.keyboard_arrow_right_rounded,
      _ => Icons.keyboard_arrow_up_rounded,
    };
    final label = switch (normalized) {
      'left' => 'Voice left',
      'right' => 'Voice right',
      _ => 'Voice center',
    };

    return Chip(avatar: Icon(icon, size: 20), label: Text(label));
  }
}

class AudioHistoryChart extends StatelessWidget {
  const AudioHistoryChart({super.key, required this.history});

  final List<AudioFrame> history;

  @override
  Widget build(BuildContext context) {
    if (history.length < 2) {
      return Center(
        child: Text(
          'Waiting for audio stream',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
      );
    }

    final leftSpots = <FlSpot>[];
    final rightSpots = <FlSpot>[];
    for (var i = 0; i < history.length; i++) {
      leftSpots.add(FlSpot(i.toDouble(), history[i].normalizedLeft));
      rightSpots.add(FlSpot(i.toDouble(), history[i].normalizedRight));
    }

    return LineChart(
      LineChartData(
        minX: 0,
        maxX: (history.length - 1).toDouble(),
        minY: 0,
        maxY: 1,
        gridData: const FlGridData(show: false),
        titlesData: const FlTitlesData(show: false),
        borderData: FlBorderData(show: false),
        lineTouchData: const LineTouchData(enabled: false),
        lineBarsData: [
          LineChartBarData(
            spots: leftSpots,
            color: Colors.cyanAccent,
            barWidth: 2,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(
              show: true,
              color: Colors.cyanAccent.withValues(alpha: 0.08),
            ),
          ),
          LineChartBarData(
            spots: rightSpots,
            color: Colors.orangeAccent,
            barWidth: 2,
            dotData: const FlDotData(show: false),
          ),
        ],
      ),
      duration: const Duration(milliseconds: 180),
    );
  }
}
