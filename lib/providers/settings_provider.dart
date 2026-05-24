import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/app_settings.dart';

final settingsProvider = NotifierProvider<SettingsController, AppSettings>(
  SettingsController.new,
);

class SettingsController extends Notifier<AppSettings> {
  SharedPreferences? _prefs;

  @override
  AppSettings build() {
    Future.microtask(_load);
    return const AppSettings();
  }

  Future<void> updateHost(String host) async {
    final trimmed = host.trim();
    state = state.copyWith(
      host: trimmed.isEmpty ? AppSettings.defaultHost : trimmed,
    );
    await _persist();
  }

  Future<void> updatePort(int port) async {
    state = state.copyWith(port: port <= 0 ? AppSettings.defaultPort : port);
    await _persist();
  }

  Future<void> setDarkMode(bool value) async {
    state = state.copyWith(darkMode: value);
    await _persist();
  }

  Future<void> setAlertSound(AlertSound sound) async {
    state = state.copyWith(alertSound: sound);
    await _persist();
  }

  Future<void> _load() async {
    final prefs = await SharedPreferences.getInstance();
    _prefs = prefs;
    if (!ref.mounted) {
      return;
    }
    state = AppSettings(
      host: prefs.getString('host') ?? AppSettings.defaultHost,
      port: prefs.getInt('port') ?? AppSettings.defaultPort,
      darkMode: prefs.getBool('darkMode') ?? true,
      alertSound: AlertSoundLabel.fromName(prefs.getString('alertSound')),
    );
  }

  Future<void> _persist() async {
    final prefs = _prefs ?? await SharedPreferences.getInstance();
    _prefs = prefs;
    await prefs.setString('host', state.host);
    await prefs.setInt('port', state.port);
    await prefs.setBool('darkMode', state.darkMode);
    await prefs.setString('alertSound', state.alertSound.name);
  }
}
