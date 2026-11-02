import 'dart:convert';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:thermal_audio_monitor/services/device_pairing_service.dart';
import 'package:thermal_audio_monitor/services/api_token.dart';

class PairAdapter implements HttpClientAdapter {
  bool approved = false,
      spoof = false,
      failRequestOnce = false,
      revoked = false;
  String? firstProof;
  final requests = <RequestOptions>[];
  final pi = 'b' * 32, secret = 'fixture-device-secret-${'x' * 32}';
  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? stream,
    Future<void>? cancel,
  ) async {
    requests.add(options);
    final body = options.data is Map ? options.data as Map : {};
    final id = body['device_id']?.toString() ?? '';
    if (options.uri.path == '/api/pairing/prove' && revoked) {
      return ResponseBody.fromString(
        '{}',
        409,
        headers: {
          Headers.contentTypeHeader: ['application/json'],
        },
      );
    }
    if (options.uri.path == '/api/pairing/request') {
      if (firstProof == null) {
        firstProof = body['claim_proof'] as String;
      } else {
        expect(body['claim_proof'], firstProof);
      }
      if (failRequestOnce) {
        failRequestOnce = false;
        throw DioException(
          requestOptions: options,
          type: DioExceptionType.connectionError,
        );
      }
    }
    final data = switch (options.uri.path) {
      '/api/discovery' => {
        'protocol': 1,
        'service': 'project-pi',
        'pi_id': pi,
        'pairing_available': true,
        'enrollment_open': true,
      },
      '/api/pairing/request' => {
        'request_id': 'request-1',
        'code': '123456',
        'expires_in': 180,
        'state': 'pending',
      },
      '/api/pairing/claim' =>
        approved
            ? {
                'state': 'approved',
                'pi_id': pi,
                'request_id': 'request-1',
                'device_id': await DevicePairingService.installation(
                  'caregiver',
                ),
                'role': 'caregiver',
                'token': secret,
              }
            : {'state': 'pending'},
      '/api/pairing/prove' => {
        'pi_id': pi,
        'proof': spoof
            ? 'bad'
            : Hmac(
                sha256,
                sha256.convert(utf8.encode(secret)).bytes,
              ).convert(utf8.encode('$pi:$id:${body['nonce']}')).toString(),
      },
      _ => <String, dynamic>{},
    };
    return ResponseBody.fromString(
      jsonEncode(data),
      200,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    ApiToken.current = '';
    ApiToken.deviceId = '';
    ApiToken.endpoint = '';
    DevicePairingService.clearActive();
  });
  test(
    'local approval required, credentials survive editable IP, and spoofed server gets no bearer',
    () async {
      final adapter = PairAdapter();
      final pairing = DevicePairingService(
        dio: Dio()..httpClientAdapter = adapter,
      );
      await expectLater(
        pairing.ensure('192.0.2.1', 8765, 'caregiver'),
        throwsA(isA<PairingRequired>()),
      );
      expect(ApiToken.current, '');
      adapter.approved = true;
      final first = await pairing.ensure('192.0.2.1', 8765, 'caregiver');
      final second = await pairing.ensure('192.0.2.99', 8765, 'caregiver');
      expect(first.deviceId, second.deviceId);
      expect(first.piId, second.piId);
      expect(ApiToken.current, adapter.secret);
      expect(ApiToken.headersFor('192.0.2.1', 8765), isEmpty);
      expect(
        ApiToken.headersFor('192.0.2.99', 8765)['X-Device-Id'],
        second.deviceId,
      );
      expect(
        adapter.requests.every((r) => !r.headers.containsKey('Authorization')),
        true,
      );
      adapter.spoof = true;
      await expectLater(
        pairing.ensure('192.0.2.100', 8765, 'caregiver'),
        throwsA(isA<PairingRequired>()),
      );
      expect(ApiToken.current, '');
    },
  );
  test(
    'durable installation and legacy inbox identity persist after app restart and IP edit',
    () async {
      FlutterSecureStorage.setMockInitialValues({
        'caregiver_installation': 'c' * 32,
        'caregiver_token_192.0.2.1': 'legacy-fixture-secret',
      });
      final adapter = PairAdapter()..approved = true;
      final service = DevicePairingService(
        dio: Dio()..httpClientAdapter = adapter,
      );
      final original = await service.ensure('192.0.2.1', 8765, 'caregiver');
      expect(original.deviceId, 'c' * 32);
      expect(original.inboxKey, '192.0.2.1');
      DevicePairingService.clearActive();
      await ApiToken.load();
      final moved = await service.ensure('192.0.2.88', 9876, 'caregiver');
      expect(moved.deviceId, original.deviceId);
      expect(moved.inboxKey, original.inboxKey);
      expect(moved.token, original.token);
      expect(ApiToken.headersFor('192.0.2.88', 8765), isEmpty);
      expect(ApiToken.headersFor('192.0.2.88', 9876), isNotEmpty);
      expect(
        adapter.requests
            .where((r) => r.uri.path == '/api/pairing/request')
            .length,
        1,
      );
    },
  );
  test('grant with the wrong role cannot activate a Main credential', () async {
    final adapter = PairAdapter()..approved = true;
    final service = DevicePairingService(
      dio: Dio()..httpClientAdapter = adapter,
    );
    await expectLater(
      service.ensure('pi.test', 8765, 'resident'),
      throwsA(isA<PairingRequired>()),
    );
    expect(ApiToken.current, isEmpty);
    expect(DevicePairingService.active('pi.test', 'resident'), isNull);
  });
  test('lost enrollment response reuses the saved claim proof', () async {
    final adapter = PairAdapter()
      ..failRequestOnce = true
      ..approved = true;
    final service = DevicePairingService(
      dio: Dio()..httpClientAdapter = adapter,
    );
    await expectLater(
      service.ensure('pi.test', 8765, 'caregiver'),
      throwsA(isA<PairingRequired>()),
    );
    final credential = await service.ensure('pi.test', 8765, 'caregiver');
    expect(credential.token, adapter.secret);
    expect(
      adapter.requests
          .where((r) => r.uri.path == '/api/pairing/request')
          .length,
      2,
    );
  });
  test(
    'concurrent startup requests retain one durable installation ID',
    () async {
      final ids = await Future.wait(
        List.generate(
          10,
          (_) => DevicePairingService.installation('caregiver'),
        ),
      );
      expect(ids.toSet().length, 1);
    },
  );
  test(
    'revoked credential cannot authenticate until explicit local reapproval',
    () async {
      final adapter = PairAdapter()..approved = true;
      final service = DevicePairingService(
        dio: Dio()..httpClientAdapter = adapter,
      );
      final old = await service.ensure('pi.test', 8765, 'caregiver');
      adapter
        ..revoked = true
        ..approved = false
        ..firstProof = null;
      await expectLater(
        service.ensure('pi.test', 8765, 'caregiver'),
        throwsA(isA<PairingRequired>()),
      );
      expect(ApiToken.current, isEmpty);
      adapter.approved = true;
      final restored = await service.ensure('pi.test', 8765, 'caregiver');
      expect(restored.deviceId, old.deviceId);
      expect(restored.inboxKey, old.inboxKey);
    },
  );
}
