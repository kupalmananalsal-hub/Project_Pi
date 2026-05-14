import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../services/alert_runtime_service.dart';

final alertRuntimeServiceProvider = Provider<AlertRuntimeService>((ref) {
  final service = AlertRuntimeService();
  ref.onDispose(service.dispose);
  return service;
});
