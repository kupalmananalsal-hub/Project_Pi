import 'dart:async';

import 'package:flutter/material.dart';

import '../models/alert_event.dart';
import '../widgets/direction_compass.dart';

class DirectionOverlay extends StatefulWidget {
  const DirectionOverlay({
    super.key,
    required this.event,
    required this.humanDetected,
    required this.onConfirm,
    required this.onDismiss,
    this.countdownSeconds = 5,
  });

  final AlertEvent event;
  final bool humanDetected;
  final VoidCallback onConfirm;
  final VoidCallback onDismiss;
  final int countdownSeconds;

  @override
  State<DirectionOverlay> createState() => _DirectionOverlayState();
}

class _DirectionOverlayState extends State<DirectionOverlay> {
  Timer? _timer;
  late int _remaining;
  bool _completed = false;

  @override
  void initState() {
    super.initState();
    _remaining = widget.countdownSeconds;
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted || _completed) {
        return;
      }
      if (_remaining <= 1) {
        _complete(widget.onConfirm);
      } else {
        setState(() => _remaining--);
      }
    });
  }

  @override
  void didUpdateWidget(covariant DirectionOverlay oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.event.timestamp != widget.event.timestamp ||
        oldWidget.event.keyword != widget.event.keyword) {
      _completed = false;
      _remaining = widget.countdownSeconds;
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final event = widget.event;
    final direction = event.voiceDirection;
    return Positioned.fill(
      child: Material(
        color: Colors.black.withValues(alpha: 0.72),
        child: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Card(
                margin: const EdgeInsets.all(16),
                child: Padding(
                  padding: const EdgeInsets.all(18),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Row(
                        children: [
                          const Icon(
                            Icons.record_voice_over_rounded,
                            color: Colors.deepOrangeAccent,
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              'Voice Detected',
                              style: Theme.of(context).textTheme.titleLarge,
                            ),
                          ),
                          Chip(label: Text('${_remaining}s')),
                        ],
                      ),
                      const SizedBox(height: 12),
                      Text(
                        event.displayKeyword,
                        style: Theme.of(context).textTheme.displaySmall
                            ?.copyWith(fontWeight: FontWeight.w900),
                      ),
                      Text(
                        'Confidence ${(event.displayedConfidence * 100).round()}%',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 14),
                      DirectionCompass(direction: direction, size: 230),
                      const SizedBox(height: 12),
                      Wrap(
                        alignment: WrapAlignment.center,
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          Chip(
                            avatar: const Icon(Icons.explore_rounded),
                            label: Text('Direction ${direction.label}'),
                          ),
                          Chip(
                            avatar: const Icon(Icons.social_distance_rounded),
                            label: Text(
                              'Distance ${_distanceLabel(direction.distanceMeters)}',
                            ),
                          ),
                          Chip(
                            avatar: Icon(
                              widget.humanDetected
                                  ? Icons.accessibility_new_rounded
                                  : Icons.visibility_off_rounded,
                            ),
                            label: Text(
                              widget.humanDetected
                                  ? 'Thermal human visible'
                                  : 'No thermal confirmation',
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 14),
                      Text(
                        'Auto-alert in $_remaining seconds',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 18),
                      Row(
                        children: [
                          Expanded(
                            child: OutlinedButton.icon(
                              onPressed: () => _complete(widget.onDismiss),
                              icon: const Icon(Icons.close_rounded),
                              label: const Text('Dismiss'),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: FilledButton.icon(
                              onPressed: () => _complete(widget.onConfirm),
                              icon: const Icon(Icons.warning_rounded),
                              label: const Text('Confirm Alert'),
                            ),
                          ),
                        ],
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

  void _complete(VoidCallback callback) {
    if (_completed) {
      return;
    }
    _completed = true;
    _timer?.cancel();
    callback();
  }

  String _distanceLabel(double? meters) {
    if (meters == null) {
      return 'unknown';
    }
    return '~${meters.toStringAsFixed(1)}m';
  }
}
