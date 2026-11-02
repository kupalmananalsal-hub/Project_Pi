import 'dart:convert';
import 'dart:math';
import 'package:crypto/crypto.dart';
import 'package:dio/dio.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../models/app_settings.dart';
import 'api_token.dart';

enum PairingFailure {
  pairingRequired,
  waitingForApproval,
  networkUnavailable,
  authenticationRejected,
}

class PairingRequired implements Exception {
  const PairingRequired(
    this.message, {
    this.kind = PairingFailure.pairingRequired,
    this.retryable = true,
  });
  final String message;
  final PairingFailure kind;
  final bool retryable;
  @override
  String toString() => message;
}

class DeviceCredential {
  const DeviceCredential(
    this.piId,
    this.deviceId,
    this.role,
    this.token,
    this.inboxKey,
  );
  final String piId, deviceId, role, token, inboxKey;
  Map<String, dynamic> toJson() => {
    'pi_id': piId,
    'device_id': deviceId,
    'role': role,
    'token': token,
    'inbox_key': inboxKey,
  };
}

/// IP addresses locate the Pi; credentials and inbox identity belong to its stable ID.
class DevicePairingService {
  DevicePairingService({Dio? dio})
    : _dio =
          dio ??
          Dio(
            BaseOptions(
              connectTimeout: const Duration(seconds: 3),
              receiveTimeout: const Duration(seconds: 3),
            ),
          );
  final Dio _dio;
  static const storage = FlutterSecureStorage();
  static final Map<String, DeviceCredential> _active = {};
  static final Map<String, int> _epochs = {};
  static void clearActive() {
    _active.clear();
    _epochs.clear();
  }

  static DeviceCredential? active(String host, String role) =>
      _active['$host:$role'];
  static String randomId() => List.generate(
    32,
    (_) => Random.secure().nextInt(16).toRadixString(16),
  ).join();
  static final Map<String, Future<String>> _identityReads = {};
  static Future<String> installation(String role) => _identityReads.putIfAbsent(
    role,
    () => _loadInstallation(role).whenComplete(() {
      _identityReads.remove(role);
    }),
  );
  static Future<String> _loadInstallation(String role) async {
    final key = role == 'caregiver'
        ? 'caregiver_installation'
        : 'resident_installation';
    final old = await storage.read(key: key);
    if (old != null) return old;
    final value = randomId();
    await storage.write(key: key, value: value);
    return value;
  }

  Future<Map<String, dynamic>> request(
    AppSettings target,
    String path,
    Map<String, dynamic>? data,
  ) async {
    final method = data == null ? 'GET' : 'POST';
    try {
      final response = data == null
          ? await _dio.getUri(target.httpUri(path))
          : await _dio.postUri(target.httpUri(path), data: data);
      final value = response.data;
      if (value is! Map) {
        throw PairingRequired(
          'Pairing required: $method $path returned an invalid JSON object. Check the matching Pi backend.',
          retryable: false,
        );
      }
      return Map<String, dynamic>.from(value);
    } on DioException catch (error) {
      final status = error.response?.statusCode;
      if (status == 401 || status == 403) {
        throw PairingRequired(
          'Authentication rejected: $method $path returned HTTP $status. Check local Pi pairing authorization; no API token entry is needed.',
          kind: PairingFailure.authenticationRejected,
          retryable: false,
        );
      }
      if (status == 404 || status == 405) {
        throw PairingRequired(
          'Pairing required: $method $path is unavailable (HTTP $status). Use the matching Pi pairing backend.',
          retryable: false,
        );
      }
      if (error.response == null) {
        throw PairingRequired(
          'Network unavailable: $method $path at ${target.host}:${target.port} (${error.type.name}).',
          kind: PairingFailure.networkUnavailable,
        );
      }
      rethrow;
    }
  }

  Future<DeviceCredential> ensure(String host, int port, String role) async {
    if (role != 'caregiver' && role != 'resident') {
      throw const PairingRequired('Invalid device role');
    }
    final epoch = (_epochs[role] ?? 0) + 1;
    _epochs[role] = epoch;
    void checkCurrent() {
      if (_epochs[role] != epoch) {
        throw const PairingRequired(
          'Connection superseded by an edited endpoint.',
        );
      }
    }

    void clearCredential() {
      if (role == 'caregiver' && _epochs[role] == epoch) {
        ApiToken.current = '';
        ApiToken.deviceId = '';
        ApiToken.endpoint = '';
      }
    }

    if (role == 'caregiver' && ApiToken.endpoint != '$host:$port') {
      ApiToken.current = '';
      ApiToken.deviceId = '';
      ApiToken.endpoint = '';
    }
    _active.remove('$host:$role');
    final target = AppSettings(host: host, port: port);
    try {
      final discovery = await request(target, '/api/discovery', null);
      final pi = discovery['pi_id'];
      if (discovery['protocol'] != 1 ||
          discovery['service'] != 'project-pi' ||
          discovery['pairing_available'] != true ||
          pi is! String ||
          !RegExp(r'^[0-9a-f]{32}$').hasMatch(pi)) {
        throw const PairingRequired(
          'Pi pairing unavailable. Ask the local operator to configure pairing.',
        );
      }
      final id = await installation(role);
      final key = 'device_pair:$pi:$role:$id';
      final saved = await storage.read(key: key);
      if (saved != null) {
        final data = jsonDecode(saved) as Map;
        final credential = DeviceCredential(
          pi,
          id,
          role,
          data['token'] as String,
          data['inbox_key'] as String? ?? pi,
        );
        final nonce = randomId() + randomId();
        Map<String, dynamic> proof = {};
        try {
          proof = await request(target, '/api/pairing/prove', {
            'device_id': id,
            'nonce': nonce,
          });
        } on DioException catch (error) {
          if (error.response?.statusCode != 409) rethrow;
          // Revocation/registry recovery still requires a new local approval.
        }
        if (proof.isNotEmpty) {
          final expected = Hmac(
            sha256,
            sha256.convert(utf8.encode(credential.token)).bytes,
          ).convert(utf8.encode('$pi:$id:$nonce')).toString();
          if (proof['pi_id'] != pi || proof['proof'] != expected) {
            throw const PairingRequired(
              'Authentication rejected: Pi identity verification failed. No credential sent; check the address or local operator.',
              kind: PairingFailure.authenticationRejected,
              retryable: false,
            );
          }
          checkCurrent();
          _activate(host, port, credential);
          return credential;
        }
      }
      final pendingKey = 'device_pending:$pi:$role:$id';
      Map<String, dynamic> pending = {};
      final pendingText = await storage.read(key: pendingKey);
      if (pendingText != null) {
        pending = Map<String, dynamic>.from(jsonDecode(pendingText) as Map);
      }
      if (pending.isEmpty ||
          (pending['expires_at'] as num? ?? 0) <
              DateTime.now().millisecondsSinceEpoch) {
        pending = {
          'claim_proof': randomId() + randomId(),
          'expires_at': DateTime.now().millisecondsSinceEpoch + 180000,
        };
        // Save the claim proof before POST: a lost response can safely retry.
        await storage.write(key: pendingKey, value: jsonEncode(pending));
      }
      if (pending['request_id'] == null) {
        if (discovery['enrollment_open'] != true) {
          throw const PairingRequired(
            'Pairing required: the local Pi enrollment window is closed. Ask the operator to open enrollment; no protected status request was sent.',
          );
        }
        final response = await request(target, '/api/pairing/request', {
          'role': role,
          'device_id': id,
          'claim_proof': pending['claim_proof'],
        });
        if (response['request_id'] is! String ||
            response['code'] is! String ||
            !RegExp(r'^[0-9]{6}$').hasMatch(response['code'] as String) ||
            response['expires_in'] is! num ||
            (response['expires_in'] as num) <= 0 ||
            (response['expires_in'] as num) > 180) {
          throw const PairingRequired(
            'Invalid enrollment response; local Pi approval required.',
          );
        }
        pending.addAll({
          'request_id': response['request_id'],
          'code': response['code'],
          'expires_at':
              DateTime.now().millisecondsSinceEpoch +
              ((response['expires_in'] as num) * 1000).floor(),
        });
        await storage.write(key: pendingKey, value: jsonEncode(pending));
      }
      Map<String, dynamic> grant;
      try {
        grant = await request(target, '/api/pairing/claim', {
          'request_id': pending['request_id'],
          'claim_proof': pending['claim_proof'],
        });
      } on DioException catch (error) {
        if (error.response?.statusCode == 409) {
          await storage.delete(key: pendingKey);
        }
        rethrow;
      }
      if (grant['state'] != 'approved') {
        throw PairingRequired(
          'Waiting for operator approval. Compare code ${pending['code']} for $role. Request ${pending['request_id']}.',
          kind: PairingFailure.waitingForApproval,
        );
      }
      if (grant['pi_id'] != pi ||
          grant['device_id'] != id ||
          grant['role'] != role ||
          grant['token'] is! String ||
          (grant['token'] as String).length < 32) {
        throw const PairingRequired(
          'Invalid pairing grant. Ask the local Pi operator.',
        );
      }
      // Preserve the old inbox path on upgrade; later DHCP changes reuse it.
      final legacy = role == 'caregiver'
          ? await storage.read(key: 'caregiver_token_$host')
          : null;
      final credential = DeviceCredential(
        pi,
        id,
        role,
        grant['token'] as String,
        saved != null
            ? ((jsonDecode(saved) as Map)['inbox_key'] as String? ?? pi)
            : legacy != null
            ? host
            : pi,
      );
      if (role == 'caregiver') {
        await storage.write(key: 'caregiver_pairing_required', value: 'true');
      }
      await storage.write(key: key, value: jsonEncode(credential.toJson()));
      await storage.delete(key: pendingKey);
      checkCurrent();
      _activate(host, port, credential);
      return credential;
    } on PairingRequired {
      clearCredential();
      rethrow;
    } on PlatformException catch (error) {
      clearCredential();
      throw PairingRequired(
        'Pairing required: Android secure storage unavailable (${error.code}); saved credentials were not cleared. Check secure storage before retrying.',
        retryable: false,
      );
    } on FormatException {
      clearCredential();
      throw const PairingRequired(
        'Pairing required: saved pairing data is invalid; credentials were preserved. Ask the local operator.',
        retryable: false,
      );
    } on DioException catch (error) {
      clearCredential();
      if (error.response?.statusCode == 409) {
        throw const PairingRequired(
          'Pairing closed, expired, or revoked. Ask the local Pi operator to open enrollment or check this device.',
        );
      }
      throw const PairingRequired(
        'Pi unavailable or pairing backend not ready. Check editable IP, port and local pairing setup.',
      );
    }
  }

  static void _activate(String host, int port, DeviceCredential credential) {
    _active['$host:${credential.role}'] = credential;
    if (credential.role == 'caregiver') {
      ApiToken.current = credential.token;
      ApiToken.deviceId = credential.deviceId;
      ApiToken.endpoint = '$host:$port';
    }
  }
}
