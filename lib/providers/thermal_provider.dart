import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/app_settings.dart';
import '../models/thermal_frame.dart';
import '../services/reconnecting_web_socket_service.dart';
import '../utils/human_detector.dart';

final thermalProvider = NotifierProvider<ThermalController, ThermalState>(
  ThermalController.new,
);

class ThermalState {
  const ThermalState({
    this.frame,
    this.socketStatus = SocketConnectionStatus.disconnected,
    this.colorMap = ThermalColorMap.jet,
    this.minTemp = 20,
    this.maxTemp = 45,
    this.autoRange = true,
    this.humanDetection = const HumanDetectionResult(detected: false),
    this.selectedX,
    this.selectedY,
    this.fps = 0,
    this.error,
  });

  final ThermalFrame? frame;
  final SocketConnectionStatus socketStatus;
  final ThermalColorMap colorMap;
  final double minTemp;
  final double maxTemp;
  final bool autoRange;
  final HumanDetectionResult humanDetection;
  final int? selectedX;
  final int? selectedY;
  final double fps;
  final String? error;

  double? get selectedTemperature {
    final currentFrame = frame;
    if (currentFrame == null || selectedX == null || selectedY == null) {
      return null;
    }
    return currentFrame.temperatureAt(selectedX!, selectedY!);
  }

  bool get humanDetected => humanDetection.detected;

  double get displayMinTemp => autoRange && frame != null
      ? frame!.clippedTemperatureRange().min
      : minTemp;

  double get displayMaxTemp => autoRange && frame != null
      ? frame!.clippedTemperatureRange().max
      : maxTemp;

  ThermalState copyWith({
    Object? frame = _unset,
    SocketConnectionStatus? socketStatus,
    ThermalColorMap? colorMap,
    double? minTemp,
    double? maxTemp,
    bool? autoRange,
    HumanDetectionResult? humanDetection,
    Object? selectedX = _unset,
    Object? selectedY = _unset,
    double? fps,
    Object? error = _unset,
  }) {
    return ThermalState(
      frame: frame == _unset ? this.frame : frame as ThermalFrame?,
      socketStatus: socketStatus ?? this.socketStatus,
      colorMap: colorMap ?? this.colorMap,
      minTemp: minTemp ?? this.minTemp,
      maxTemp: maxTemp ?? this.maxTemp,
      autoRange: autoRange ?? this.autoRange,
      humanDetection: humanDetection ?? this.humanDetection,
      selectedX: selectedX == _unset ? this.selectedX : selectedX as int?,
      selectedY: selectedY == _unset ? this.selectedY : selectedY as int?,
      fps: fps ?? this.fps,
      error: error == _unset ? this.error : error as String?,
    );
  }
}

class ThermalController extends Notifier<ThermalState> {
  ReconnectingWebSocketService<ThermalFrame>? _socket;
  StreamSubscription<ThermalFrame>? _frameSubscription;
  StreamSubscription<SocketConnectionStatus>? _statusSubscription;
  Timer? _fpsTimer;
  int _framesThisSecond = 0;

  @override
  ThermalState build() {
    ref.onDispose(disconnect);
    return const ThermalState();
  }

  void connect(String host, int port) {
    disconnect();
    _socket = ReconnectingWebSocketService<ThermalFrame>(
      uri: Uri(
        scheme: 'ws',
        host: host,
        port: AppSettings.normalizeBackendPort(port),
        path: '/ws/thermal',
      ),
      parser: ThermalFrame.fromMessage,
    );
    _frameSubscription = _socket!.messages.listen(
      (frame) {
        _framesThisSecond++;
        final detection = HumanDetector.fromThermalFrame(frame);
        state = state.copyWith(
          frame: frame,
          humanDetection: detection,
          error: null,
        );
      },
      onError: (Object error) {
        state = state.copyWith(error: error.toString());
      },
    );
    _statusSubscription = _socket!.status.listen((status) {
      state = state.copyWith(socketStatus: status);
    });
    _fpsTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      state = state.copyWith(fps: _framesThisSecond.toDouble());
      _framesThisSecond = 0;
    });
    _socket!.connect();
  }

  void setColorMap(ThermalColorMap colorMap) {
    state = state.copyWith(colorMap: colorMap);
  }

  void setTemperatureRange(double minTemp, double maxTemp) {
    state = state.copyWith(minTemp: minTemp, maxTemp: maxTemp);
  }

  void setAutoRange(bool enabled) {
    state = state.copyWith(autoRange: enabled);
  }

  void selectPixel(int x, int y) {
    state = state.copyWith(selectedX: x, selectedY: y);
  }

  void disconnect() {
    _fpsTimer?.cancel();
    _fpsTimer = null;
    _frameSubscription?.cancel();
    _frameSubscription = null;
    _statusSubscription?.cancel();
    _statusSubscription = null;
    _socket?.disconnect();
    _socket = null;
    if (ref.mounted) {
      state = state.copyWith(
        frame: null,
        humanDetection: const HumanDetectionResult(detected: false),
        selectedX: null,
        selectedY: null,
        fps: 0,
        socketStatus: SocketConnectionStatus.disconnected,
      );
    }
  }
}

const _unset = Object();
