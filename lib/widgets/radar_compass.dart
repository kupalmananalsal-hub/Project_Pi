import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/voice_direction.dart';

const _arrowPanel = Color(0xFF111821);
const _arrowLine = Color(0xFF263441);
const _arrowText = Color(0xFFA5ADB9);
const _arrowAccent = Color(0xFFFF3042);

class RadarCompass extends StatelessWidget {
  const RadarCompass({super.key, required this.direction, this.size = 340});

  final VoiceDirection direction;
  final double size;

  @override
  Widget build(BuildContext context) {
    final dimension = size.clamp(220.0, 420.0);
    final rotation = direction.isKnown
        ? direction.angleDegrees * math.pi / 180
        : 0.0;

    return SizedBox.square(
      dimension: dimension,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: _arrowPanel,
          shape: BoxShape.circle,
          border: Border.all(color: _arrowLine.withValues(alpha: 0.78)),
        ),
        child: Stack(
          alignment: Alignment.center,
          children: [
            AnimatedRotation(
              turns: rotation / (2 * math.pi),
              duration: const Duration(milliseconds: 240),
              curve: Curves.easeOutCubic,
              child: Icon(
                Icons.navigation_rounded,
                key: const ValueKey('voice-direction-arrow'),
                size: dimension * 0.36,
                color: direction.isKnown ? _arrowAccent : _arrowText,
              ),
            ),
            Positioned(
              bottom: dimension * 0.16,
              child: Text(
                direction.isKnown ? direction.label : 'NO DIRECTION',
                style: const TextStyle(
                  color: _arrowText,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

