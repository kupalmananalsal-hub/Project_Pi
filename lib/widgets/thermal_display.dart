import 'package:flutter/material.dart';

import '../models/thermal_frame.dart';

class ThermalDisplay extends StatelessWidget {
  const ThermalDisplay({
    super.key,
    required this.frame,
    required this.colorMap,
    required this.minTemp,
    required this.maxTemp,
    this.selectedX,
    this.selectedY,
    this.onPixelSelected,
  });

  final ThermalFrame? frame;
  final ThermalColorMap colorMap;
  final double minTemp;
  final double maxTemp;
  final int? selectedX;
  final int? selectedY;
  final void Function(int x, int y)? onPixelSelected;

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 4 / 3,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(8),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(8),
          child: LayoutBuilder(
            builder: (context, constraints) {
              final currentFrame = frame;
              return GestureDetector(
                onTapDown: currentFrame == null
                    ? null
                    : (details) {
                        final width = constraints.maxWidth;
                        final height = constraints.maxHeight;
                        final x =
                            (details.localPosition.dx /
                                    width *
                                    currentFrame.width)
                                .floor()
                                .clamp(0, currentFrame.width - 1);
                        final y =
                            (details.localPosition.dy /
                                    height *
                                    currentFrame.height)
                                .floor()
                                .clamp(0, currentFrame.height - 1);
                        onPixelSelected?.call(x, y);
                      },
                child: CustomPaint(
                  painter: _ThermalPainter(
                    frame: currentFrame,
                    colorMap: colorMap,
                    minTemp: minTemp,
                    maxTemp: maxTemp,
                    selectedX: selectedX,
                    selectedY: selectedY,
                    textColor: Theme.of(context).colorScheme.onSurface,
                  ),
                  child: const SizedBox.expand(),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

class _ThermalPainter extends CustomPainter {
  const _ThermalPainter({
    required this.frame,
    required this.colorMap,
    required this.minTemp,
    required this.maxTemp,
    required this.selectedX,
    required this.selectedY,
    required this.textColor,
  });

  final ThermalFrame? frame;
  final ThermalColorMap colorMap;
  final double minTemp;
  final double maxTemp;
  final int? selectedX;
  final int? selectedY;
  final Color textColor;

  @override
  void paint(Canvas canvas, Size size) {
    final currentFrame = frame;
    if (currentFrame == null) {
      final textPainter = TextPainter(
        text: TextSpan(
          text: 'Waiting for thermal stream',
          style: TextStyle(color: textColor.withValues(alpha: 0.7)),
        ),
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: size.width);
      textPainter.paint(
        canvas,
        Offset(
          (size.width - textPainter.width) / 2,
          (size.height - textPainter.height) / 2,
        ),
      );
      return;
    }

    final cellWidth = size.width / currentFrame.width;
    final cellHeight = size.height / currentFrame.height;
    final paint = Paint();

    for (var y = 0; y < currentFrame.height; y++) {
      for (var x = 0; x < currentFrame.width; x++) {
        paint.color = thermalColorForValue(
          currentFrame.temperatureAt(x, y),
          minTemp,
          maxTemp,
          colorMap,
        );
        canvas.drawRect(
          Rect.fromLTWH(x * cellWidth, y * cellHeight, cellWidth, cellHeight),
          paint,
        );
      }
    }

    if (selectedX != null && selectedY != null) {
      final center = Offset(
        (selectedX! + 0.5) * cellWidth,
        (selectedY! + 0.5) * cellHeight,
      );
      final linePaint = Paint()
        ..color = Colors.white
        ..strokeWidth = 1.5;
      canvas.drawLine(
        Offset(center.dx - 10, center.dy),
        Offset(center.dx + 10, center.dy),
        linePaint,
      );
      canvas.drawLine(
        Offset(center.dx, center.dy - 10),
        Offset(center.dx, center.dy + 10),
        linePaint,
      );
      canvas.drawCircle(center, 6, linePaint..style = PaintingStyle.stroke);
    }
  }

  @override
  bool shouldRepaint(covariant _ThermalPainter oldDelegate) {
    return oldDelegate.frame != frame ||
        oldDelegate.colorMap != colorMap ||
        oldDelegate.minTemp != minTemp ||
        oldDelegate.maxTemp != maxTemp ||
        oldDelegate.selectedX != selectedX ||
        oldDelegate.selectedY != selectedY ||
        oldDelegate.textColor != textColor;
  }
}
