import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/app_settings.dart';
import '../models/noise_suppression_settings.dart';
import '../services/noise_suppression_service.dart';

final noiseSuppressionProvider =
    NotifierProvider<NoiseSuppressionController, NoiseSuppressionState>(
      NoiseSuppressionController.new,
    );

class NoiseSuppressionState {
  const NoiseSuppressionState({
    this.settings = const NoiseSuppressionSettings.defaults(),
    this.connectedHost,
    this.connectedPort,
    this.loading = false,
    this.saving = false,
    this.error,
  });

  final NoiseSuppressionSettings settings;
  final String? connectedHost;
  final int? connectedPort;
  final bool loading;
  final bool saving;
  final String? error;

  bool get isConnected => connectedHost != null && connectedPort != null;

  NoiseSuppressionState copyWith({
    NoiseSuppressionSettings? settings,
    Object? connectedHost = _unset,
    Object? connectedPort = _unset,
    bool? loading,
    bool? saving,
    Object? error = _unset,
  }) {
    return NoiseSuppressionState(
      settings: settings ?? this.settings,
      connectedHost: connectedHost == _unset
          ? this.connectedHost
          : connectedHost as String?,
      connectedPort: connectedPort == _unset
          ? this.connectedPort
          : connectedPort as int?,
      loading: loading ?? this.loading,
      saving: saving ?? this.saving,
      error: error == _unset ? this.error : error as String?,
    );
  }
}

class NoiseSuppressionController extends Notifier<NoiseSuppressionState> {
  @override
  NoiseSuppressionState build() {
    return const NoiseSuppressionState();
  }

  Future<void> connect(String host, int port) async {
    final normalizedPort = AppSettings.normalizeBackendPort(port);
    if (state.connectedHost == host &&
        state.connectedPort == normalizedPort &&
        !state.loading) {
      await refresh();
      return;
    }

    state = state.copyWith(
      connectedHost: host,
      connectedPort: normalizedPort,
      loading: true,
      error: null,
    );

    try {
      final settings = await _service(host, normalizedPort).fetchSettings();
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(settings: settings, loading: false, error: null);
    } catch (error) {
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(loading: false, error: error.toString());
    }
  }

  void disconnect() {
    state = state.copyWith(
      connectedHost: null,
      connectedPort: null,
      loading: false,
      saving: false,
      error: null,
    );
  }

  Future<void> refresh() async {
    final host = state.connectedHost;
    final port = state.connectedPort;
    if (host == null || port == null) {
      return;
    }
    state = state.copyWith(loading: true, error: null);
    try {
      final settings = await _service(host, port).fetchSettings();
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(settings: settings, loading: false, error: null);
    } catch (error) {
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(loading: false, error: error.toString());
    }
  }

  Future<void> update({
    bool? active,
    double? strength,
    double? sensitivity,
    double? snowboySensitivity,
  }) async {
    final host = state.connectedHost;
    final port = state.connectedPort;
    if (host == null || port == null) {
      return;
    }
    final next = state.settings.copyWith(
      active: active,
      strength: strength,
      sensitivity: sensitivity,
      snowboySensitivity: snowboySensitivity,
    );
    state = state.copyWith(settings: next, saving: true, error: null);
    try {
      final stored = await _service(host, port).updateSettings(next);
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(settings: stored, saving: false, error: null);
    } catch (error) {
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(saving: false, error: error.toString());
    }
  }

  Future<void> applyPreset(NoiseSuppressionPreset preset) async {
    final settings = preset.build();
    await update(
      active: settings.active,
      strength: settings.strength,
      sensitivity: settings.sensitivity,
      snowboySensitivity: settings.snowboySensitivity,
    );
  }

  NoiseSuppressionService _service(String host, int port) {
    return NoiseSuppressionService(host: host, port: port);
  }
}

const _unset = Object();
