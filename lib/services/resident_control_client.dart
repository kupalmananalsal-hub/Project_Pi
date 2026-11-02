import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/app_settings.dart';
import 'mute_acknowledgement.dart';
import 'device_pairing_service.dart';

class ResidentBackendUpdateRequired implements Exception {}

class ResidentPairing {
  static const _storage = FlutterSecureStorage();
  static String key(String host, int port) => 'resident:$host:$port';
  static Future<void> save(String host, int port, String id, String token) =>
      _storage.write(
        key: key(host, port),
        value: jsonEncode({'id': id, 'token': token}),
      );
  static Future<Map<String, dynamic>> load(String host, int port) async {
    final value = await _storage.read(key: key(host, port));
    return value == null
        ? {}
        : Map<String, dynamic>.from(jsonDecode(value) as Map);
  }
}

/// TEST-only, scoped control channel. Never calls the real manual-alert endpoint.
class ResidentControlClient extends ChangeNotifier {
  ResidentControlClient({
    Dio? dio,
    this.pollInterval = const Duration(seconds: 1),
  }) : _dio = dio ?? Dio();
  final Dio _dio;
  final _muteAck = MuteAcknowledgement();
  final Duration pollInterval;
  Timer? _timer;
  String? _session, _lease;
  String _host = '', _id = '', _token = '';
  int _port = 8765, _sequence = 0, _generation = 0;
  bool _holding = false, _busy = false, _disposed = false, _paused = false;
  int _holdGeneration = 0;
  int _pairingGeneration = 0;
  bool _managedPairing = false;
  bool _connectionRetryAllowed = true;
  Map<String, dynamic> state = {};
  String message = 'Not connected — configure Resident pairing';
  String? lastEventId;
  String? lastHistoryEventId;
  bool get connected => _session != null;
  bool get muteAvailable =>
      connected &&
      state['remote_mute_available'] == true &&
      state['max_lease_seconds'] is num &&
      (state['max_lease_seconds'] as num).isFinite &&
      (state['max_lease_seconds'] as num) > 0;
  bool get muted =>
      connected &&
      _holding &&
      _lease != null &&
      state['active_lease_id'] == _lease &&
      state['remote_microphone_muted'] == true;
  bool get holding => _holding;
  String _commandId() => List.generate(
    24,
    (_) => Random.secure().nextInt(256).toRadixString(16).padLeft(2, '0'),
  ).join();
  Future<void> _serial = Future.value();

  void _changed() {
    if (!_disposed) notifyListeners();
  }

  void _schedule() {
    _timer?.cancel();
    final seconds = state['max_lease_seconds'];
    var micros = pollInterval.inMicroseconds;
    if (seconds is num && seconds.isFinite && seconds > 0) {
      micros = min(
        micros,
        (min(seconds.toDouble(), micros / 1000000) * 1000000 / 3).floor(),
      );
    }
    _timer = Timer.periodic(
      Duration(microseconds: max(1, micros)),
      (_) => poll(),
    );
  }

  Future<void> connectSaved() async {
    final generation = ++_pairingGeneration;
    _paused = false;
    _timer?.cancel();
    try {
      final prefs = await SharedPreferences.getInstance();
      final host = AppSettings.normalizeBackendHost(prefs.getString('host'));
      final port = AppSettings.normalizeBackendPort(prefs.getInt('port'));
      if (host == null) return;
      final credential = await DevicePairingService().ensure(
        host,
        port,
        'resident',
      );
      if (_disposed || generation != _pairingGeneration || _paused) return;
      _managedPairing = true;
      await connect(host, port, credential.deviceId, credential.token);
    } catch (error) {
      if (_disposed || generation != _pairingGeneration || _paused) return;
      message = error is PairingRequired
          ? error.message
          : 'Unable to pair with Pi. Check IP and port.';
      _changed();
      if (error is! PairingRequired || error.retryable) {
        _timer = Timer(const Duration(seconds: 2), () => connectSaved());
      }
    }
  }

  Future<Map<String, dynamic>> _post(Map<String, dynamic> data) async {
    final elapsed = Stopwatch()..start();
    final response = await _dio
        .postUri<Map<String, dynamic>>(
          Uri(
            scheme: 'http',
            host: _host,
            port: _port,
            path: '/api/resident/control',
          ),
          data: data,
          options: Options(
            headers: {'Authorization': 'Bearer $_token', 'X-Resident-Id': _id},
            sendTimeout: const Duration(seconds: 2),
            receiveTimeout: const Duration(seconds: 2),
          ),
        )
        .timeout(const Duration(seconds: 3));
    final value = response.data!;
    value['_local_rtt_us'] = elapsed.elapsedMicroseconds;
    if (value['test_mode'] != true || value['boot_id'] is! String) {
      throw StateError('incompatible_test_control_protocol');
    }
    if (value['manual_alert_history_version'] != 1) {
      throw ResidentBackendUpdateRequired();
    }
    return value;
  }

  void _accept(Map<String, dynamic> value) {
    _muteAck.apply(
      value,
      Duration(microseconds: value.remove('_local_rtt_us') as int),
      _changed,
    );
    state = value;
  }

  Future<void> connect(String host, int port, String id, String token) async {
    _timer?.cancel();
    await release();
    final generation = ++_generation;
    _session = null;
    _lease = null;
    _holding = false;
    state = {};
    _host = AppSettings.normalizeBackendHost(host) ?? '';
    _port = AppSettings.normalizeBackendPort(port);
    _id = id;
    _token = token;
    _paused = false;
    _connectionRetryAllowed = true;
    if (_host.isEmpty || _id.isEmpty || token.length < 32) {
      message = 'Resident pairing required (separate from Main API token)';
      _changed();
      return;
    }
    await _connect(generation);
    if (!_disposed && generation == _generation && _connectionRetryAllowed) {
      _schedule();
    }
  }

  Future<void> _connect(int generation) async {
    try {
      if (_managedPairing) {
        final credential = await DevicePairingService().ensure(
          _host,
          _port,
          'resident',
        );
        if (_disposed || _paused || generation != _generation) return;
        _id = credential.deviceId;
        _token = credential.token;
      }
      final value = await _post({'action': 'connect'});
      if (_disposed || _paused || generation != _generation) return;
      _session = value['session_id'] as String;
      _sequence = 0;
      _accept(value);
      message = 'Paired and connected';
    } catch (error) {
      _connectionRetryAllowed = error is ResidentBackendUpdateRequired
          ? false
          : error is PairingRequired
          ? error.retryable
          : !(error is DioException &&
                (error.response?.statusCode == 401 ||
                    error.response?.statusCode == 403));
      if (!_connectionRetryAllowed) _timer?.cancel();
      message = error is ResidentBackendUpdateRequired
          ? 'Pi backend update required for delivery to Main and saved History. Pairing is preserved.'
          : error is PairingRequired
          ? error.message
          : error is DioException &&
                (error.response?.statusCode == 401 ||
                    error.response?.statusCode == 403)
          ? 'Authentication rejected by Resident control. Ask the local Pi operator.'
          : 'Network unavailable or Resident TEST control unavailable. Check IP, port and test mode.';
    }
    _changed();
  }

  Future<void> poll() async {
    if (_busy || _disposed || _paused || !_connectionRetryAllowed) return;
    _busy = true;
    final generation = _generation;
    try {
      if (_session == null) {
        await _connect(generation);
      } else {
        final value = await _post({
          'action': 'heartbeat',
          'session_id': _session,
        });
        if (generation != _generation || _disposed || _paused) return;
        if (value['boot_id'] != state['boot_id']) {
          throw StateError('backend_restarted');
        }
        _accept(value);
        if (_holding && _lease != null) {
          await _command('mute_renew', lease: _lease);
        }
        final events = (state['events'] as List? ?? []).whereType<Map>();
        final own = events.where((e) => e['event_id'] == lastEventId);
        if (own.isNotEmpty) {
          message = switch (own.last['delivery']) {
            'presented' =>
              'TEST presented on Main — physical outputs not verified',
            'user_acknowledged' => 'TEST acknowledged on Main',
            'deferred_real_emergency' =>
              'TEST deferred — real emergency active',
            _ =>
              lastHistoryEventId != null
                  ? 'Saved in Main alert history'
                  : 'Manual trigger awaiting backend persistence',
          };
        }
        _changed();
      }
    } catch (_) {
      _lost();
    } finally {
      _busy = false;
    }
  }

  void _lost() {
    _muteAck.clear();
    ++_holdGeneration;
    _session = null;
    _lease = null;
    _holding = false;
    state = {};
    message =
        'Disconnected — mute state unknown; Pi lease expires automatically';
    _changed();
  }

  Future<Map<String, dynamic>> _command(
    String action, {
    String? lease,
    String? gestureId,
  }) {
    final done = Completer<Map<String, dynamic>>();
    final session = _session, generation = _generation;
    _serial = _serial.then((_) async {
      try {
        if (session == null ||
            session != _session ||
            generation != _generation) {
          throw StateError('session_changed');
        }
        final value = await _post({
          'action': action,
          'session_id': session,
          'sequence': ++_sequence,
          'command_id': _commandId(),
          'lease_id': ?lease,
          'gesture_id': ?gestureId,
        });
        if (session != _session || generation != _generation || _disposed) {
          throw StateError('session_changed');
        }
        _accept(value);
        done.complete(value);
      } catch (error, stack) {
        done.completeError(error, stack);
      }
    });
    return done.future;
  }

  String? _testGestureId;
  Future<void> sendTest({required bool full}) async {
    if (!full || _testGestureId == null) _testGestureId = _commandId();
    final gestureId = _testGestureId!;
    try {
      final result = await _command(
        full ? 'full_test' : 'keyword_test',
        gestureId: gestureId,
      );
      lastEventId = result['event_id'] as String;
      lastHistoryEventId = result['history_event_id'] as String?;
      message = result['history_persisted'] == true
          ? 'Saved in Main alert history'
          : 'Backend update required for persistent manual history';
      _changed();
    } catch (_) {
      _lost();
    }
  }

  Future<void> beginHold() async {
    if (!muteAvailable || _holding) return;
    final holdGeneration = ++_holdGeneration;
    _holding = true;
    message = 'Requesting recognition mute — awaiting KWS acknowledgement';
    _changed();
    try {
      _schedule();
      final result = await _command('mute_start');
      _lease = result['lease_id'] as String;
      if (!_holding || holdGeneration != _holdGeneration) {
        await release();
        return;
      }
      message = muted
          ? 'Listening paused — KWS acknowledged'
          : 'Awaiting KWS mute acknowledgement';
      _changed();
    } catch (_) {
      _lost();
    }
  }

  Future<void> release() async {
    ++_holdGeneration;
    _holding = false;
    final lease = _lease;
    _lease = null;
    if (lease != null) {
      try {
        await _command('mute_end', lease: lease);
        message = state['mute_state'] == 'unmuted'
            ? 'Listening resumed — KWS acknowledged'
            : 'Resuming — awaiting KWS acknowledgement';
      } catch (_) {
        _lost();
      }
    }
    _changed();
  }

  Future<void> pause() async {
    ++_pairingGeneration;
    _paused = true;
    _timer?.cancel();
    await release();
    if (_session != null) {
      try {
        await _command('disconnect');
      } catch (_) {
        /* Lease expiry is independent. */
      }
    }
    ++_generation;
    _lost();
  }

  @override
  void dispose() {
    _muteAck.clear();
    _disposed = true;
    _timer?.cancel();
    unawaited(pause());
    super.dispose();
  }
}
