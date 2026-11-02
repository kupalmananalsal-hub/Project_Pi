import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import 'dart:typed_data';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:thermal_audio_monitor/services/device_pairing_service.dart';
import 'package:thermal_audio_monitor/services/pi_api_service.dart';
import 'package:thermal_audio_monitor/services/api_token.dart';
import 'package:thermal_audio_monitor/providers/settings_provider.dart';
import 'device_pairing_test.dart' show PairAdapter;
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:thermal_audio_monitor/screens/settings_screen.dart';
import 'package:thermal_audio_monitor/providers/connection_provider.dart';

class RetryingConnection extends ConnectionController {
  String? attemptedHost;
  int? attemptedPort;
  @override
  PiConnectionState build() =>
      PiConnectionState(host: 'old-pi.test', port: 8765);
  void failOldAttempt() => state = state.copyWith(
    connectionStatus: PiConnectionStatus.error,
    error: 'Old connection retry failed',
  );
  @override
  Future<void> connect({String? host, int? port}) async {
    attemptedHost = host;
    attemptedPort = port;
  }
}

class DiscoveryFailureAdapter implements HttpClientAdapter {
  DiscoveryFailureAdapter(this.status, {this.offline = false});
  final int status;
  final bool offline;
  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? stream,
    Future<void>? cancel,
  ) async {
    if (offline) {
      throw DioException(
        requestOptions: options,
        type: DioExceptionType.connectionTimeout,
      );
    }
    return ResponseBody.fromString(
      status == 200 ? 'not-json' : '{}',
      status,
      headers: {
        Headers.contentTypeHeader: [
          status == 200 ? 'text/plain' : 'application/json',
        ],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  setUp(
    () => SharedPreferences.setMockInitialValues({
      'host': 'old-pi.test',
      'port': 8765,
    }),
  );
  testWidgets(
    'a retry rebuild cannot overwrite an edited IP after focus moves to port',
    (tester) async {
      final controller = RetryingConnection();
      await tester.pumpWidget(
        ProviderScope(
          overrides: [connectionProvider.overrideWith(() => controller)],
          child: const MaterialApp(home: SettingsScreen()),
        ),
      );
      await tester.pumpAndSettle();
      final host = find.byKey(const ValueKey('pi-host-field'));
      await tester.enterText(host, '10.48.48.236');
      await tester.tap(find.byKey(const ValueKey('pi-port-field')));
      controller.failOldAttempt();
      await tester.pump();
      expect(tester.widget<TextField>(host).controller!.text, '10.48.48.236');
      await tester.ensureVisible(
        find.byKey(const ValueKey('pi-connect-button')),
      );
      await tester.tap(find.byKey(const ValueKey('pi-connect-button')));
      await tester.pump();
      expect(controller.attemptedHost, '10.48.48.236');
      expect(controller.attemptedPort, 8765);
      await tester.pumpWidget(const SizedBox());
    },
  );
  testWidgets(
    '401 from the selected Pi must not be masked by a fallback network failure',
    (tester) async {
      final hosts = <String>[];
      final container = ProviderContainer(
        overrides: [
          piAutoConnectProvider.overrideWithValue(false),
          piStatusFetcherProvider.overrideWithValue((host, port) async {
            hosts.add(host);
            if (host == '10.48.48.236') {
              final request = RequestOptions(path: '/api/status');
              throw DioException(
                requestOptions: request,
                response: Response(requestOptions: request, statusCode: 401),
                type: DioExceptionType.badResponse,
              );
            }
            throw StateError('fallback unreachable');
          }),
          piConnectionChannelsProvider.overrideWithValue(
            PiConnectionChannels(connect: (_, _) {}, disconnect: () {}),
          ),
        ],
      );
      final controller = container.read(connectionProvider.notifier);
      await controller.connect(host: '10.48.48.236', port: 8765);
      expect(hosts, ['10.48.48.236']);
      expect(
        container.read(connectionProvider).error,
        contains('Authentication rejected'),
      );
      final count = hosts.length;
      await tester.pump(const Duration(seconds: 12));
      expect(hosts.length, count);
      controller.disconnect();
      container.dispose();
    },
  );
  test(
    'the production status fetcher enrolls first and never requests protected status while pending',
    () async {
      FlutterSecureStorage.setMockInitialValues({});
      SharedPreferences.setMockInitialValues({});
      DevicePairingService.clearActive();
      ApiToken.current = '';
      ApiToken.deviceId = '';
      ApiToken.endpoint = '';
      final adapter = PairAdapter();
      final container = ProviderContainer(
        overrides: [
          piPairingServiceProvider.overrideWithValue(
            DevicePairingService(dio: Dio()..httpClientAdapter = adapter),
          ),
          piApiFactoryProvider.overrideWithValue(
            (host, port) => PiApiService(
              host: host,
              port: port,
              dio: Dio(
                BaseOptions(
                  baseUrl: 'http://$host:$port',
                  headers: ApiToken.headersFor(host, port),
                ),
              )..httpClientAdapter = adapter,
            ),
          ),
        ],
      );
      addTearDown(container.dispose);
      final fetch = container.read(piStatusFetcherProvider);
      for (var i = 0; i < 2; i++) {
        await expectLater(
          fetch('10.48.48.236', 8765),
          throwsA(
            isA<PairingRequired>().having(
              (e) => e.kind,
              'state',
              PairingFailure.waitingForApproval,
            ),
          ),
        );
      }
      expect(
        adapter.requests.where((r) => r.uri.path == '/api/status'),
        isEmpty,
      );
      expect(
        adapter.requests
            .where((r) => r.uri.path == '/api/pairing/request')
            .length,
        1,
      );
      expect(adapter.requests.first.uri.path, '/api/discovery');
      adapter.approved = true;
      await fetch('10.48.48.236', 8765);
      expect(adapter.requests.last.uri.path, '/api/status');
      expect(
        adapter.requests.last.headers['Authorization'],
        'Bearer ${adapter.secret}',
      );
      expect(adapter.requests.last.headers['X-Device-Id'], isNotEmpty);
    },
  );
  test('pairing outcomes map to distinct connection labels', () {
    expect(
      connectionFailureStatus(const PairingRequired('window closed')),
      PiConnectionStatus.pairingRequired,
    );
    expect(
      connectionFailureStatus(
        const PairingRequired(
          'pending',
          kind: PairingFailure.waitingForApproval,
        ),
      ),
      PiConnectionStatus.waitingForApproval,
    );
    expect(
      connectionFailureStatus(
        const PairingRequired(
          'offline',
          kind: PairingFailure.networkUnavailable,
        ),
      ),
      PiConnectionStatus.networkUnavailable,
    );
    expect(
      connectionFailureStatus(
        const PairingRequired(
          'rejected',
          kind: PairingFailure.authenticationRejected,
          retryable: false,
        ),
      ),
      PiConnectionStatus.authenticationRejected,
    );
    expect(PiConnectionStatus.connected.label, 'Paired and connected');
  });
  testWidgets(
    'unrelated settings rebuilds keep pending enrollment and its public retry alive',
    (tester) async {
      SharedPreferences.setMockInitialValues({'host': 'pi.test', 'port': 8765});
      var attempts = 0;
      final container = ProviderContainer(
        overrides: [
          piAutoConnectProvider.overrideWithValue(false),
          piStatusFetcherProvider.overrideWithValue((host, port) async {
            attempts++;
            throw const PairingRequired(
              'pending code',
              kind: PairingFailure.waitingForApproval,
            );
          }),
          piConnectionChannelsProvider.overrideWithValue(
            PiConnectionChannels(connect: (_, _) {}, disconnect: () {}),
          ),
        ],
      );
      final controller = container.read(connectionProvider.notifier);
      await controller.connect(host: 'pi.test', port: 8765);
      expect(
        container.read(connectionProvider).connectionStatus,
        PiConnectionStatus.waitingForApproval,
      );
      await container.read(settingsProvider.notifier).setDarkMode(false);
      await tester.pump();
      expect(
        container.read(connectionProvider).connectionStatus,
        PiConnectionStatus.waitingForApproval,
      );
      final before = attempts;
      await tester.pump(const Duration(seconds: 6));
      expect(attempts, greaterThan(before));
      controller.disconnect();
      container.dispose();
    },
  );

  test(
    'shared Main/Resident discovery failures retain phase and terminal/retry distinction',
    () async {
      FlutterSecureStorage.setMockInitialValues({});
      DevicePairingService.clearActive();
      for (final role in ['caregiver', 'resident']) {
        for (final status in [401, 404, 200]) {
          final service = DevicePairingService(
            dio: Dio()..httpClientAdapter = DiscoveryFailureAdapter(status),
          );
          await expectLater(
            service.ensure('pi.test', 8765, role),
            throwsA(
              isA<PairingRequired>()
                  .having((e) => e.message, 'stage', contains('/api/discovery'))
                  .having((e) => e.retryable, 'retry', false),
            ),
          );
        }
        final offline = DevicePairingService(
          dio: Dio()
            ..httpClientAdapter = DiscoveryFailureAdapter(0, offline: true),
        );
        await expectLater(
          offline.ensure('pi.test', 8765, role),
          throwsA(
            isA<PairingRequired>()
                .having(
                  (e) => e.kind,
                  'state',
                  PairingFailure.networkUnavailable,
                )
                .having((e) => e.message, 'endpoint', contains('pi.test:8765')),
          ),
        );
      }
    },
  );
  test(
    'a closed discovery window reports Pairing required and waits before submitting enrollment',
    () async {
      FlutterSecureStorage.setMockInitialValues({});
      DevicePairingService.clearActive();
      final adapter = PairAdapter()..enrollmentOpen = false;
      final service = DevicePairingService(
        dio: Dio()..httpClientAdapter = adapter,
      );
      await expectLater(
        service.ensure('pi.test', 8765, 'caregiver'),
        throwsA(
          isA<PairingRequired>()
              .having((e) => e.kind, 'state', PairingFailure.pairingRequired)
              .having(
                (e) => e.message,
                'reason',
                contains('enrollment window'),
              ),
        ),
      );
      expect(
        adapter.requests.where((r) => r.uri.path == '/api/pairing/request'),
        isEmpty,
      );
      adapter.enrollmentOpen = true;
      await expectLater(
        service.ensure('pi.test', 8765, 'caregiver'),
        throwsA(
          isA<PairingRequired>().having(
            (e) => e.kind,
            'state',
            PairingFailure.waitingForApproval,
          ),
        ),
      );
      expect(
        adapter.requests
            .where((r) => r.uri.path == '/api/pairing/request')
            .length,
        1,
      );
    },
  );
}
