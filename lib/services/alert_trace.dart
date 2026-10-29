import 'dart:convert';

import 'package:flutter/foundation.dart';

/// JSON-line diagnostic record shared by the Caregiver alert path.
void traceAlert(
  String stage,
  String? eventId,
  String outcome, [
  Map<String, Object?> details = const {},
]) {
  debugPrint(
    jsonEncode({
      'kind': 'alert_trace',
      'timestamp': DateTime.now().toUtc().toIso8601String(),
      'stage': stage,
      'event_id': eventId ?? 'unknown',
      'outcome': outcome,
      ...details,
    }),
  );
}
