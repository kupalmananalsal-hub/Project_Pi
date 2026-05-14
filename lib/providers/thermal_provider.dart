import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/thermal_frame.dart';
import '../services/reconnecting_web_socket_service.dart';

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

  ThermalState copyWith({
    Object? frame = _unset,
    SocketConnectionStatus? socketStatus,
    ThermalColorMap? colorMap,
    double? minTemp,
    double? maxTemp,
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
      uri: Uri(scheme: 'ws', host: host, port: port, path: '/ws/thermal'),
      parser: ThermalFrame.fromMessage,
    );
    _frameSubscription = _socket!.messages.listen(
      (frame) {
        _framesThisSecond++;
        state = state.copyWith(frame: frame, error: null);
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
      state = state.copyWith(socketStatus: SocketConnectionStatus.disconnected);
    }
  }
}

const _unset = Object();
