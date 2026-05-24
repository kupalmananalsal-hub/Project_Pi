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
  const AppSettings({
    this.host = defaultHost,
    this.port = defaultPort,
    this.darkMode = true,
    this.alertSound = AlertSound.alarm,
  });

  static const defaultHost = '172.20.10.8';
  static const fallbackHost = '172.20.10.8';
  static const mdnsFallbackHost = 'raspberrypi.local';
  static const defaultPort = 8765;

  final String host;
  final int port;
  final bool darkMode;
  final AlertSound alertSound;

  Uri httpUri(String path, {String? hostOverride}) {
    return Uri(
      scheme: 'http',
      host: hostOverride ?? host,
      port: port,
      path: path,
    );
  }

  Uri wsUri(String path, {String? hostOverride}) {
    return Uri(
      scheme: 'ws',
      host: hostOverride ?? host,
      port: port,
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
      port: port ?? this.port,
      darkMode: darkMode ?? this.darkMode,
      alertSound: alertSound ?? this.alertSound,
    );
  }
}
