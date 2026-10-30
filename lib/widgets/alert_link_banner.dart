import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../providers/alerts_provider.dart';
import '../providers/connection_provider.dart';
import '../services/reconnecting_web_socket_service.dart';

/// Red banner shown while the alert link to the Pi is down, so a caregiver never
/// mistakes a silent phone for a quiet room. Waits 10 s so routine reconnects don't flash it.
class AlertLinkBanner extends ConsumerStatefulWidget {
  const AlertLinkBanner({super.key});

  static const delay = Duration(seconds: 10);

  @override
  ConsumerState<AlertLinkBanner> createState() => _AlertLinkBannerState();
}

class _AlertLinkBannerState extends ConsumerState<AlertLinkBanner> {
  Timer? _timer;
  bool _visible = false;

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final alerts = ref.watch(alertsProvider);
    final userDisconnected = ref.watch(
      connectionProvider.select((state) => state.userRequestedDisconnect),
    );
    final linkDown =
        !userDisconnected &&
        alerts.socketStatus != SocketConnectionStatus.connected;

    if (!linkDown) {
      _timer?.cancel();
      _timer = null;
      _visible = false;
    } else if (!_visible && _timer == null) {
      _timer = Timer(AlertLinkBanner.delay, () {
        if (mounted) setState(() => _visible = true);
      });
    }
    if (!_visible) return const SizedBox.shrink();

    final colors = Theme.of(context).colorScheme;
    return Material(
      key: const ValueKey('alert-link-banner'),
      color: colors.error,
      child: SafeArea(
        bottom: false,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
          child: Row(
            children: [
              Icon(Icons.notifications_off_rounded, color: colors.onError),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Alerts are NOT being received from the Pi.'
                  '${alerts.error == null ? ' Reconnecting...' : '\n${alerts.error}'}',
                  style: TextStyle(
                    color: colors.onError,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
