import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../models/audio_frame.dart';

class AudioMeter extends StatelessWidget {
  const AudioMeter({
    super.key,
    required this.label,
    required this.value,
    required this.color,
  });

  final String label;
  final double value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final percent = value.clamp(0.0, 1.0);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(label, style: Theme.of(context).textTheme.labelLarge),
            ),
            Text('${(percent * 100).round()}%'),
          ],
        ),
        const SizedBox(height: 8),
        ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: LinearProgressIndicator(
            value: percent,
            minHeight: 18,
            color: color,
            backgroundColor: color.withValues(alpha: 0.16),
          ),
        ),
      ],
    );
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
