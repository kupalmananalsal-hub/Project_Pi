import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:thermal_audio_monitor/main.dart';
import 'package:thermal_audio_monitor/models/alert_event.dart';
import 'package:thermal_audio_monitor/models/app_settings.dart';
import 'package:thermal_audio_monitor/models/audio_frame.dart';
import 'package:thermal_audio_monitor/models/thermal_frame.dart';
import 'package:thermal_audio_monitor/providers/alerts_provider.dart';
import 'package:thermal_audio_monitor/providers/app_services_provider.dart';
import 'package:thermal_audio_monitor/providers/connection_provider.dart';
import 'package:thermal_audio_monitor/providers/controls_provider.dart';
import 'package:thermal_audio_monitor/providers/audio_provider.dart';
import 'package:thermal_audio_monitor/providers/thermal_provider.dart';
import 'package:thermal_audio_monitor/services/reconnecting_web_socket_service.dart';
import 'package:thermal_audio_monitor/services/alert_runtime_service.dart';
import 'package:thermal_audio_monitor/widgets/alert_overlay.dart';
import 'package:thermal_audio_monitor/widgets/thermal_display.dart';

class _UiConnection extends ConnectionController {
  _UiConnection(this.initial);
  final PiConnectionState initial;
  @override
  PiConnectionState build() => initial;
}

class _UiControls extends ControlsController {
  @override
  ControlsState build() => const ControlsState();
  void publishPattern(LedPattern pattern) =>
      state = state.copyWith(pattern: pattern);
}

class _UiAudio extends AudioController {
  _UiAudio(this.initial);
  final AudioState initial;
  @override
  AudioState build() => initial;
}

class _UiThermal extends ThermalController {
  _UiThermal(this.initial);
  final ThermalState initial;
  @override
  ThermalState build() => initial;
}

class _SilentRuntime extends AlertRuntimeService {
  @override
  Future<void> initialize() async {}
  @override
  Future<void> startEmergency(
    AlertEvent event,
    AlertSound sound, {
    bool vibrate = true,
  }) async {}
  @override
  Future<void> stopEmergency() async {}
  @override
  Future<void> dispose() async {}
}

void main() {
  setUpAll(() async {
    const fonts = String.fromEnvironment('UI_FONT_DIR');
    if (fonts.isEmpty) return;
    for (final font in {
      'Roboto': 'roboto-regular.ttf',
      'MaterialIcons': 'materialicons-regular.otf',
    }.entries) {
      final bytes = await File('$fonts/${font.value}').readAsBytes();
      final loader = FontLoader(font.key)
        ..addFont(Future.value(ByteData.sublistView(bytes)));
      await loader.load();
    }
  });
  setUp(() => SharedPreferences.setMockInitialValues({}));

  Future<ProviderContainer> pumpApp(
    WidgetTester tester, {
    List overrides = const [],
  }) async {
    final container = ProviderContainer(
      overrides: [
        piAutoConnectProvider.overrideWithValue(false),
        controlsProvider.overrideWith(_UiControls.new),
        alertRuntimeServiceProvider.overrideWithValue(_SilentRuntime()),
        ...overrides,
      ],
    );
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: RepaintBoundary(
          key: const ValueKey('ui-capture'),
          child: const ThermalAudioMonitorApp(),
        ),
      ),
    );
    await tester.pump();
    addTearDown(container.dispose);
    return container;
  }

  Future<void> capture(WidgetTester tester, String name) async {
    const output = String.fromEnvironment('UI_PREVIEW_DIR');
    if (output.isEmpty) return;
    await tester.pump(const Duration(milliseconds: 300));
    final boundary = tester.renderObject<RenderRepaintBoundary>(
      find.byKey(const ValueKey('ui-capture')),
    );
    await tester.runAsync(() async {
      final image = await boundary.toImage();
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      await Directory(output).create(recursive: true);
      await File('$output/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
      image.dispose();
    });
  }

  testWidgets(
    'only Monitor History Controls remain and removed features are absent',
    (tester) async {
      await pumpApp(tester);
      expect(
        tester.widget<NavigationBar>(find.byType(NavigationBar)).destinations,
        hasLength(3),
      );
      expect(find.text('Training'), findsNothing);
      expect(find.text('PART'), findsNothing);
      expect(find.text('Simulate distress call'), findsNothing);
      await tester.tap(find.text('History').last);
      await tester.pump();
      expect(find.text('Recent Alerts'), findsOneWidget);
      await tester.tap(find.text('Controls').last);
      await tester.pump();
      expect(find.text('Refresh KWS Service'), findsNothing);
      expect(find.text('System Status'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  testWidgets('phone and tablet layouts remain usable with enlarged text', (
    tester,
  ) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    tester.view.devicePixelRatio = 1;
    for (final width in [320.0, 900.0]) {
      tester.view.physicalSize = Size(width, 900);
      tester.platformDispatcher.textScaleFactorTestValue = 1.6;
      await pumpApp(tester);
      expect(tester.takeException(), isNull);
      for (final tab in ['History', 'Controls', 'Monitor']) {
        await tester.tap(find.text(tab).last);
        await tester.pump();
        expect(tester.takeException(), isNull, reason: '$tab at $width');
      }
      expect(
        find.byType(NavigationRail),
        width >= 840 ? findsOneWidget : findsNothing,
      );
      await tester.pumpWidget(const SizedBox.shrink());
    }
  });

  testWidgets(
    'critical alert still overlays Controls and can be acknowledged',
    (tester) async {
      final container = await pumpApp(tester);
      await tester.tap(find.text('Controls').last);
      await tester.pump();
      container
          .read(alertsProvider.notifier)
          .handleAlertForTest(
            AlertEvent.fromMessage({
              'event_id': 'c158-critical',
              'event': 'keyword_detected',
              'keyword': 'help',
              'confidence': .95,
              'alert_level': 'full_alert',
              'decision_state': 'critical',
              'thermal_state': 'negative',
              'alert_modality': 'voice_only',
              'timestamp': DateTime.now().toIso8601String(),
            }),
          );
      await tester.pump();
      expect(find.byType(AlertOverlay), findsOneWidget);
      expect(find.text('EMERGENCY ALERT'), findsOneWidget);
      await capture(tester, 'critical-overlay-800');
      await tester.ensureVisible(find.text('Dismiss Alert'));
      await tester.tap(find.text('Dismiss Alert'));
      await tester.pump();
      expect(find.byType(AlertOverlay), findsNothing);
      expect(container.read(alertsProvider).history, hasLength(1));
      await tester.pump(const Duration(seconds: 4));
      await tester.tap(find.text('History').last);
      await tester.pump();
      await capture(tester, 'history-alert-800');
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  testWidgets('capture offline phone and tablet states', (tester) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    tester.view.devicePixelRatio = 1;
    for (final width in [390.0, 1000.0]) {
      tester.view.physicalSize = Size(width, 900);
      await pumpApp(tester);
      await tester.pump(const Duration(milliseconds: 300));
      await capture(tester, 'monitor-${width.toInt()}');
      await tester.tap(find.text('History').last);
      await tester.pump();
      await capture(tester, 'history-${width.toInt()}');
      await tester.tap(find.text('Controls').last);
      await tester.pump();
      await capture(tester, 'controls-${width.toInt()}');
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    }
  });

  testWidgets('connecting and disconnected states do not imply live sensors', (
    tester,
  ) async {
    await pumpApp(
      tester,
      overrides: [
        connectionProvider.overrideWith(
          () => _UiConnection(PiConnectionState(isConnecting: true)),
        ),
      ],
    );
    expect(find.text('Connecting'), findsOneWidget);
    expect(find.text('WAITING FOR AUDIO'), findsOneWidget);
    expect(find.text('No live stream'), findsOneWidget);
    expect(find.text('PART'), findsNothing);
    expect(find.text('LISTENING'), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets(
    'live synthetic streams preserve microphone levels and thermal selection',
    (tester) async {
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1000, 1000);
      final frame = ThermalFrame(
        width: 8,
        height: 6,
        pixels: List.generate(48, (i) => 23 + (i % 8) * 1.8),
        timestamp: DateTime.utc(2026),
      );
      await pumpApp(
        tester,
        overrides: [
          connectionProvider.overrideWith(
            () => _UiConnection(PiConnectionState(isConnected: true)),
          ),
          audioProvider.overrideWith(
            () => _UiAudio(
              AudioState(
                socketStatus: SocketConnectionStatus.connected,
                latest: AudioFrame(
                  leftRms: .35,
                  rightRms: .7,
                  direction: 'right',
                  timestamp: DateTime.utc(2026),
                ),
              ),
            ),
          ),
          thermalProvider.overrideWith(
            () => _UiThermal(
              ThermalState(
                frame: frame,
                colorMap: ThermalColorMap.inferno,
                socketStatus: SocketConnectionStatus.connected,
              ),
            ),
          ),
        ],
      );
      expect(find.text('LISTENING'), findsOneWidget);
      expect(find.text('Live input levels'), findsOneWidget);
      expect(
        tester.widget<ThermalDisplay>(find.byType(ThermalDisplay)).colorMap,
        ThermalColorMap.inferno,
      );
      await tester.tap(find.byType(ThermalDisplay));
      await tester.pump();
      expect(find.text('SELECTED PIXEL'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await capture(tester, 'monitor-live-1000');
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  testWidgets(
    'sensor failures never look like live microphone or thermal data',
    (tester) async {
      final frame = ThermalFrame(
        width: 2,
        height: 2,
        pixels: const [23, 25, 30, 34],
        timestamp: DateTime.utc(2026),
      );
      await pumpApp(
        tester,
        overrides: [
          audioProvider.overrideWith(
            () => _UiAudio(
              AudioState(
                socketStatus: SocketConnectionStatus.connected,
                latest: AudioFrame(
                  leftRms: 0,
                  rightRms: 0,
                  direction: 'right',
                  error: 'Microphone read failed',
                  timestamp: DateTime.utc(2026),
                ),
              ),
            ),
          ),
          thermalProvider.overrideWith(
            () => _UiThermal(
              ThermalState(
                frame: frame,
                socketStatus: SocketConnectionStatus.connected,
                error: 'Thermal read failed',
              ),
            ),
          ),
        ],
      );
      expect(find.text('LISTENING'), findsNothing);
      expect(find.text('Live input levels'), findsNothing);
      expect(find.text('Scanning'), findsNothing);
      expect(find.text('Sensor unavailable'), findsOneWidget);
      expect(find.text('NO DIRECTION'), findsOneWidget);
      expect(
        find.text('Stream disconnected. Showing the last received frame.'),
        findsNothing,
      );
      await capture(tester, 'monitor-sensor-error-800');
      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  testWidgets('compact pattern selection follows external state changes', (
    tester,
  ) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(390, 900);
    final container = await pumpApp(tester);
    await tester.tap(find.text('Controls').last);
    await tester.pump();
    final controls = container.read(controlsProvider.notifier) as _UiControls;
    controls.publishPattern(LedPattern.breathing);
    await tester.pump();
    expect(
      tester
          .widget<DropdownButton<LedPattern>>(
            find.byType(DropdownButton<LedPattern>),
          )
          .value,
      LedPattern.breathing,
    );
    controls.publishPattern(LedPattern.solid);
    await tester.pump();
    expect(
      tester
          .widget<DropdownButton<LedPattern>>(
            find.byType(DropdownButton<LedPattern>),
          )
          .value,
      LedPattern.solid,
    );
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('palette has named selected-state semantics and 48dp targets', (
    tester,
  ) async {
    final semantics = tester.ensureSemantics();
    try {
      await pumpApp(tester);
      await tester.tap(find.text('Controls').last);
      await tester.pump();
      await tester.ensureVisible(find.byKey(const ValueKey('light-color-red')));
      await tester.pump();
      expect(find.bySemanticsLabel('Red light color'), findsOneWidget);
      expect(
        tester.getSize(find.byKey(const ValueKey('light-color-red'))),
        const Size(48, 48),
      );
      await tester.pumpWidget(const SizedBox.shrink());
    } finally {
      semantics.dispose();
    }
  });
}
