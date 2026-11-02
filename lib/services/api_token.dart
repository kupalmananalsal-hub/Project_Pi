import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Active device credential, installed only after pairing/server verification.
/// Legacy save remains for compatibility; connection settings never request a token.
class ApiToken {
  static const _storage = FlutterSecureStorage();
  static const _key = 'pi_api_token';

  static String current = '';
  static String deviceId = '';
  static String endpoint = '';
  static Map<String, String> headersFor(String host, int port) =>
      endpoint.isEmpty || endpoint == '$host:$port' ? headers : const {};

  static Map<String, String> get headers => current.isEmpty
      ? const {}
      : {
          'Authorization': 'Bearer $current',
          if (deviceId.isNotEmpty) 'X-Device-Id': deviceId,
        };

  static Future<void> load() async {
    // Device credentials activate only after the Pi identity proof succeeds.
    current = '';
    deviceId = '';
    endpoint = '';
  }

  static Future<void> save(String value) async {
    final token = value.trim();
    await _storage.write(key: _key, value: token);
    current = token;
  }
}
