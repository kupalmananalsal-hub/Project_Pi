import 'package:flutter_test/flutter_test.dart';
import 'package:thermal_audio_monitor/models/app_settings.dart';

void main() {
  test('normalizes URL-form host input to a raw host', () {
    expect(
      AppSettings.normalizeBackendHost('https://192.168.1.5/'),
      '192.168.1.5',
    );
    expect(
      AppSettings.normalizeBackendHost('raspberrypi.local'),
      'raspberrypi.local',
    );
  });

  test('rejects host paths and unsupported host syntax', () {
    expect(AppSettings.normalizeBackendHost('http://192.168.1.5/path'), isNull);
    expect(AppSettings.normalizeBackendHost('user@192.168.1.5'), isNull);
    expect(AppSettings.normalizeBackendHost(''), isNull);
  });

  test('preserves valid custom ports and falls back for invalid ports', () {
    expect(AppSettings.normalizeBackendPort(9000), 9000);
    expect(AppSettings.normalizeBackendPort(1), 1);
    expect(AppSettings.normalizeBackendPort(65535), 65535);
    expect(AppSettings.normalizeBackendPort(null), AppSettings.defaultPort);
    expect(AppSettings.normalizeBackendPort(0), AppSettings.defaultPort);
    expect(AppSettings.normalizeBackendPort(65536), AppSettings.defaultPort);
  });
}
