import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:thermal_audio_monitor/services/resident_alert_service.dart';

class _ScriptedAdapter implements HttpClientAdapter {
  _ScriptedAdapter(this.script);

  /// Per attempt: null = network failure, otherwise the HTTP status to return.
  final List<int?> script;
  final eventIds = <String>[];

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    eventIds.add((options.data as Map)['event_id'] as String);
    final status = script.removeAt(0);
    if (status == null) throw const SocketException('Network is unreachable');
    return ResponseBody.fromString(
      jsonEncode({'ok': true}),
      status,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({'host': '10.0.0.5'}));

  test(
    'panic alert retries through a network blip with one event_id',
    () async {
      final adapter = _ScriptedAdapter([null, null, 200]);
      final service = ResidentAlertService(
        dio: Dio()..httpClientAdapter = adapter,
      );

      expect(await service.sendManualAlert(), isTrue);
      expect(adapter.eventIds.length, 3);
      expect(adapter.eventIds.toSet().length, 1);
    },
  );

  test('a rejected token is not retried', () async {
    final adapter = _ScriptedAdapter([401, 200]);
    final service = ResidentAlertService(
      dio: Dio()..httpClientAdapter = adapter,
    );

    expect(await service.sendManualAlert(), isFalse);
    expect(adapter.eventIds.length, 1);
  });

  test('gives up after the retry window', () async {
    final adapter = _ScriptedAdapter(List.filled(10, null, growable: true));
    final service = ResidentAlertService(
      dio: Dio()..httpClientAdapter = adapter,
      retryWindow: const Duration(seconds: 1),
    );

    expect(await service.sendManualAlert(), isFalse);
    expect(adapter.eventIds.length, lessThan(4));
  });
}
