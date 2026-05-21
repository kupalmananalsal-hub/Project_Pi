import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/voice_direction.dart';

class DirectionCompass extends StatefulWidget {
  const DirectionCompass({
    super.key,
    required this.direction,
    this.size = 220,
    this.showLabels = true,
  });

  final VoiceDirection direction;
  final double size;
  final bool showLabels;

  @override
  State<DirectionCompass> createState() => _DirectionCompassState();
}

class _DirectionCompassState extends State<DirectionCompass>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
      lowerBound: 0.72,
      upperBound: 1,
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox.square(
      dimension: widget.size,
      child: AnimatedBuilder(
        animation: _pulse,
        builder: (context, _) {
          return CustomPaint(
            painter: _DirectionCompassPainter(
              direction: widget.direction,
              pulse: _pulse.value,
              surface: Theme.of(context).colorScheme.surfaceContainerHighest,
              outline: Theme.of(context).colorScheme.outlineVariant,
              textColor: Theme.of(context).colorScheme.onSurface,
              accent: Colors.deepOrangeAccent,
              showLabels: widget.showLabels,
            ),
          );
        },
      ),
    );
  }
}

class _DirectionCompassPainter extends CustomPainter {
  const _DirectionCompassPainter({
    required this.direction,
    required this.pulse,
    required this.surface,
    required this.outline,
    required this.textColor,
    required this.accent,
    required this.showLabels,
  });

  final VoiceDirection direction;
  final double pulse;
  final Color surface;
  final Color outline;
  final Color textColor;
  final Color accent;
  final bool showLabels;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = math.min(size.width, size.height) / 2 - 10;
    final fill = Paint()..color = surface;
    final stroke = Paint()
      ..color = outline
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;

    canvas.drawCircle(center, radius, fill);
    canvas.drawCircle(center, radius, stroke);

    for (var i = 0; i < 8; i++) {
      final angle = (-90 + (i * 45)) * math.pi / 180;
      final inner = Offset(
        center.dx + math.cos(angle) * (radius * 0.22),
        center.dy + math.sin(angle) * (radius * 0.22),
      );
      final outer = Offset(
        center.dx + math.cos(angle) * radius,
        center.dy + math.sin(angle) * radius,
      );
      canvas.drawLine(inner, outer, stroke);
    }

    final devicePaint = Paint()..color = textColor.withValues(alpha: 0.9);
    canvas.drawCircle(center, 9, devicePaint);
    canvas.drawCircle(center, 15, stroke);

    if (showLabels) {
      _label(canvas, center + Offset(0, -radius + 22), 'FRONT', size.width);
      _label(canvas, center + Offset(radius - 28, 0), 'RIGHT', size.width);
      _label(canvas, center + Offset(0, radius - 22), 'BACK', size.width);
      _label(canvas, center + Offset(-radius + 28, 0), 'LEFT', size.width);
    }

    if (!direction.isKnown) {
      _label(canvas, center + const Offset(0, 34), 'NO DIRECTION', size.width);
      return;
    }

    final sourceAngle = (direction.angleDegrees - 90) * math.pi / 180;
    final source = Offset(
      center.dx + math.cos(sourceAngle) * (radius * 0.62),
      center.dy + math.sin(sourceAngle) * (radius * 0.62),
    );
    final glow = Paint()
      ..color = accent.withValues(alpha: 0.18 * pulse)
      ..style = PaintingStyle.fill;
    final dot = Paint()
      ..color = accent
      ..style = PaintingStyle.fill;
    canvas.drawCircle(source, 28 * pulse, glow);
    canvas.drawCircle(source, 9 + (4 * pulse), dot);

    final arrow = Paint()
      ..color = accent
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(center, source, arrow);
  }

  void _label(Canvas canvas, Offset center, String text, double maxWidth) {
    final painter = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(
          color: textColor.withValues(alpha: 0.76),
          fontSize: 11,
          fontWeight: FontWeight.w700,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout(maxWidth: maxWidth);
    painter.paint(
      canvas,
      Offset(center.dx - painter.width / 2, center.dy - painter.height / 2),
    );
  }

  @override
  bool shouldRepaint(covariant _DirectionCompassPainter oldDelegate) {
    return oldDelegate.direction != direction ||
        oldDelegate.pulse != pulse ||
        oldDelegate.surface != surface ||
        oldDelegate.outline != outline ||
        oldDelegate.textColor != textColor ||
        oldDelegate.accent != accent ||
        oldDelegate.showLabels != showLabels;
  }
}
