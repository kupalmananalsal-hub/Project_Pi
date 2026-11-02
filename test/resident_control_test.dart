import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:thermal_audio_monitor/models/app_settings.dart';
import 'package:thermal_audio_monitor/services/resident_control_client.dart';
import 'package:thermal_audio_monitor/services/resident_monitor_service.dart';
import 'package:thermal_audio_monitor/services/api_token.dart';
import 'package:thermal_audio_monitor/services/mute_acknowledgement.dart';
import 'package:thermal_audio_monitor/models/audio_frame.dart';

class ControlAdapter implements HttpClientAdapter {
  final requests = <RequestOptions>[];
  bool ack = false, fail = false, realKeyword = false;
  Completer<void>? startGate;
  List<Map<String, dynamic>> events = [];
  Map<String, dynamic> get state => {
    'boot_id': 'fixture-boot',
    'session_id': 'fixture-session',
    'test_mode': true,
    'remote_mute_available': true,
    'mute_ack_valid_for_seconds': 2,
    'remote_microphone_muted': ack,
    'active_lease_id': 'fixture-lease',
    'mute_state': ack ? 'muted' : 'unmuted',
    'resident_connected': true,
    'events': events,
  };
  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? stream,
    Future<void>? cancel,
  ) async {
    requests.add(options);
    if (fail) throw StateError('fixture_wifi_loss');
    final body = options.data is Map
        ? options.data as Map
        : <String, dynamic>{};
    if (body['action'] == 'mute_start') await startGate?.future;
    return ResponseBody.fromString(
      jsonEncode({
        ...state,
        if (body['action'] == 'mute_start') 'lease_id': 'fixture-lease',
        if (body['action'] == 'keyword_test' || body['action'] == 'full_test')
          'event_id': 'test-fixture-1',
      }),
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
    SharedPreferences.setMockInitialValues({});
    ApiToken.current = 'fixture-only-main-token';
  });
  testWidgets(
    'mute acknowledgement expires locally and delayed or malformed ACKs cannot claim MUTED',
    (tester) async {
      final ack = MuteAcknowledgement();
      final state = <String, dynamic>{
        'remote_microphone_muted': true,
        'mute_ack_valid_for_seconds': .1,
      };
      var changes = 0;
      ack.apply(state, Duration.zero, () => changes++);
      expect(state['remote_microphone_muted'], true);
      await tester.pump(const Duration(milliseconds: 101));
      expect(state['remote_microphone_muted'], false);
      expect(changes, 1);
      state['remote_microphone_muted'] = true;
      ack.apply(state, const Duration(seconds: 1), () {});
      expect(state['remote_microphone_muted'], false);
      for (final ttl in [null, -1, double.infinity, 100000]) {
        state['remote_microphone_muted'] = true;
        state['mute_ack_valid_for_seconds'] = ttl;
        ack.apply(state, Duration.zero, () {});
        expect(state['remote_microphone_muted'], false);
      }
      ack.clear();
    },
  );
  test(
    'muted audio remains explicitly unavailable evidence, with unknown direction',
    () {
      final audio = AudioFrame.fromMessage({
        'rms': [0, 0],
        'remote_microphone_muted': true,
        'direction': 'left',
        'audio_evidence': 'muted_not_evidence',
      });
      expect(audio.remoteMicrophoneMuted, true);
      expect(audio.voiceDirection, isNotNull);
      expect(audio.voiceDirection.isKnown, false);
    },
  );
  Future<(ResidentControlClient, ControlAdapter)> resident() async {
    final adapter = ControlAdapter();
    final client = ResidentControlClient(
      dio: Dio()..httpClientAdapter = adapter,
      pollInterval: const Duration(days: 1),
    );
    addTearDown(client.dispose);
    await client.connect(
      'http://pi.test/',
      8765,
      'phone2',
      'fixture-only-resident-secret-longer-than-32',
    );
    return (client, adapter);
  }

  test(
    'scoped control endpoint, authentication and unique command IDs',
    () async {
      final (client, adapter) = await resident();
      await client.sendTest(full: false);
      await client.sendTest(full: true);
      expect(
        adapter.requests.every((r) => r.uri.path == '/api/resident/control'),
        true,
      );
      expect(adapter.requests.first.uri.host, 'pi.test');
      expect(adapter.requests.first.headers['X-Resident-Id'], 'phone2');
      expect(
        adapter.requests.first.headers['Authorization'],
        contains('fixture-only-resident'),
      );
      final commands = adapter.requests
          .map((r) => r.data as Map)
          .where((r) => r['command_id'] != null)
          .toList();
      expect(commands.map((r) => r['command_id']).toSet().length, 2);
      expect(commands.map((r) => r['sequence']), [1, 2]);
      expect(client.message, contains('waiting for Main presentation'));
    },
  );
  test(
    'remote mute stays disabled even if a backend advertises capability',
    () async {
      final (client, adapter) = await resident();
      expect(client.muteAvailable, false);
      await client.beginHold();
      adapter.ack = true;
      await client.poll();
      expect(client.holding, false);
      expect(client.muted, false);
      await client.release();
      expect(
        adapter.requests.where(
          (r) => (r.data as Map)['action'].toString().startsWith('mute_'),
        ),
        isEmpty,
      );
    },
  );
  test('network loss and reconnect never replay a hold', () async {
    final (client, adapter) = await resident();
    await client.beginHold();
    adapter.fail = true;
    await client.poll();
    expect(client.connected, false);
    expect(client.muted, false);
    adapter.fail = false;
    await client.poll();
    expect(client.connected, true);
    expect(client.holding, false);
    expect(
      adapter.requests
          .where((r) => (r.data as Map)['action'] == 'mute_start')
          .length,
      0,
    );
  });
  test('background pause disconnects without a mute command', () async {
    final (client, adapter) = await resident();
    await client.beginHold();
    await client.pause();
    expect(client.connected, false);
    expect(
      adapter.requests.map((r) => (r.data as Map)['action']).toList(),
      contains('disconnect'),
    );
  });
  test(
    'Main keeps synthetic and real events separate and persists dedup across restart',
    () async {
      final adapter = ControlAdapter()
        ..events = [
          {
            'event_id': 'test-one',
            'kind': 'full_test',
            'is_test': true,
            'delivery': 'backend_accepted',
          },
          {
            'event_id': 'real-event',
            'kind': 'full_test',
            'is_test': false,
            'delivery': 'backend_accepted',
          },
        ];
      ResidentMonitorService make() =>
          ResidentMonitorService(dio: Dio()..httpClientAdapter = adapter);
      var monitor = make();
      await monitor.start(AppSettings(host: 'pi.test'));
      expect(monitor.pending.length, 1);
      final event = monitor.pending.single;
      expect(await monitor.claim(event), true);
      expect(await monitor.claim(event), false);
      await monitor.poll();
      expect(monitor.pending, isEmpty);
      monitor.dispose();
      monitor = make();
      await monitor.start(AppSettings(host: 'pi.test'));
      expect(monitor.pending, isEmpty);
      adapter.fail = true;
      await monitor.poll();
      expect(monitor.connected, false);
      expect(monitor.state, isEmpty);
      monitor.dispose();
    },
  );
}
