import 'package:flutter/material.dart';
import 'package:flutter_colorpicker/flutter_colorpicker.dart';

import '../providers/controls_provider.dart';

class LedControl extends StatelessWidget {
  const LedControl({
    super.key,
    required this.selectedLed,
    required this.ledColors,
    required this.brightness,
    required this.pattern,
    required this.onLedSelected,
    required this.onColorChanged,
    required this.onBrightnessChanged,
    required this.onPatternChanged,
  });

  final int selectedLed;
  final List<Color> ledColors;
  final double brightness;
  final LedPattern pattern;
  final ValueChanged<int> onLedSelected;
  final ValueChanged<Color> onColorChanged;
  final ValueChanged<double> onBrightnessChanged;
  final ValueChanged<LedPattern> onPatternChanged;

  @override
  Widget build(BuildContext context) {
    final selectedColor = ledColors[selectedLed];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SegmentedButton<int>(
          segments: const [
            ButtonSegment(
              value: 0,
              icon: Icon(Icons.looks_one_rounded),
              tooltip: 'Indicator 1',
            ),
            ButtonSegment(
              value: 1,
              icon: Icon(Icons.looks_two_rounded),
              tooltip: 'Indicator 2',
            ),
            ButtonSegment(
              value: 2,
              icon: Icon(Icons.looks_3_rounded),
              tooltip: 'Indicator 3',
            ),
          ],
          selected: {selectedLed},
          onSelectionChanged: (selection) => onLedSelected(selection.first),
        ),
        const SizedBox(height: 16),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: List.generate(3, (index) {
            final color = ledColors[index];
            return InkWell(
              borderRadius: BorderRadius.circular(8),
              onTap: () => onLedSelected(index),
              child: Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: color,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: index == selectedLed
                        ? Theme.of(context).colorScheme.primary
                        : Theme.of(context).dividerColor,
                    width: index == selectedLed ? 3 : 1,
                  ),
                ),
              ),
            );
          }),
        ),
        const SizedBox(height: 18),
        BlockPicker(
          pickerColor: selectedColor,
          onColorChanged: onColorChanged,
          itemBuilder: (color, selected, changeColor) {
            final name = _colorName(color);
            final foreground =
                ThemeData.estimateBrightnessForColor(color) == Brightness.dark
                ? Colors.white
                : Colors.black;
            return Semantics(
              label: '$name light color',
              button: true,
              selected: selected,
              child: Tooltip(
                message: name,
                excludeFromSemantics: true,
                child: SizedBox.square(
                  key: ValueKey('light-color-${name.toLowerCase()}'),
                  dimension: 48,
                  child: Material(
                    color: color,
                    borderRadius: BorderRadius.circular(12),
                    child: InkWell(
                      onTap: changeColor,
                      borderRadius: BorderRadius.circular(12),
                      child: selected
                          ? Icon(Icons.check_rounded, color: foreground)
                          : const SizedBox.expand(),
                    ),
                  ),
                ),
              ),
            );
          },
          availableColors: const [
            Colors.red,
            Colors.deepOrange,
            Colors.amber,
            Colors.yellow,
            Colors.lightGreenAccent,
            Colors.greenAccent,
            Colors.cyanAccent,
            Colors.lightBlueAccent,
            Colors.blueAccent,
            Colors.purpleAccent,
            Colors.pinkAccent,
            Colors.white,
          ],
          layoutBuilder: (context, colors, child) {
            return Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [for (final color in colors) child(color)],
            );
          },
        ),
        const SizedBox(height: 18),
        Text('Brightness', style: Theme.of(context).textTheme.labelLarge),
        Slider(
          value: brightness,
          min: 0,
          max: 1,
          divisions: 20,
          label: '${(brightness * 100).round()}%',
          onChanged: onBrightnessChanged,
        ),
        const SizedBox(height: 8),
        LayoutBuilder(
          builder: (context, constraints) {
            if (constraints.maxWidth < 440 ||
                MediaQuery.textScalerOf(context).scale(1) > 1.3) {
              return InputDecorator(
                decoration: const InputDecoration(labelText: 'Light pattern'),
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<LedPattern>(
                    isExpanded: true,
                    value: pattern,
                    items: [
                      for (final item in LedPattern.values)
                        DropdownMenuItem(value: item, child: Text(item.label)),
                    ],
                    onChanged: (value) {
                      if (value != null) onPatternChanged(value);
                    },
                  ),
                ),
              );
            }
            return SegmentedButton<LedPattern>(
              segments: [
                for (final item in LedPattern.values)
                  ButtonSegment(
                    value: item,
                    label: Text(item.label),
                    icon: Icon(_patternIcon(item)),
                  ),
              ],
              selected: {pattern},
              onSelectionChanged: (selection) =>
                  onPatternChanged(selection.first),
            );
          },
        ),
      ],
    );
  }

  IconData _patternIcon(LedPattern pattern) {
    switch (pattern) {
      case LedPattern.solid:
        return Icons.circle_rounded;
      case LedPattern.breathing:
        return Icons.blur_on_rounded;
      case LedPattern.rainbow:
        return Icons.gradient_rounded;
    }
  }

  String _colorName(Color color) =>
      <Color, String>{
        Colors.red: 'Red',
        Colors.deepOrange: 'Orange',
        Colors.amber: 'Amber',
        Colors.yellow: 'Yellow',
        Colors.lightGreenAccent: 'Lime',
        Colors.greenAccent: 'Green',
        Colors.cyanAccent: 'Cyan',
        Colors.lightBlueAccent: 'Light blue',
        Colors.blueAccent: 'Blue',
        Colors.purpleAccent: 'Purple',
        Colors.pinkAccent: 'Pink',
        Colors.white: 'White',
      }[color] ??
      'Custom';
}
