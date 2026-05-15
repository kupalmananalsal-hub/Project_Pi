import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:gal/gal.dart';

import '../models/thermal_frame.dart';
import '../providers/connection_provider.dart';
import '../providers/thermal_provider.dart';
import '../widgets/status_card.dart';
import '../widgets/thermal_display.dart';

class ThermalCameraScreen extends ConsumerStatefulWidget {
  const ThermalCameraScreen({super.key});

  @override
  ConsumerState<ThermalCameraScreen> createState() =>
      _ThermalCameraScreenState();
}

class _ThermalCameraScreenState extends ConsumerState<ThermalCameraScreen> {
  final _captureKey = GlobalKey();

  @override
  Widget build(BuildContext context) {
    final thermal = ref.watch(thermalProvider);
    final connection = ref.watch(connectionProvider);
    final frame = thermal.frame;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                'Thermal Camera',
                style: Theme.of(context).textTheme.headlineSmall,
              ),
            ),
            IconButton.filledTonal(
              tooltip: 'Save screenshot',
              onPressed: frame == null ? null : _saveScreenshot,
              icon: const Icon(Icons.photo_camera_rounded),
            ),
          ],
        ),
        const SizedBox(height: 12),
        if (!connection.isConnected)
          const StatusCard(
            title: 'Stream',
            value: 'Connect to the Pi to start the thermal stream',
            icon: Icons.link_off_rounded,
          ),
        RepaintBoundary(
          key: _captureKey,
          child: ThermalDisplay(
            frame: frame,
            colorMap: thermal.colorMap,
            minTemp: thermal.displayMinTemp,
            maxTemp: thermal.displayMaxTemp,
            selectedX: thermal.selectedX,
            selectedY: thermal.selectedY,
            onPixelSelected: (x, y) {
              ref.read(thermalProvider.notifier).selectPixel(x, y);
            },
          ),
        ),
        const SizedBox(height: 14),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: [
            SizedBox(
              width: 190,
              child: DropdownButtonFormField<ThermalColorMap>(
                initialValue: thermal.colorMap,
                decoration: const InputDecoration(
                  labelText: 'Color map',
                  border: OutlineInputBorder(),
                ),
                items: [
                  for (final map in ThermalColorMap.values)
                    DropdownMenuItem(value: map, child: Text(map.label)),
                ],
                onChanged: (value) {
                  if (value != null) {
                    ref.read(thermalProvider.notifier).setColorMap(value);
                  }
                },
              ),
            ),
            StatusChip(
              icon: Icons.speed_rounded,
              label: '${thermal.fps.toStringAsFixed(1)} fps',
            ),
            StatusChip(
              icon: Icons.center_focus_strong_rounded,
              label: frame == null
                  ? 'Center --'
                  : '${frame.centerTemperature.toStringAsFixed(1)} C',
            ),
            StatusChip(
              icon: thermal.humanDetected
                  ? Icons.accessibility_new_rounded
                  : Icons.person_off_rounded,
              label: thermal.humanDetected ? 'Human visible' : 'No human',
            ),
          ],
        ),
        const SizedBox(height: 18),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Auto Range'),
          subtitle: Text(
            thermal.autoRange
                ? '${thermal.displayMinTemp.toStringAsFixed(1)} C to '
                      '${thermal.displayMaxTemp.toStringAsFixed(1)} C'
                : 'Manual range sliders enabled',
          ),
          value: thermal.autoRange,
          onChanged: (value) {
            ref.read(thermalProvider.notifier).setAutoRange(value);
          },
        ),
        RangeSlider(
          values: RangeValues(thermal.minTemp, thermal.maxTemp),
          min: -20,
          max: 120,
          divisions: 140,
          labels: RangeLabels(
            '${thermal.minTemp.round()} C',
            '${thermal.maxTemp.round()} C',
          ),
          onChanged: thermal.autoRange
              ? null
              : (values) {
                  ref
                      .read(thermalProvider.notifier)
                      .setTemperatureRange(values.start, values.end);
                },
        ),
        Row(
          children: [
            Expanded(
              child: StatusCard(
                title: 'Frame Min',
                value: frame == null
                    ? '--'
                    : '${frame.minTemperature.toStringAsFixed(1)} C',
                icon: Icons.south_rounded,
                accentColor: Colors.lightBlueAccent,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: StatusCard(
                title: 'Frame Max',
                value: frame == null
                    ? '--'
                    : '${frame.maxTemperature.toStringAsFixed(1)} C',
                icon: Icons.north_rounded,
                accentColor: Colors.deepOrangeAccent,
              ),
            ),
          ],
        ),
        StatusCard(
          title: 'Tapped Pixel',
          value: thermal.selectedTemperature == null
              ? 'Tap the image'
              : 'x${thermal.selectedX}, y${thermal.selectedY}: '
                    '${thermal.selectedTemperature!.toStringAsFixed(1)} C',
          icon: Icons.ads_click_rounded,
          accentColor: Colors.greenAccent,
        ),
        StatusCard(
          title: 'Human Detection',
          value: thermal.humanDetection.detected
              ? 'Blob ${thermal.humanDetection.blob?.width}x'
                    '${thermal.humanDetection.blob?.height}, '
                    'avg ${thermal.humanDetection.averageTemperature?.toStringAsFixed(1)} C'
              : 'No 30-40 C human-shaped blob',
          icon: Icons.accessibility_new_rounded,
          accentColor: thermal.humanDetected ? Colors.greenAccent : Colors.grey,
        ),
      ],
    );
  }

  Future<void> _saveScreenshot() async {
    try {
      final boundary =
          _captureKey.currentContext?.findRenderObject()
              as RenderRepaintBoundary?;
      if (boundary == null) {
        throw StateError('Thermal view is not ready.');
      }
      final image = await boundary.toImage(pixelRatio: 2);
      final byteData = await image.toByteData(format: ui.ImageByteFormat.png);
      final pngBytes = byteData?.buffer.asUint8List();
      if (pngBytes == null) {
        throw StateError('Could not encode screenshot.');
      }
      await Gal.putImageBytes(
        pngBytes,
        album: 'Thermal Monitor',
        name: 'thermal_${DateTime.now().millisecondsSinceEpoch}',
      );
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Thermal screenshot saved')));
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Screenshot failed: $error')));
    }
  }
}

class StatusChip extends StatelessWidget {
  const StatusChip({super.key, required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Chip(avatar: Icon(icon, size: 18), label: Text(label));
  }
}
