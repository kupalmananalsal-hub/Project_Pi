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
  static Future<void> saveToken(String host, String value) =>
      storage.write(key: 'caregiver_token_$host', value: value);
}

/// Alternating flushed snapshots keep the preceding valid snapshot on interrupted writes.
/// All callers serialize mutations through the delivery service.
class AlertInbox {
  AlertInbox(this.directory);
  final Directory directory;
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
  }

  Future<void> save() async {
    final next = revision + 1;
    await File(
      '${directory.path}/inbox.${next % 2}.json',
    ).writeAsString(jsonEncode({'revision': next, 'data': data}), flush: true);
    revision = next;
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
  });
  final Uri uri;
  final String installation;
  final String token;
  final AlertInbox inbox;
  final bool Function(AlertEvent) onEvent;
  final void Function(Object) onError;
  final void Function(SocketConnectionStatus) onStatus;
  ReconnectingWebSocketService<Map<String, dynamic>>? _socket;
  StreamSubscription<Map<String, dynamic>>? _messages;
  StreamSubscription<SocketConnectionStatus>? _status;
  Timer? _watchdog;
  Future<void> _work = Future.value();
  bool _closed = false;
  bool _authenticated = false;

  @visibleForTesting
  Future<void> handleMessageForTest(Map<String, dynamic> message) =>
      _handle(message);

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
      _work = _work
          .then((_) async {
            if (!_closed) await _handle(message);
          })
          .catchError((Object error) {
            traceAlert(
              'client_delivery',
              message['event_id']?.toString(),
              'failed',
              {'reason': error.runtimeType.toString()},
            );
            if (!_closed) {
              onError(error);
              _socket?.reconnect();
            }
          });
    }, onError: onError);
    _status = _socket!.status.listen(onStatus);
    _socket!.connect();
  }

  void _send(Map<String, dynamic> message) {
    if (!_closed) {
      _socket?.send(jsonEncode({'protocol_version': 2, ...message}));
    }
  }

  void _flush() {
    for (final message in inbox.outbox.values) {
      _send(Map<String, dynamic>.from(message as Map));
    }
  }

  void _armWatchdog() {
    _watchdog?.cancel();
    _watchdog = Timer(const Duration(seconds: 35), () => _socket?.reconnect());
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
          'cursor': inbox.data['cursor'],
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
        inbox.events[id] = row;
        inbox.ack('ack_received', id, sequence);
        await inbox.save();
        _send(
          Map<String, dynamic>.from(inbox.outbox['ack_received:$id'] as Map),
        );
        final shouldHandle = row['processed'] != true;
        if (shouldHandle) {
          // Commit intent before native side effects; a crash here is an uncertain presentation.
          row['processed'] = true;
          row['disposition'] = 'intent_committed';
          await inbox.save();
          if (_closed) return;
          final present = message['present'] == true;
          final presented = onEvent(
            AlertEvent.fromMessage({
              ...event,
              'type': present ? 'live' : 'historical',
            }),
          );
          row['disposition'] = presented ? 'presented' : 'history_or_notice';
          if (presented) inbox.ack('ack_presented', id, sequence);
          await inbox.save();
          if (presented) {
            _send(
              Map<String, dynamic>.from(
                inbox.outbox['ack_presented:$id'] as Map,
              ),
            );
          }
        } else {
          traceAlert('provider_disposition', id, 'duplicate_ignored', {
            'reason': 'durable_inbox',
          });
        }
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
