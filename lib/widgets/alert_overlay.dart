import 'package:flutter/material.dart';

import '../models/alert_event.dart';
import '../models/thermal_frame.dart';
import 'thermal_display.dart';

class AlertOverlay extends StatefulWidget {
  const AlertOverlay({
    super.key,
    required this.event,
    required this.humanDetected,
    this.thermalFrame,
    this.thermalColorMap = ThermalColorMap.jet,
    this.thermalMinTemp = 20,
    this.thermalMaxTemp = 45,
    required this.onDismiss,
  });

  final AlertEvent event;
  final bool humanDetected;
  final ThermalFrame? thermalFrame;
  final ThermalColorMap thermalColorMap;
  final double thermalMinTemp;
  final double thermalMaxTemp;
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
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(28),
              child: AnimatedBuilder(
                animation: _controller,
                builder: (context, child) {
                  return Transform.scale(
                    scale: _controller.value,
                    child: child,
                  );
                },
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 520),
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
                        'EMERGENCY ALERT',
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.headlineMedium
                            ?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w800,
                              letterSpacing: 1.5,
                            ),
                      ),
                      const SizedBox(height: 18),
                      Text(
                        'Keyword Spotted!',
                        style: Theme.of(context).textTheme.displaySmall
                            ?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w900,
                            ),
                      ),
                      const SizedBox(height: 8),
                      _AlertDirection(event: widget.event),
                      const SizedBox(height: 12),
                      Text(
                        widget.humanDetected
                            ? 'Thermal human detected - alarm active'
                            : 'No thermal human detected',
                        textAlign: TextAlign.center,
                        style: Theme.of(
                          context,
                        ).textTheme.titleMedium?.copyWith(color: Colors.white),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Final confidence ${(widget.event.displayedConfidence * 100).round()}%',
                        style: Theme.of(
                          context,
                        ).textTheme.titleMedium?.copyWith(color: Colors.white),
                      ),
                      const SizedBox(height: 10),
                      Text(
                        '${widget.event.detectedPartLabel} - '
                        '${(widget.event.bodyCoverage * 100).toStringAsFixed(1)}% coverage - '
                        'boost +${(widget.event.thermalConfidenceBoost * 100).round()}%',
                        textAlign: TextAlign.center,
                        style: Theme.of(
                          context,
                        ).textTheme.bodyLarge?.copyWith(color: Colors.white),
                      ),
                      if (widget.thermalFrame != null) ...[
                        const SizedBox(height: 14),
                        _ThermalCapture(
                          frame: widget.thermalFrame,
                          colorMap: widget.thermalColorMap,
                          minTemp: widget.thermalMinTemp,
                          maxTemp: widget.thermalMaxTemp,
                        ),
                      ],
                      if (widget.event.noiseLevelDb != null ||
                          widget.event.snrDb != null) ...[
                        const SizedBox(height: 8),
                        Text(
                          _noiseSummary(widget.event),
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.bodyMedium
                              ?.copyWith(color: Colors.white70),
                        ),
                      ],
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
        ),
      ),
    );
  }

  String _noiseSummary(AlertEvent event) {
    final noise = event.noiseLevelDb;
    final snr = event.snrDb;
    final parts = <String>[];
    if (noise != null) {
      parts.add('Noise ${noise.toStringAsFixed(1)} dB');
    }
    if (snr != null) {
      parts.add('SNR ${snr.toStringAsFixed(1)} dB');
    }
    return parts.join(' - ');
  }
}

class _ThermalCapture extends StatelessWidget {
  const _ThermalCapture({
    required this.frame,
    required this.colorMap,
    required this.minTemp,
    required this.maxTemp,
  });

  final ThermalFrame? frame;
  final ThermalColorMap colorMap;
  final double minTemp;
  final double maxTemp;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.24),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.36)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          children: [
            Text(
              'Thermal frame at alert time',
              style: Theme.of(
                context,
              ).textTheme.labelLarge?.copyWith(color: Colors.white),
            ),
            const SizedBox(height: 6),
            ThermalDisplay(
              frame: frame,
              colorMap: colorMap,
              minTemp: minTemp,
              maxTemp: maxTemp,
            ),
          ],
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
      'front-left' => Icons.north_west_rounded,
      'front-right' => Icons.north_east_rounded,
      'left' => Icons.keyboard_arrow_left_rounded,
      'right' => Icons.keyboard_arrow_right_rounded,
      'back-left' => Icons.south_west_rounded,
      'back-right' => Icons.south_east_rounded,
      'back' => Icons.keyboard_arrow_down_rounded,
      _ => Icons.keyboard_arrow_up_rounded,
    };
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(icon, color: Colors.white, size: 34),
        const SizedBox(width: 8),
        Text(
          'Voice from ${event.directionLabel}',
          style: Theme.of(
            context,
          ).textTheme.titleLarge?.copyWith(color: Colors.white),
        ),
      ],
    );
  }
}
