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
  }) : host = normalizeBackendHost(host) ?? defaultHost,
       port = normalizeBackendPort(port);

  static const defaultHost = 'raspberrypi.local';
  static const fallbackHost = 'raspberrypi.local';
  static const mdnsFallbackHost = 'raspberrypi.local';
  static const defaultPort = 8765;

  static String? normalizeBackendHost(String? value) {
    var host = value?.trim() ?? '';
    host = host.replaceFirst(RegExp(r'^https?://', caseSensitive: false), '');
    host = host.replaceFirst(RegExp(r'/+$'), '');
    if (host.isEmpty ||
        host.contains('/') ||
        host.contains('\\') ||
        host.contains(':') ||
        host.contains('@')) {
      return null;
    }
    if (!RegExp(r'^[A-Za-z0-9.-]+$').hasMatch(host)) {
      return null;
    }
    return host;
  }

  static int normalizeBackendPort(int? port) {
    return port != null && port >= 1 && port <= 65535 ? port : defaultPort;
  }

  final String host;
  final int port;
  final bool darkMode;
  final AlertSound alertSound;
  final bool thermalMonitoringEnabled = true;

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
