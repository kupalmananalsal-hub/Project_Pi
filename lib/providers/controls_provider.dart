import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/button_event.dart';
import '../services/pi_api_service.dart';
import 'connection_provider.dart';

final controlsProvider = NotifierProvider<ControlsController, ControlsState>(
  ControlsController.new,
);

enum LedPattern { solid, breathing, rainbow }

extension LedPatternLabel on LedPattern {
  String get label {
    switch (this) {
      case LedPattern.solid:
        return 'Solid';
      case LedPattern.breathing:
        return 'Breathing';
      case LedPattern.rainbow:
        return 'Rainbow';
    }
  }
}

class ControlsState {
  const ControlsState({
    this.selectedLed = 0,
    this.ledColors = const [
      Color(0xFF00E676),
      Color(0xFFFFD54F),
      Color(0xFFFF5252),
    ],
    this.brightness = 1,
    this.pattern = LedPattern.solid,
    this.buttonEvent,
    this.isBusy = false,
    this.error,
  });

  final int selectedLed;
  final List<Color> ledColors;
  final double brightness;
  final LedPattern pattern;
  final ButtonEvent? buttonEvent;
  final bool isBusy;
  final String? error;

  ControlsState copyWith({
    int? selectedLed,
    List<Color>? ledColors,
    double? brightness,
    LedPattern? pattern,
    Object? buttonEvent = _unset,
    bool? isBusy,
    Object? error = _unset,
  }) {
    return ControlsState(
      selectedLed: selectedLed ?? this.selectedLed,
      ledColors: ledColors ?? this.ledColors,
      brightness: brightness ?? this.brightness,
      pattern: pattern ?? this.pattern,
      buttonEvent: buttonEvent == _unset
          ? this.buttonEvent
          : buttonEvent as ButtonEvent?,
      isBusy: isBusy ?? this.isBusy,
      error: error == _unset ? this.error : error as String?,
    );
  }
}

class ControlsController extends Notifier<ControlsState> {
  Timer? _patternTimer;
  Timer? _buttonTimer;
  double _phase = 0;

  @override
  ControlsState build() {
    ref.listen(connectionProvider, (_, next) {
      if (next.isConnected) {
        _startButtonPolling();
        _sendCurrentPattern();
      } else {
        _stopButtonPolling();
      }
    });

    ref.onDispose(() {
      _patternTimer?.cancel();
      _buttonTimer?.cancel();
    });

    if (ref.read(connectionProvider).isConnected) {
      _startButtonPolling();
    }

    return const ControlsState();
  }

  void selectLed(int led) {
    state = state.copyWith(selectedLed: led.clamp(0, 2));
  }

  Future<void> setLedColor(Color color) async {
    final colors = [...state.ledColors];
    colors[state.selectedLed] = color;
    state = state.copyWith(ledColors: colors, pattern: LedPattern.solid);
    _patternTimer?.cancel();
    await _sendLed(state.selectedLed, color, state.brightness);
  }

  Future<void> setBrightness(double brightness) async {
    state = state.copyWith(brightness: brightness.clamp(0.0, 1.0));
    await _sendCurrentPattern();
  }

  Future<void> setPattern(LedPattern pattern) async {
    state = state.copyWith(pattern: pattern);
    _patternTimer?.cancel();
    if (pattern == LedPattern.solid) {
      await _sendAll(state.ledColors, state.brightness);
      return;
    }
    _phase = 0;
    _patternTimer = Timer.periodic(const Duration(milliseconds: 220), (_) {
      _tickPattern();
    });
    await _sendCurrentPattern();
  }

  Future<void> refreshButton() async {
    final connection = ref.read(connectionProvider);
    if (!connection.isConnected) {
      return;
    }
    try {
      final event = await PiApiService(
        host: connection.host,
        port: connection.port,
      ).fetchButton();
      state = state.copyWith(buttonEvent: event, error: null);
    } catch (error) {
      state = state.copyWith(error: error.toString());
    }
  }

  Future<bool> shutdown() async {
    return _postPowerAction((api) => api.shutdown());
  }

  Future<bool> reboot() async {
    return _postPowerAction((api) => api.reboot());
  }

  Future<bool> refreshKws({bool gitPull = false}) async {
    final connection = ref.read(connectionProvider);
    if (!connection.isConnected) {
      state = state.copyWith(error: 'Connect to the Pi first.');
      return false;
    }
    state = state.copyWith(isBusy: true, error: null);
    try {
      final result = await PiApiService(
        host: connection.host,
        port: connection.port,
      ).refreshServices(gitPull: gitPull);
      final ok = result['ok'] == true;
      if (!ok) {
        final stderr = result['stderr']?.toString() ?? '';
        final stdout = result['stdout']?.toString() ?? '';
        state = state.copyWith(
          isBusy: false,
          error: stderr.isNotEmpty
              ? stderr
              : (stdout.isNotEmpty ? stdout : 'Refresh failed.'),
        );
        return false;
      }
      state = state.copyWith(isBusy: false, error: null);
      return true;
    } catch (error) {
      state = state.copyWith(isBusy: false, error: error.toString());
      return false;
    }
  }

  void _startButtonPolling() {
    _buttonTimer?.cancel();
    _buttonTimer = Timer.periodic(
      const Duration(seconds: 2),
      (_) => refreshButton(),
    );
    unawaited(refreshButton());
  }

  void _stopButtonPolling() {
    _buttonTimer?.cancel();
    _buttonTimer = null;
  }

  Future<bool> _postPowerAction(
    Future<void> Function(PiApiService api) action,
  ) async {
    final connection = ref.read(connectionProvider);
    if (!connection.isConnected) {
      state = state.copyWith(error: 'Connect to the Pi first.');
      return false;
    }
    state = state.copyWith(isBusy: true, error: null);
    try {
      await action(PiApiService(host: connection.host, port: connection.port));
      state = state.copyWith(isBusy: false);
      return true;
    } catch (error) {
      state = state.copyWith(isBusy: false, error: error.toString());
      return false;
    }
  }

  Future<void> _sendCurrentPattern() async {
    switch (state.pattern) {
      case LedPattern.solid:
        await _sendAll(state.ledColors, state.brightness);
      case LedPattern.breathing:
        final scaled = state.ledColors
            .map((color) => color)
            .toList(growable: false);
        await _sendAll(scaled, _breathingBrightness());
      case LedPattern.rainbow:
        await _sendAll(_rainbowColors(), state.brightness);
    }
  }

  void _tickPattern() {
    _phase += 0.08;
    unawaited(_sendCurrentPattern());
  }

  double _breathingBrightness() {
    final wave = (math.sin(_phase) + 1) / 2;
    return (0.12 + (wave * 0.88)) * state.brightness;
  }

  List<Color> _rainbowColors() {
    return List.generate(3, (index) {
      final hue = ((_phase * 70) + (index * 120)) % 360;
      return HSVColor.fromAHSV(1, hue, 0.95, 1).toColor();
    });
  }

  Future<void> _sendAll(List<Color> colors, double brightness) async {
    for (var led = 0; led < 3; led++) {
      await _sendLed(led, colors[led], brightness);
    }
  }

  Future<void> _sendLed(int led, Color color, double brightness) async {
    final connection = ref.read(connectionProvider);
    if (!connection.isConnected) {
      return;
    }
    final factor = brightness.clamp(0.0, 1.0);
    try {
      await PiApiService(host: connection.host, port: connection.port).setLed(
        led: led,
        r: (color.r * 255 * factor).round(),
        g: (color.g * 255 * factor).round(),
        b: (color.b * 255 * factor).round(),
      );
      state = state.copyWith(error: null);
    } catch (error) {
      state = state.copyWith(error: error.toString());
    }
  }
}

const _unset = Object();
