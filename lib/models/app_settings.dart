enum AlertSound { alarm, bell, siren }

extension AlertSoundLabel on AlertSound {
  String get label {
    switch (this) {
      case AlertSound.alarm:
        return 'Alarm';
      case AlertSound.bell:
        return 'Bell';
      case AlertSound.siren:
        return 'Siren';
    }
  }

  static AlertSound fromName(String? name) {
    return AlertSound.values.firstWhere(
      (sound) => sound.name == name,
      orElse: () => AlertSound.alarm,
    );
  }
}

class AppSettings {
  AppSettings({
    String host = defaultHost,
    int? port,
    this.darkMode = true,
    this.alertSound = AlertSound.alarm,
  }) : host = host.trim().isEmpty ? defaultHost : host.trim(),
       port = normalizeBackendPort(port);

  static const defaultHost = '10.129.205.32';
  static const fallbackHost = '10.129.205.32';
  static const mdnsFallbackHost = 'raspberrypi.local';
  static const defaultPort = 8765;

  static int normalizeBackendPort(int? port) {
    // The Pi backend is fixed on 8765. Normalize stale saved ports from older
    // builds so actions like clear history, reboot, and shutdown cannot drift.
    return defaultPort;
  }

  final String host;
  final int port;
  final bool darkMode;
  final AlertSound alertSound;

  Uri httpUri(String path, {String? hostOverride}) {
    return Uri(
      scheme: 'http',
      host: hostOverride ?? host,
      port: normalizeBackendPort(port),
      path: path,
    );
  }

  Uri wsUri(String path, {String? hostOverride}) {
    return Uri(
      scheme: 'ws',
      host: hostOverride ?? host,
      port: normalizeBackendPort(port),
      path: path,
    );
  }

  AppSettings copyWith({
    String? host,
    int? port,
    bool? darkMode,
    AlertSound? alertSound,
  }) {
    return AppSettings(
      host: host ?? this.host,
      port: normalizeBackendPort(port ?? this.port),
      darkMode: darkMode ?? this.darkMode,
      alertSound: alertSound ?? this.alertSound,
    );
  }
}
