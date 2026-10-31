import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Bearer token the Pi backend requires on every /api and /ws route
/// (PROJECT_PI_API_TOKEN in /etc/project-pi/backend.env on the Pi).
///
/// Loaded once before runApp so HTTP and WebSocket clients, which are created
/// on demand all over the app, can read it synchronously.
class ApiToken {
  static const _storage = FlutterSecureStorage();
  static const _key = 'pi_api_token';

  static String current = '';

  static Map<String, String> get headers =>
      current.isEmpty ? const {} : {'Authorization': 'Bearer $current'};

  static Future<void> load() async {
    current = await _storage.read(key: _key) ?? '';
  }

  static Future<void> save(String value) async {
    final token = value.trim();
    await _storage.write(key: _key, value: token);
    current = token;
  }
}
