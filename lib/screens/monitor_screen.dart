import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/alert_event.dart';
import '../models/audio_frame.dart';
import '../models/thermal_frame.dart';
import '../models/voice_direction.dart';
import '../providers/alerts_provider.dart';
import '../providers/connection_provider.dart';
import '../providers/monitor_provider.dart';
import '../providers/thermal_provider.dart';
import '../services/pi_api_service.dart';
import '../utils/human_detector.dart';
import '../widgets/radar_compass.dart';

const _pageBackground = Color(0xFF071012);
const _panelColor = Color(0xFF151A24);
const _panelBorder = Color(0xFF273642);
const _mutedText = Color(0xFFA5ADB9);
const _trackColor = Color(0xFF222835);
const _alertRed = Color(0xFFFF3042);
const _successGreen = Color(0xFF16D899);

class MonitorScreen extends ConsumerStatefulWidget {
  const MonitorScreen({super.key});

  @override
  ConsumerState<MonitorScreen> createState() => _MonitorScreenState();
}

class _MonitorScreenState extends ConsumerState<MonitorScreen> {
  final _scrollController = ScrollController();

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final monitor = ref.watch(monitorProvider);
    final thermal = ref.watch(thermalProvider);
    final alerts = ref.watch(alertsProvider);
    final directionEvent = alerts.keywordNotice ?? alerts.activeAlert;
    final keywordSpotted = directionEvent != null;
    final direction =
        directionEvent?.voiceDirection ?? const VoiceDirection.unknown();
    final voiceNotice = alerts.keywordNotice;

    return ColoredBox(
      color: _pageBackground,
      child: Stack(
        children: [
          ListView(
            controller: _scrollController,
            padding: EdgeInsets.fromLTRB(
              18,
              18,
              18,
              voiceNotice == null ? 28 : 118,
            ),
            children: [
              Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 620),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _DirectionPanel(
                        direction: direction,
                        keywordSpotted: keywordSpotted,
                        thermalSoftAlert: alerts.thermalSoftAlert,
                      ),
                      const SizedBox(height: 18),
                      _ThermalPanel(thermal: thermal),
                      const SizedBox(height: 18),
                      _MicrophonePanel(audio: monitor.audioFrame),
                      const SizedBox(height: 18),
                      _RecentDetectionsPanel(alerts: alerts.history),
                      const SizedBox(height: 26),
                      _DistressButton(),
                    ],
                  ),
                ),
              ),
            ],
          ),
          if (voiceNotice != null)
            Positioned(
              left: 18,
              right: 18,
              bottom: 18,
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 620),
                  child: _VoiceDetectedBanner(
                    event: voiceNotice,
                    onTap: _scrollToRadar,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }

  void _scrollToRadar() {
    if (!_scrollController.hasClients) {
      return;
    }
    _scrollController.animateTo(
      0,
      duration: const Duration(milliseconds: 320),
      curve: Curves.easeOutCubic,
    );
  }
}

class _DirectionPanel extends StatelessWidget {
  const _DirectionPanel({
    required this.direction,
    required this.keywordSpotted,
    required this.thermalSoftAlert,
  });

  final VoiceDirection direction;
  final bool keywordSpotted;
  final bool thermalSoftAlert;

  @override
  Widget build(BuildContext context) {
    return _MonitorPanel(
      padding: const EdgeInsets.fromLTRB(28, 28, 28, 30),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final radarSize = (constraints.maxWidth - 10).clamp(250.0, 420.0);
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const _SectionTitle('DIRECTION'),
              const SizedBox(height: 20),
              Center(
                child: _StatusPill(
                  label: keywordSpotted ? 'Keyword Spotted!' : 'Listening',
                  active: keywordSpotted,
                ),
              ),
              if (thermalSoftAlert) ...[
                const SizedBox(height: 14),
                const Center(child: _ThermalSoftAlertPill()),
              ],
              const SizedBox(height: 18),
              Center(
                child: RadarCompass(direction: direction, size: radarSize),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _ThermalPanel extends ConsumerWidget {
  const _ThermalPanel({required this.thermal});

  final ThermalState thermal;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final frame = thermal.frame;
    final detection = thermal.humanDetection;
    final frameLabel = frame == null
        ? 'MLX90640 · 32×24'
        : 'MLX90640 · ${frame.width}×${frame.height}';

    return _MonitorPanel(
      padding: const EdgeInsets.fromLTRB(28, 28, 28, 30),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const _SectionTitle('THERMAL'),
                    const SizedBox(height: 10),
                    Text(
                      frameLabel,
                      style: Theme.of(context).textTheme.headlineSmall
                          ?.copyWith(
                            color: Colors.white,
                            fontWeight: FontWeight.w500,
                          ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              _HumanPresencePill(detected: detection.detected),
            ],
          ),
          const SizedBox(height: 26),
          _ThermalViewport(
            frame: frame,
            minTemp: thermal.displayMinTemp,
            maxTemp: thermal.displayMaxTemp,
            selectedX: thermal.selectedX,
            selectedY: thermal.selectedY,
            onPixelSelected: ref.read(thermalProvider.notifier).selectPixel,
          ),
          const SizedBox(height: 18),
          _ThermalLegend(
            minTemp: thermal.displayMinTemp,
            maxTemp: thermal.displayMaxTemp,
          ),
          const SizedBox(height: 22),
          _ThermalFacts(detection: detection),
        ],
      ),
    );
  }
}

class _MicrophonePanel extends StatelessWidget {
  const _MicrophonePanel({required this.audio});

  final AudioFrame? audio;

  @override
  Widget build(BuildContext context) {
    return _MonitorPanel(
      padding: const EdgeInsets.fromLTRB(28, 28, 28, 30),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionTitle('MICROPHONES'),
          const SizedBox(height: 24),
          _MicLevelRow(label: 'MIC L', value: audio?.normalizedLeft ?? 0),
          const SizedBox(height: 18),
          _MicLevelRow(label: 'MIC R', value: audio?.normalizedRight ?? 0),
        ],
      ),
    );
  }
}

class _RecentDetectionsPanel extends StatelessWidget {
  const _RecentDetectionsPanel({required this.alerts});

  final List<AlertEvent> alerts;

  @override
  Widget build(BuildContext context) {
    final recent = alerts.take(4).toList(growable: false);
    return _MonitorPanel(
      padding: const EdgeInsets.fromLTRB(28, 28, 28, 30),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const _SectionTitle('RECENT DETECTIONS'),
          const SizedBox(height: 20),
          if (recent.isEmpty)
            Text(
              'No detections yet. Trigger a test call for help below.',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                color: _mutedText,
                height: 1.35,
              ),
            )
          else
            for (final event in recent) _DetectionLogRow(event: event),
        ],
      ),
    );
  }
}

class _DistressButton extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return SizedBox(
      height: 68,
      child: FilledButton(
        style: FilledButton.styleFrom(
          backgroundColor: _alertRed,
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(24),
          ),
          textStyle: Theme.of(
            context,
          ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
        ),
        onPressed: () => _simulateDistressCall(context, ref),
        child: const Text('Simulate distress call'),
      ),
    );
  }

  Future<void> _simulateDistressCall(
    BuildContext context,
    WidgetRef ref,
  ) async {
    final connection = ref.read(connectionProvider);
    if (!connection.isConnected) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Connect to the Pi before testing.')),
      );
      return;
    }

    try {
      await PiApiService(
        host: connection.host,
        port: connection.port,
      ).postAlert(keyword: 'help', confidence: 0.95);
      if (!context.mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Test distress call sent.')));
    } catch (error) {
      if (!context.mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Test distress call failed: $error')),
      );
    }
  }
}

class _MonitorPanel extends StatelessWidget {
  const _MonitorPanel({required this.child, required this.padding});

  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: _panelColor,
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: _panelBorder),
      ),
      child: Padding(padding: padding, child: child),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: Theme.of(context).textTheme.titleLarge?.copyWith(
        color: _mutedText,
        fontWeight: FontWeight.w800,
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.label, required this.active});

  final String label;
  final bool active;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: active
            ? _alertRed.withValues(alpha: 0.18)
            : const Color(0xFF252A34),
        borderRadius: BorderRadius.circular(26),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 30, vertical: 12),
        child: Text(
          label,
          style: Theme.of(context).textTheme.titleLarge?.copyWith(
            color: active ? _alertRed : _mutedText,
            fontWeight: FontWeight.w800,
          ),
        ),
      ),
    );
  }
}

class _VoiceDetectedBanner extends StatelessWidget {
  const _VoiceDetectedBanner({required this.event, required this.onTap});

  final AlertEvent event;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final confidence = (event.displayedConfidence.clamp(0.0, 1.0) * 100)
        .round();
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(22),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: const Color(0xFF201923),
            borderRadius: BorderRadius.circular(22),
            border: Border.all(color: _alertRed.withValues(alpha: 0.46)),
            boxShadow: [
              BoxShadow(
                color: _alertRed.withValues(alpha: 0.18),
                blurRadius: 24,
                offset: const Offset(0, 10),
              ),
            ],
          ),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(18, 15, 18, 15),
            child: Row(
              children: [
                Container(
                  width: 42,
                  height: 42,
                  decoration: BoxDecoration(
                    color: _alertRed.withValues(alpha: 0.18),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.graphic_eq_rounded, color: _alertRed),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        'Voice Detected',
                        style: Theme.of(context).textTheme.titleMedium
                            ?.copyWith(
                              color: Colors.white,
                              fontWeight: FontWeight.w900,
                            ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        '${event.displayKeyword} - $confidence% - ${event.directionLabel}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(
                          context,
                        ).textTheme.bodyMedium?.copyWith(color: _mutedText),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 12),
                const Icon(Icons.keyboard_arrow_up_rounded, color: _mutedText),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ThermalSoftAlertPill extends StatefulWidget {
  const _ThermalSoftAlertPill();

  @override
  State<_ThermalSoftAlertPill> createState() => _ThermalSoftAlertPillState();
}

class _ThermalSoftAlertPillState extends State<_ThermalSoftAlertPill>
    with SingleTickerProviderStateMixin {
  late final AnimationController _pulse;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 680),
      lowerBound: 0.48,
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
    const thermalColor = Color(0xFFFFC857);
    return AnimatedBuilder(
      animation: _pulse,
      builder: (context, child) {
        return Opacity(opacity: _pulse.value, child: child);
      },
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: thermalColor.withValues(alpha: 0.14),
          borderRadius: BorderRadius.circular(18),
          border: Border.all(color: thermalColor.withValues(alpha: 0.48)),
        ),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 9),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                Icons.thermostat_rounded,
                size: 18,
                color: thermalColor,
              ),
              const SizedBox(width: 8),
              Text(
                'Thermal presence detected',
                style: Theme.of(context).textTheme.labelLarge?.copyWith(
                  color: thermalColor,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _HumanPresencePill extends StatelessWidget {
  const _HumanPresencePill({required this.detected});

  final bool detected;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: detected ? _successGreen.withValues(alpha: 0.20) : _trackColor,
        borderRadius: BorderRadius.circular(22),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
        child: Text(
          detected ? 'Human present' : 'Scanning',
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
            color: detected ? _successGreen : _mutedText,
            fontWeight: FontWeight.w800,
          ),
        ),
      ),
    );
  }
}

class _ThermalViewport extends StatelessWidget {
  const _ThermalViewport({
    required this.frame,
    required this.minTemp,
    required this.maxTemp,
    required this.selectedX,
    required this.selectedY,
    required this.onPixelSelected,
  });

  final ThermalFrame? frame;
  final double minTemp;
  final double maxTemp;
  final int? selectedX;
  final int? selectedY;
  final void Function(int x, int y) onPixelSelected;

  @override
  Widget build(BuildContext context) {
    return AspectRatio(
      aspectRatio: 4 / 3,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(22),
        child: LayoutBuilder(
          builder: (context, constraints) {
            final currentFrame = frame;
            return GestureDetector(
              onTapDown: currentFrame == null
                  ? null
                  : (details) {
                      final x =
                          (details.localPosition.dx /
                                  constraints.maxWidth *
                                  currentFrame.width)
                              .floor()
                              .clamp(0, currentFrame.width - 1);
                      final y =
                          (details.localPosition.dy /
                                  constraints.maxHeight *
                                  currentFrame.height)
                              .floor()
                              .clamp(0, currentFrame.height - 1);
                      onPixelSelected(x, y);
                    },
              child: CustomPaint(
                painter: _ThermalViewportPainter(
                  frame: currentFrame,
                  minTemp: minTemp,
                  maxTemp: maxTemp,
                  selectedX: selectedX,
                  selectedY: selectedY,
                  textColor: _mutedText,
                ),
                child: const SizedBox.expand(),
              ),
            );
          },
        ),
      ),
    );
  }
}

class _ThermalViewportPainter extends CustomPainter {
  const _ThermalViewportPainter({
    required this.frame,
    required this.minTemp,
    required this.maxTemp,
    required this.selectedX,
    required this.selectedY,
    required this.textColor,
  });

  final ThermalFrame? frame;
  final double minTemp;
  final double maxTemp;
  final int? selectedX;
  final int? selectedY;
  final Color textColor;

  @override
  void paint(Canvas canvas, Size size) {
    final background = Paint()..color = const Color(0xFF07102B);
    canvas.drawRect(Offset.zero & size, background);

    final currentFrame = frame;
    if (currentFrame == null) {
      final painter = TextPainter(
        text: TextSpan(
          text: 'Waiting for thermal stream',
          style: TextStyle(color: textColor, fontSize: 16),
        ),
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: size.width);
      painter.paint(
        canvas,
        Offset(
          (size.width - painter.width) / 2,
          (size.height - painter.height) / 2,
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
          ThermalColorMap.jet,
        );
        canvas.drawRect(
          Rect.fromLTWH(x * cellWidth, y * cellHeight, cellWidth, cellHeight),
          paint,
        );
      }
    }

    final gridPaint = Paint()
      ..color = Colors.white.withValues(alpha: 0.05)
      ..strokeWidth = 1;
    for (var x = 8; x < currentFrame.width; x += 8) {
      final dx = x * cellWidth;
      canvas.drawLine(Offset(dx, 0), Offset(dx, size.height), gridPaint);
    }
    for (var y = 6; y < currentFrame.height; y += 6) {
      final dy = y * cellHeight;
      canvas.drawLine(Offset(0, dy), Offset(size.width, dy), gridPaint);
    }

    if (selectedX != null && selectedY != null) {
      final center = Offset(
        (selectedX! + 0.5) * cellWidth,
        (selectedY! + 0.5) * cellHeight,
      );
      final cross = Paint()
        ..color = Colors.white
        ..strokeWidth = 1.5;
      canvas.drawLine(
        center + const Offset(-10, 0),
        center + const Offset(10, 0),
        cross,
      );
      canvas.drawLine(
        center + const Offset(0, -10),
        center + const Offset(0, 10),
        cross,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _ThermalViewportPainter oldDelegate) {
    return oldDelegate.frame != frame ||
        oldDelegate.minTemp != minTemp ||
        oldDelegate.maxTemp != maxTemp ||
        oldDelegate.selectedX != selectedX ||
        oldDelegate.selectedY != selectedY ||
        oldDelegate.textColor != textColor;
  }
}

class _ThermalLegend extends StatelessWidget {
  const _ThermalLegend({required this.minTemp, required this.maxTemp});

  final double minTemp;
  final double maxTemp;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Text(_tempLabel(minTemp), style: _legendStyle(context)),
        const SizedBox(width: 14),
        const Expanded(child: _JetGradientBar()),
        const SizedBox(width: 14),
        Text(_tempLabel(maxTemp), style: _legendStyle(context)),
      ],
    );
  }

  TextStyle? _legendStyle(BuildContext context) {
    return Theme.of(context).textTheme.titleMedium?.copyWith(
      color: _mutedText,
      fontFeatures: const [FontFeature.tabularFigures()],
    );
  }

  String _tempLabel(double temp) => '${temp.toStringAsFixed(1)}°C';
}

class _JetGradientBar extends StatelessWidget {
  const _JetGradientBar();

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(8),
      child: const SizedBox(
        height: 12,
        child: DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                Color(0xFF0015A8),
                Color(0xFF008BFF),
                Color(0xFF00FF70),
                Color(0xFFFFE600),
                Color(0xFFFF8A00),
                Color(0xFFFF2A00),
                Color(0xFF7A0000),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ThermalFacts extends StatelessWidget {
  const _ThermalFacts({required this.detection});

  final HumanDetectionResult detection;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _FactTile(
            label: 'COVERAGE',
            value: '${(detection.bodyCoverage * 100).toStringAsFixed(1)}%',
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _FactTile(label: 'PART', value: _compactPart(detection)),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _FactTile(
            label: 'BOOST',
            value: _signed(detection.confidenceBoost),
          ),
        ),
      ],
    );
  }

  String _compactPart(HumanDetectionResult detection) {
    switch (detection.detectedPart) {
      case 'finger_detected':
        return 'Finger';
      case 'hand_or_partial_face':
        return 'Hand';
      case 'torso_or_full_face':
        return 'Torso';
      case 'analysis_error':
        return 'Error';
      default:
        return detection.detected ? detection.detectedPartLabel : 'None';
    }
  }

  String _signed(double value) {
    final prefix = value >= 0 ? '+' : '';
    return '$prefix${value.toStringAsFixed(2)}';
  }
}

class _FactTile extends StatelessWidget {
  const _FactTile({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: const Color(0xFF1C212D),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 15, 14, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              label,
              maxLines: 1,
              style: Theme.of(context).textTheme.labelLarge?.copyWith(
                color: _mutedText,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.centerLeft,
              child: Text(
                value,
                maxLines: 1,
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  color: Colors.white,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MicLevelRow extends StatelessWidget {
  const _MicLevelRow({required this.label, required this.value});

  final String label;
  final double value;

  @override
  Widget build(BuildContext context) {
    final percent = value.clamp(0.0, 1.0);
    return Row(
      children: [
        SizedBox(
          width: 70,
          child: Text(
            label,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              color: _mutedText,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: SizedBox(
              height: 12,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  const DecoratedBox(
                    decoration: BoxDecoration(color: _trackColor),
                  ),
                  FractionallySizedBox(
                    widthFactor: percent,
                    alignment: Alignment.centerLeft,
                    child: const DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          colors: [
                            Color(0xFF28F0B8),
                            Color(0xFFFFE15E),
                            Color(0xFFFF514B),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(width: 18),
        SizedBox(
          width: 34,
          child: Text(
            '${(percent * 100).round()}',
            textAlign: TextAlign.right,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              color: _mutedText,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
        ),
      ],
    );
  }
}

class _DetectionLogRow extends StatelessWidget {
  const _DetectionLogRow({required this.event});

  final AlertEvent event;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  event.displayKeyword,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    color: Colors.white,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  '${_formatTime(event.timestamp)} · ${event.directionLabel}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(
                    context,
                  ).textTheme.bodyMedium?.copyWith(color: _mutedText),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          _AlertLevelPill(level: event.alertLevel),
        ],
      ),
    );
  }

  String _formatTime(DateTime timestamp) {
    final local = timestamp.toLocal();
    final hour = local.hour.toString().padLeft(2, '0');
    final minute = local.minute.toString().padLeft(2, '0');
    return '$hour:$minute';
  }
}

class _AlertLevelPill extends StatelessWidget {
  const _AlertLevelPill({required this.level});

  final String level;

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (level) {
      'full_alert' => ('FULL', _alertRed),
      'visual_only' => ('VISUAL', const Color(0xFFFFC857)),
      _ => ('SUPPRESSED', _mutedText),
    };
    return DecoratedBox(
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
        child: Text(
          label,
          style: Theme.of(context).textTheme.labelLarge?.copyWith(
            color: color,
            fontWeight: FontWeight.w800,
          ),
        ),
      ),
    );
  }
}
