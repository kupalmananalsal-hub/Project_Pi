import 'package:flutter/material.dart';

import '../models/alert_event.dart';

class AlertOverlay extends StatefulWidget {
  const AlertOverlay({
    super.key,
    required this.event,
    required this.humanDetected,
    required this.onDismiss,
  });

  final AlertEvent event;
  final bool humanDetected;
  final VoidCallback onDismiss;

  @override
  State<AlertOverlay> createState() => _AlertOverlayState();
}

class _AlertOverlayState extends State<AlertOverlay>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 780),
      lowerBound: 0.86,
      upperBound: 1.06,
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Positioned.fill(
      child: Material(
        color: Colors.red.shade900,
        child: SafeArea(
          child: AnimatedBuilder(
            animation: _controller,
            builder: (context, child) {
              return Transform.scale(scale: _controller.value, child: child);
            },
            child: Padding(
              padding: const EdgeInsets.all(28),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(
                    Icons.warning_rounded,
                    color: Colors.white,
                    size: 96,
                  ),
                  const SizedBox(height: 24),
                  Text(
                    widget.event.emergencyTitle,
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 18),
                  Text(
                    widget.event.displayKeyword,
                    style: Theme.of(context).textTheme.displaySmall?.copyWith(
                      color: Colors.white,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                  const SizedBox(height: 8),
                  _AlertDirection(event: widget.event),
                  const SizedBox(height: 12),
                  Text(
                    widget.humanDetected
                        ? 'Thermal human detected - vibration enabled'
                        : 'No thermal human visible - vibration skipped',
                    textAlign: TextAlign.center,
                    style: Theme.of(
                      context,
                    ).textTheme.titleMedium?.copyWith(color: Colors.white),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Confidence ${(widget.event.confidence * 100).round()}%',
                    style: Theme.of(
                      context,
                    ).textTheme.titleMedium?.copyWith(color: Colors.white),
                  ),
                  const SizedBox(height: 36),
                  FilledButton.icon(
                    style: FilledButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: Colors.red.shade900,
                      minimumSize: const Size.fromHeight(54),
                    ),
                    onPressed: widget.onDismiss,
                    icon: const Icon(Icons.close_rounded),
                    label: const Text('Dismiss Alert'),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _AlertDirection extends StatelessWidget {
  const _AlertDirection({required this.event});

  final AlertEvent event;

  @override
  Widget build(BuildContext context) {
    final icon = switch (event.direction) {
      'left' => Icons.keyboard_arrow_left_rounded,
      'right' => Icons.keyboard_arrow_right_rounded,
      _ => Icons.keyboard_arrow_up_rounded,
    };
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(icon, color: Colors.white, size: 34),
        const SizedBox(width: 8),
        Text(
          'Voice from the ${event.directionLabel}',
          style: Theme.of(
            context,
          ).textTheme.titleLarge?.copyWith(color: Colors.white),
        ),
      ],
    );
  }
}
