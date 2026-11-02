import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/app_settings.dart';
import 'api_token.dart';
import 'mute_acknowledgement.dart';

class ResidentTestEvent {
  const ResidentTestEvent(this.id, this.full);
  final String id;
  final bool full;
  static ResidentTestEvent? parse(Map value) {
    final id = value['event_id'];
    if (value['is_test'] != true ||
        id is! String ||
        !id.startsWith('test-') ||
        !['keyword_test', 'full_test'].contains(value['kind'])) {
      return null;
    }
    return ResidentTestEvent(id, value['kind'] == 'full_test');
  }
}

/// Independent TEST channel. Never feeds AlertsController or the durable inbox.
class ResidentMonitorService extends ChangeNotifier {
  ResidentMonitorService({Dio? dio}) : _dio = dio ?? Dio();
  final Dio _dio;
  final _muteAck = MuteAcknowledgement();
  Timer? _timer;
  int _generation = 0;
  bool _disposed = false, _busy = false;
  AppSettings? _settings;
  SharedPreferences? _prefs;
  final Set<String> _seen = {};
  final List<ResidentTestEvent> pending = [];
  Map<String, dynamic> state = {};
  bool connected = false;
  String message = 'Resident TEST channel unavailable';
  String get _seenKey =>
      'resident_test_seen:${_settings?.host}:${_settings?.port}';
  void _changed() {
    if (!_disposed) notifyListeners();
  }

  Future<void> start(AppSettings settings) async {
    stop();
    if (ApiToken.current.isEmpty) {
      message = 'Resident TEST channel requires Main API authentication';
      _changed();
      return;
    }
    _settings = settings;
    final generation = _generation;
    final prefs = await SharedPreferences.getInstance();
    if (_disposed || generation != _generation) return;
    _prefs = prefs;
    _seen
      ..clear()
      ..addAll(prefs.getStringList(_seenKey) ?? []);
    await poll();
    if (!_disposed && generation == _generation) {
      _timer = Timer.periodic(const Duration(seconds: 1), (_) => poll());
    }
  }

  Future<void> poll() async {
    final settings = _settings, generation = _generation;
    if (_busy || _disposed || settings == null) return;
    _busy = true;
    try {
      final elapsed = Stopwatch()..start();
      final response = await _dio
          .getUri<Map<String, dynamic>>(
            settings.httpUri('/api/resident/main'),
            options: Options(
              headers: ApiToken.headers,
              receiveTimeout: const Duration(seconds: 2),
            ),
          )
          .timeout(const Duration(seconds: 3));
      if (_disposed || generation != _generation) return;
      final value = response.data!;
      _muteAck.apply(value, elapsed.elapsed, _changed);
      if (value['test_mode'] != true || value['boot_id'] is! String) {
        throw StateError('incompatible_protocol');
      }
      connected = true;
      state = value;
      message = value['resident_connected'] == true
          ? 'Resident connected • TEST mode'
          : 'Resident disconnected • TEST mode';
      for (final row in (value['events'] as List? ?? []).whereType<Map>()) {
        final event = ResidentTestEvent.parse(row);
        if (event != null &&
            !_seen.contains(event.id) &&
            row['delivery'] == 'backend_accepted' &&
            !pending.any((e) => e.id == event.id)) {
          pending.add(event);
        }
      }
      _changed();
    } catch (_) {
      if (_disposed || generation != _generation) return;
      connected = false;
      state = {};
      pending.clear();
      message =
          'Resident TEST channel unavailable — check Pi test mode and Main authentication';
      _changed();
    } finally {
      _busy = false;
    }
  }

  Future<bool> claim(ResidentTestEvent event) async {
    if (_seen.contains(event.id) || !connected || _prefs == null) return false;
    if (_seen.length >= 4096) {
      message = 'TEST presentation blocked: deduplication capacity reached';
      _changed();
      return false;
    }
    _seen.add(event.id);
    final generation = _generation;
    try {
      // Persist BEFORE presentation: reconnect/restart cannot restart a test siren.
      if (!await _prefs!.setStringList(_seenKey, _seen.toList())) {
        throw StateError('dedup_storage_failed');
      }
      if (_disposed || generation != _generation || !connected) return false;
      pending.removeWhere((e) => e.id == event.id);
      return true;
    } catch (_) {
      message = 'TEST presentation blocked: durable deduplication unavailable';
      _changed();
      return false;
    }
  }

  Future<bool> acknowledge(ResidentTestEvent event, String disposition) =>
      _post({'event_id': event.id, 'disposition': disposition});
  Future<bool> disableMute() => _post({'action': 'disable_mute'});
  Future<bool> _post(Map<String, dynamic> body) async {
    final settings = _settings, generation = _generation;
    if (settings == null) return false;
    try {
      await _dio
          .postUri(
            settings.httpUri('/api/resident/main'),
            data: jsonEncode(body),
            options: Options(
              headers: ApiToken.headers,
              contentType: Headers.jsonContentType,
              receiveTimeout: const Duration(seconds: 2),
            ),
          )
          .timeout(const Duration(seconds: 3));
      return !_disposed && generation == _generation;
    } catch (_) {
      if (_disposed || generation != _generation) return false;
      message =
          'TEST acknowledgement delivery failed — backend acceptance is not presentation';
      _changed();
      return false;
    }
  }

  void stop() {
    _muteAck.clear();
    ++_generation;
    _timer?.cancel();
    _settings = null;
    connected = false;
    state = {};
    pending.clear();
  }

  @override
  void dispose() {
    _disposed = true;
    stop();
    super.dispose();
  }
}
