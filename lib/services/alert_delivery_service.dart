import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:path_provider/path_provider.dart';
import 'package:flutter/foundation.dart';

import '../models/alert_event.dart';
import 'alert_trace.dart';
import 'reconnecting_web_socket_service.dart';

enum AlertPairingState { legacy, reliable, reconfigurationRequired }

class CaregiverCredentials {
  static const storage = FlutterSecureStorage();
  static String randomId() => List.generate(
    32,
    (_) => Random.secure().nextInt(16).toRadixString(16),
  ).join();
  static Future<String> installationId() async {
    final old = await storage.read(key: 'caregiver_installation');
    if (old != null) return old;
    final id = randomId();
    await storage.write(key: 'caregiver_installation', value: id);
    return id;
  }

  static Future<String?> token(String host) =>
      storage.read(key: 'caregiver_token_$host');
  static Future<AlertPairingState> endpointState(String host) async {
    final values = await storage.readAll();
    // Migrate pre-marker installations by inspecting all saved endpoint keys.
    final hasPairing =
        values['caregiver_pairing_required'] == 'true' ||
        values.entries.any(
          (e) => e.key.startsWith('caregiver_token_') && e.value.isNotEmpty,
        );
    if (hasPairing) {
      await storage.write(key: 'caregiver_pairing_required', value: 'true');
      return (values['caregiver_token_$host']?.isNotEmpty ?? false)
          ? AlertPairingState.reliable
          : AlertPairingState.reconfigurationRequired;
    }
    return AlertPairingState.legacy;
  }

  static Future<void> saveToken(String host, String value) async {
    // Persist the downgrade guard first; interrupted pairing must fail closed.
    await storage.write(key: 'caregiver_pairing_required', value: 'true');
    await storage.write(key: 'caregiver_token_$host', value: value);
  }

  static Future<void> unpair(String administratorSecret) async {
    final values = await storage.readAll();
    final keys = values.keys
        .where((key) => key.startsWith('caregiver_token_'))
        .toList();
    if (administratorSecret.isEmpty ||
        !keys.any((key) => values[key] == administratorSecret)) {
      throw StateError('An existing pairing secret is required to unpair.');
    }
    await storage.write(key: 'caregiver_pairing_required', value: 'true');
    for (final key in keys) {
      await storage.delete(key: key);
    }
    // Only an explicit completed administrator action enables legacy mode.
    await storage.write(key: 'caregiver_pairing_required', value: 'false');
  }
}

/// Alternating flushed snapshots keep the preceding valid snapshot on interrupted writes.
/// All callers serialize mutations through the delivery service.
class AlertInbox {
  AlertInbox(this.directory, {this.writeSnapshot});
  final Directory directory;
  final Future<void> Function(File file, String contents)? writeSnapshot;
  String? _committed;
  int revision = 0;
  Map<String, dynamic> data = {
    'instance': '',
    'cursor': 0,
    'events': <String, dynamic>{},
    'outbox': <String, dynamic>{},
  };
  Map<String, dynamic> get events => data['events'] as Map<String, dynamic>;
  Map<String, dynamic> get outbox => data['outbox'] as Map<String, dynamic>;
  Future<void> load() async {
    await directory.create(recursive: true);
    var exists = false;
    var valid = false;
    for (var slot = 0; slot < 2; slot++) {
      final file = File('${directory.path}/inbox.$slot.json');
      if (!await file.exists()) continue;
      exists = true;
      try {
        final snapshot =
            jsonDecode(await file.readAsString()) as Map<String, dynamic>;
        final next = snapshot['revision'] as int;
        final payload = snapshot['data'] as Map<String, dynamic>;
        if (payload['events'] is! Map ||
            payload['outbox'] is! Map ||
            payload['cursor'] is! int) {
          continue;
        }
        valid = true;
        if (next > revision) {
          revision = next;
          data = payload;
        }
      } catch (_) {
        /* Try the preceding snapshot. */
      }
    }
    if (exists && !valid) throw StateError('alert_inbox_corrupt');
    _committed = jsonEncode(data);
  }

  /// Every save rewrites the whole inbox, so it must not grow for the app's lifetime.
  /// A pruned event that is replayed later is only shown as history: replay
  /// re-presents critical events for 300 s, far less than 500 events back.
  static const maxEvents = 500;

  void _prune() {
    if (events.length <= maxEvents) return;
    final unacked = {for (final m in outbox.values) (m as Map)['event_id']};
    int sequence(String id) =>
        ((events[id] as Map)['event'] as Map)['sequence'] as int? ?? 0;
    final removable = events.keys.where((id) => !unacked.contains(id)).toList()
      ..sort((a, b) => sequence(a).compareTo(sequence(b)));
    for (final id in removable.take(events.length - maxEvents)) {
      events.remove(id);
    }
  }

  Future<void> save() async {
    _prune();
    final next = revision + 1;
    final file = File('${directory.path}/inbox.${next % 2}.json');
    final contents = jsonEncode({'revision': next, 'data': data});
    try {
      if (writeSnapshot != null) {
        await writeSnapshot!(file, contents);
      } else {
        await file.writeAsString(contents, flush: true);
      }
    } catch (_) {
      if (_committed != null) {
        data = jsonDecode(_committed!) as Map<String, dynamic>;
      }
      rethrow;
    }
    revision = next;
    _committed = jsonEncode(data);
  }

  void ack(String kind, String id, int sequence) {
    outbox['$kind:$id'] = {
      'protocol_version': 2,
      'type': kind,
      'event_id': id,
      'sequence': sequence,
    };
  }
}

class AlertDeliveryService {
  AlertDeliveryService({
    required this.uri,
    required this.installation,
    required this.token,
    required this.inbox,
    required this.onEvent,
    required this.onError,
    required this.onStatus,
    this.isActive,
    this.afterIntent,
    this.onSendForTest,
  });
  final Uri uri;
  final String installation;
  final String token;
  final AlertInbox inbox;
  final bool Function(AlertEvent) onEvent;
  final void Function(Object) onError;
  final void Function(SocketConnectionStatus) onStatus;
  final bool Function(String eventId)? isActive;
  final Future<void> Function()? afterIntent;
  @visibleForTesting
  final void Function(Map<String, dynamic>)? onSendForTest;
  final Set<String> _handledThisRun = {};
  int _sessionGeneration = 0;
  ReconnectingWebSocketService<Map<String, dynamic>>? _socket;
  StreamSubscription<Map<String, dynamic>>? _messages;
  StreamSubscription<SocketConnectionStatus>? _status;
  Timer? _watchdog;
  Future<void> _work = Future.value();
  bool _closed = false;
  bool _authenticated = false;

  @visibleForTesting
  Future<void> handleMessageForTest(Map<String, dynamic> message) => runZoned(
    () => _handle(message),
    zoneValues: {#deliverySession: _sessionGeneration},
  );

  @visibleForTesting
  void invalidateSessionForTest() {
    _sessionGeneration++;
  }

  static Future<AlertInbox> openInbox(String host, String installation) async {
    final root = await getApplicationSupportDirectory();
    final name = base64Url.encode(utf8.encode(host)).replaceAll('=', '');
    final inbox = AlertInbox(
      Directory('${root.path}/alert_delivery/$installation/$name'),
    );
    await inbox.load();
    return inbox;
  }

  void connect() {
    _socket = ReconnectingWebSocketService<Map<String, dynamic>>(
      uri: uri.replace(queryParameters: {'protocol': '2'}),
      parser: (message) =>
          jsonDecode(message as String) as Map<String, dynamic>,
      onReady: () {
        _sessionGeneration++;
        _authenticated = false;
        _send({
          'type': 'authenticate',
          'installation_id': installation,
          'token': token,
        });
        _armWatchdog();
      },
    );
    _messages = _socket!.messages.listen((message) {
      final generation = _sessionGeneration;
      _work = _work
          .then((_) async {
            if (!_closed && generation == _sessionGeneration) {
              await runZoned(
                () => _handle(message),
                zoneValues: {#deliverySession: generation},
              );
            }
          })
          .catchError((Object error) {
            traceAlert(
              'client_delivery',
              message['event_id']?.toString(),
              'failed',
              {'reason': error.runtimeType.toString()},
            );
            if (!_closed && generation == _sessionGeneration) {
              onError(error);
              _socket?.reconnect();
            }
          });
    }, onError: onError);
    _status = _socket!.status.listen((status) {
      if (status == SocketConnectionStatus.reconnecting ||
          status == SocketConnectionStatus.disconnected) {
        _sessionGeneration++;
        _authenticated = false;
      }
      onStatus(status);
    });
    _socket!.connect();
  }

  void _send(Map<String, dynamic> message) {
    final session = Zone.current[#deliverySession];
    if (!_closed && (session == null || session == _sessionGeneration)) {
      onSendForTest?.call(message);
      _socket?.send(jsonEncode({'protocol_version': 2, ...message}));
    }
  }

  static Map<String, dynamic> _ack(String kind, String id, int sequence) => {
    'type': kind,
    'event_id': id,
    'sequence': sequence,
  };

  void _flush() {
    for (final message in inbox.outbox.values) {
      _send(Map<String, dynamic>.from(message as Map));
    }
  }

  void _armWatchdog() {
    _watchdog?.cancel();
    // The Pi sends a heartbeat every 5 s, so 12 s of silence means the session is dead.
    _watchdog = Timer(const Duration(seconds: 12), () => _socket?.reconnect());
  }

  Future<void> _handle(Map<String, dynamic> message) async {
    if (message['protocol_version'] != 2) {
      throw const FormatException('delivery_version');
    }
    _armWatchdog();
    switch (message['type']) {
      case 'connected':
        _authenticated = true;
        final instance = message['instance'] as String;
        if (inbox.data['instance'] != instance ||
            (inbox.data['cursor'] as int) >
                (message['high_water'] as int? ?? 0)) {
          // Keep UUID dispositions across database restore; invalidate only its cursor/outbox.
          inbox.data['instance'] = instance;
          inbox.data['cursor'] = 0;
          inbox.outbox.clear();
          await inbox.save();
        }
        // Commit cursors only after all preceding dispositions. An interrupted
        // page is replayed and durable UUIDs suppress its completed entries.
        _send({
          'type': 'replay_request',
          'cursor': min(
            inbox.data['cursor'] as int,
            message['recovery_cursor'] as int? ?? inbox.data['cursor'] as int,
          ),
          'instance': instance,
        });
        _flush();
      case 'heartbeat':
        _send({'type': 'heartbeat_ack', 'nonce': message['nonce']});
      case 'alert':
        if (!_authenticated) throw StateError('unauthenticated_delivery');
        final id = message['event_id'] as String;
        final sequence = message['sequence'] as int;
        final event = Map<String, dynamic>.from(message['event'] as Map);
        if (event['event_id'] != id || event['sequence'] != sequence) {
          throw const FormatException('event_identity');
        }
        final existing = inbox.events[id] as Map<String, dynamic>?;
        final row =
            existing ?? <String, dynamic>{'event': event, 'processed': false};
        final confirmed =
            row['user_confirmed'] == true ||
            inbox.outbox.containsKey('ack_user_confirmed:$id');
        final recovery =
            message['delivery_mode'] == 'replay' &&
            event['decision_state'] == 'critical' &&
            message['present'] == true;
        final active = isActive?.call(id) ?? false;
        final shouldHandle =
            !confirmed &&
            !active &&
            !_handledThisRun.contains(id) &&
            (row['processed'] != true || recovery);
        // A failed save (e.g. phone storage full) must not swallow the alarm: present
        // anyway, but send no acknowledgement the phone has not durably recorded, then
        // fail the session so the Pi re-offers it. _handledThisRun keeps that
        // re-offer from sounding the alarm a second time in this run.
        Object? storageError;
        Future<void> save() async {
          if (storageError != null) return;
          try {
            await inbox.save();
          } catch (error) {
            storageError = error;
          }
        }

        inbox.events[id] = row;
        inbox.ack('ack_received', id, sequence);
        await save();
        if (storageError == null) _send(_ack('ack_received', id, sequence));
        if (shouldHandle) {
          // Intent is evidence of an attempt, never confirmation or a replay veto.
          row['disposition'] = 'intent_committed';
          await save();
          await afterIntent?.call();
          final session = Zone.current[#deliverySession];
          if (_closed || (session != null && session != _sessionGeneration)) {
            return;
          }
          final present = message['present'] == true;
          final presented = onEvent(
            AlertEvent.fromMessage({
              ...event,
              'type': present ? 'live' : 'historical',
            }),
          );
          row['disposition'] = presented ? 'presented' : 'history_or_notice';
          row['processed'] = true;
          _handledThisRun.add(id);
          if (presented) inbox.ack('ack_presented', id, sequence);
          await save();
          if (presented && storageError == null) {
            _send(_ack('ack_presented', id, sequence));
          }
        } else {
          traceAlert('provider_disposition', id, 'duplicate_ignored', {
            'reason': 'durable_inbox',
          });
        }
        if (storageError != null) throw storageError!;
      case 'ack_committed':
        inbox.outbox.remove(
          '${message['acknowledgement']}:${message['event_id']}',
        );
        await inbox.save();
      case 'replay_complete':
        inbox.data['cursor'] = message['cursor'] as int;
        await inbox.save();
        if (message['more'] == true) {
          _send({
            'type': 'replay_request',
            'cursor': message['cursor'],
            'instance': message['instance'],
          });
        }
      default:
        throw const FormatException('unknown_delivery_message');
    }
  }

  Future<void> confirm(String id) {
    final done = _work.then((_) async {
      final row = inbox.events[id] as Map<String, dynamic>?;
      if (row == null) return;
      final event = row['event'] as Map;
      row['user_confirmed'] = true;
      inbox.ack('ack_user_confirmed', id, event['sequence'] as int);
      await inbox.save();
      if (_authenticated) {
        _send(
          Map<String, dynamic>.from(
            inbox.outbox['ack_user_confirmed:$id'] as Map,
          ),
        );
      }
    });
    _work = done.catchError((Object error) {
      if (!_closed) onError(error);
    });
    return done;
  }

  Future<void> dispose() async {
    _closed = true;
    _watchdog?.cancel();
    await _messages?.cancel();
    await _status?.cancel();
    await _socket?.dispose();
    await _work;
  }
}
