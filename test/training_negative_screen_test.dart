import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:thermal_audio_monitor/models/training_keyword.dart';
import 'package:thermal_audio_monitor/providers/connection_provider.dart';
import 'package:thermal_audio_monitor/providers/training_provider.dart';
import 'package:thermal_audio_monitor/screens/training_screen.dart';

class Connected extends ConnectionController {
  @override
  PiConnectionState build() => PiConnectionState(isConnected: true);
}

class TrainingFixture extends TrainingNotifier {
  @override
  TrainingState build() =>
      const TrainingState(keywords: fallbackTrainingKeywords);
  @override
  Future<void> initialize() async {}
  @override
  void cancelPendingRecording() {}
}

void main() {
  testWidgets(
    'negative mode offers non-keywords without relabeling positives',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(1200, 2400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            connectionProvider.overrideWith(Connected.new),
            trainingProvider.overrideWith(TrainingFixture.new),
          ],
          child: const MaterialApp(home: Scaffold(body: TrainingScreen())),
        ),
      );
      await tester.pumpAndSettle();
      final type = find.widgetWithText(
        DropdownButtonFormField<String>,
        'Positive distress keyword',
      );
      await tester.ensureVisible(type);
      await tester.tap(type);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Negative — must not trigger').last);
      await tester.pumpAndSettle();
      expect(find.text('hello (en)'), findsOneWidget);
      expect(
        find.textContaining('Do not say a distress keyword'),
        findsOneWidget,
      );
      await tester.tap(find.text('hello (en)'));
      await tester.pumpAndSettle();
      expect(find.text('helmet (en)'), findsWidgets);
      expect(find.text('help (en)'), findsNothing);
      await tester.tap(find.text('helmet (en)').last);
      await tester.pumpAndSettle();
      expect(find.text('helmet (en)'), findsOneWidget);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
  testWidgets(
    'positive keyword fixes language while negatives allow explicit language',
    (tester) async {
      await tester.binding.setSurfaceSize(const Size(1200, 2400));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            connectionProvider.overrideWith(Connected.new),
            trainingProvider.overrideWith(TrainingFixture.new),
          ],
          child: const MaterialApp(home: Scaffold(body: TrainingScreen())),
        ),
      );
      await tester.pumpAndSettle();
      final keyword = find.byKey(const ValueKey('positive'));
      await tester.ensureVisible(keyword);
      await tester.tap(keyword);
      await tester.pumpAndSettle();
      await tester.tap(find.text('tulong (fil)').last);
      await tester.pumpAndSettle();
      final filipino = tester.widget<DropdownButtonFormField<String>>(
        find.byKey(const ValueKey('language-positive-fil')),
      );
      expect(filipino.initialValue, 'fil');
      expect(filipino.onChanged, isNull);
      await tester.tap(keyword);
      await tester.pumpAndSettle();
      await tester.tap(find.text('help (en)').last);
      await tester.pumpAndSettle();
      expect(
        find.byKey(const ValueKey('language-positive-en')),
        findsOneWidget,
      );
      await tester.tap(
        find.widgetWithText(
          DropdownButtonFormField<String>,
          'Positive distress keyword',
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Negative — must not trigger').last);
      await tester.pumpAndSettle();
      final language = find.byKey(const ValueKey('language-negative-en'));
      expect(
        tester.widget<DropdownButtonFormField<String>>(language).onChanged,
        isNotNull,
      );
      await tester.tap(language);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Cebuano / Bisaya').last);
      await tester.pumpAndSettle();
      expect(find.text('hello (ceb)'), findsOneWidget);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );
}
