import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Android foreground service (MonitoringService.kt) that keeps alerts arriving
/// with the screen off. iOS has no equivalent for a LAN socket: alerts there
/// only arrive while the app is in the foreground.
class BackgroundMonitoring {
  static const _channel = MethodChannel('project_pi/monitoring');
  static bool _askedBatteryExemption = false;

  static Future<void> start() async {
    if (!Platform.isAndroid) return;
    try {
      await _channel.invokeMethod<void>('start');
      // Ask once per app run: Doze can otherwise still delay network access.
      if (!_askedBatteryExemption) {
        _askedBatteryExemption = true;
        await _channel.invokeMethod<bool>('requestBatteryExemption');
      }
    } catch (error) {
      debugPrint('Background monitoring unavailable: $error');
    }
  }

  static Future<void> stop() async {
    if (!Platform.isAndroid) return;
    try {
      await _channel.invokeMethod<void>('stop');
    } catch (error) {
      debugPrint('Background monitoring stop failed: $error');
    }
  }
}
