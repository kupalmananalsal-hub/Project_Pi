import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/voice_direction.dart';

const _radarLine = Color(0xFF263441);
const _radarText = Color(0xFFA5ADB9);
const _radarAccent = Color(0xFFFF3042);

class RadarCompass extends StatefulWidget {
  const RadarCompass({super.key, required this.direction, this.size = 340});

  final VoiceDirection direction;
  final double size;

  @override
  State<RadarCompass> createState() => _RadarCompassState();
}

class _RadarCompassState extends State<RadarCompass>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 950),
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
            painter: _RadarCompassPainter(
              direction: widget.direction,
              pulse: _pulse.value,
            ),
          );
        },
      ),
    );
  }
}

class _RadarCompassPainter extends CustomPainter {
  const _RadarCompassPainter({required this.direction, required this.pulse});

  final VoiceDirection direction;
  final double pulse;

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = (math.min(size.width, size.height) / 2) - 10;
    final ringPaint = Paint()
      ..color = _radarLine.withValues(alpha: 0.58)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2;
    final faintRingPaint = Paint()
      ..color = _radarLine.withValues(alpha: 0.32)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;

    for (final factor in const [1.0, 0.74, 0.43]) {
      canvas.drawCircle(center, radius * factor, ringPaint);
    }

    canvas.drawCircle(center, radius * 0.12, faintRingPaint);

    _drawAxisLabels(canvas, center, radius, size.width);

    if (direction.isKnown) {
      _drawDirectionBeam(canvas, center, radius);
    }

    _drawReadout(canvas, center, size.width);
  }

  void _drawDirectionBeam(Canvas canvas, Offset center, double radius) {
    final angle = (direction.angleDegrees - 90) * math.pi / 180;
    final sweep = 28 * math.pi / 180;
    final outerRadius = radius * 0.88;
    final outerRect = Rect.fromCircle(center: center, radius: outerRadius);

    final glowPath = Path()
      ..moveTo(center.dx, center.dy)
      ..arcTo(outerRect, angle - sweep / 2, sweep, false)
      ..close();
    canvas.drawPath(
      glowPath,
      Paint()
        ..shader = RadialGradient(
          colors: [
            _radarAccent.withValues(alpha: 0.28),
            _radarAccent.withValues(alpha: 0.08),
            _radarAccent.withValues(alpha: 0.0),
          ],
          stops: const [0, 0.55, 1],
        ).createShader(Rect.fromCircle(center: center, radius: outerRadius)),
    );

    final tip = Offset(
      center.dx + math.cos(angle) * (radius * 0.80),
      center.dy + math.sin(angle) * (radius * 0.80),
    );
    final tail = Offset(
      center.dx + math.cos(angle) * (radius * 0.44),
      center.dy + math.sin(angle) * (radius * 0.44),
    );
    final arrowGlow = Paint()
      ..color = _radarAccent.withValues(alpha: 0.20 * pulse)
      ..strokeWidth = 16
      ..strokeCap = StrokeCap.round;
    final arrowLine = Paint()
      ..color = _radarAccent
      ..strokeWidth = 6
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(tail, tip, arrowGlow);
    canvas.drawLine(tail, tip, arrowLine);

    final backAngle = angle + math.pi;
    final leftWing = tip.translate(
      math.cos(backAngle - math.pi / 6) * 24,
      math.sin(backAngle - math.pi / 6) * 24,
    );
    final rightWing = tip.translate(
      math.cos(backAngle + math.pi / 6) * 24,
      math.sin(backAngle + math.pi / 6) * 24,
    );
    final arrowHead = Path()
      ..moveTo(tip.dx, tip.dy)
      ..lineTo(leftWing.dx, leftWing.dy)
      ..lineTo(rightWing.dx, rightWing.dy)
      ..close();
    final arrowFill = Paint()
      ..color = _radarAccent
      ..style = PaintingStyle.fill;
    canvas.drawPath(arrowHead, arrowFill);

    _label(
      canvas,
      tip.translate(0, -28),
      direction.label,
      radius,
      color: Colors.white.withValues(alpha: 0.72),
      fontSize: 13,
      fontWeight: FontWeight.w800,
    );
  }

  void _drawAxisLabels(
    Canvas canvas,
    Offset center,
    double radius,
    double width,
  ) {
    _label(canvas, center + Offset(0, -radius * 0.82), 'FRONT', width);
    _label(canvas, center + Offset(radius * 0.88, 0), 'R', width);
    _label(canvas, center + Offset(0, radius * 0.84), 'BACK', width);
    _label(canvas, center + Offset(-radius * 0.88, 0), 'L', width);
  }

  void _drawReadout(Canvas canvas, Offset center, double width) {
    final angleText = direction.isKnown
        ? '${direction.angleDegrees.round()}°'
        : '--°';
    final distanceText = direction.distanceMeters == null
        ? '≈ -- m'
        : '≈ ${direction.distanceMeters!.toStringAsFixed(1)} m';

    _label(
      canvas,
      center.translate(0, -6),
      angleText,
      width,
      color: Colors.white,
      fontSize: 40,
      fontWeight: FontWeight.w800,
    );
    _label(
      canvas,
      center.translate(0, 33),
      distanceText,
      width,
      color: _radarText,
      fontSize: 18,
      fontWeight: FontWeight.w700,
    );
  }

  void _label(
    Canvas canvas,
    Offset center,
    String text,
    double maxWidth, {
    Color color = _radarText,
    double fontSize = 14,
    FontWeight fontWeight = FontWeight.w700,
  }) {
    final painter = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(
          color: color,
          fontSize: fontSize,
          fontWeight: fontWeight,
          fontFeatures: const [FontFeature.tabularFigures()],
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
  bool shouldRepaint(covariant _RadarCompassPainter oldDelegate) {
    return oldDelegate.direction != direction || oldDelegate.pulse != pulse;
  }
}
