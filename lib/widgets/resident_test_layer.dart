import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/alert_event.dart';
import '../providers/alerts_provider.dart';
import '../providers/app_services_provider.dart';
import '../providers/connection_provider.dart';
import '../providers/settings_provider.dart';
import '../services/resident_monitor_service.dart';
import '../services/alert_runtime_service.dart';
import 'alert_overlay.dart';

final residentMonitorProvider = Provider<ResidentMonitorService>((ref) {
  final service = ResidentMonitorService();
  ref.onDispose(service.dispose);
  return service;
});

class ResidentTestLayer extends ConsumerStatefulWidget {
  const ResidentTestLayer({super.key, required this.builder});
  final Widget Function(Widget status) builder;
  @override
  ConsumerState<ResidentTestLayer> createState() => _ResidentTestLayerState();
}

class _ResidentTestLayerState extends ConsumerState<ResidentTestLayer>
    with WidgetsBindingObserver {
  late ResidentMonitorService _service;
  late AlertRuntimeService _runtime;
  ResidentTestEvent? _active;
  bool _processing = false, _outputsAuthorized = false, _foreground = true;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _service = ref.read(residentMonitorProvider)..addListener(_update);
    _runtime = ref.read(alertRuntimeServiceProvider);
    Future.microtask(() {
      if (mounted) unawaited(_service.start(ref.read(settingsProvider)));
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
    if (_foreground) {
      unawaited(_service.start(ref.read(settingsProvider)));
    } else {
      _service.stop();
      final event = _active;
      _active = null;
      _outputsAuthorized = false;
      if (event != null) {
        unawaited(_runtime.stopTestEmergency(event.id));
      }
    }
    if (mounted) setState(() {});
  }

  void _update() {
    if (!mounted) return;
    if (!_service.connected) {
      final event = _active;
      _active = null;
      _outputsAuthorized = false;
      if (event != null) {
        unawaited(_runtime.stopTestEmergency(event.id));
      }
    }
    setState(() {});
    if (_foreground &&
        !_processing &&
        _active == null &&
        _service.pending.isNotEmpty) {
      unawaited(_present(_service.pending.first));
    }
  }

  Future<void> _present(ResidentTestEvent event) async {
    _processing = true;
    try {
      if (!await _service.claim(event) ||
          !mounted ||
          !_foreground ||
          !_service.connected) {
        return;
      }
      if (ref.read(alertsProvider).activeAlert != null) {
        await _service.acknowledge(event, 'deferred_real_emergency');
        return;
      }
      setState(() => _active = event);
      // Acknowledge only after Flutter has rendered the TEST presentation.
      await WidgetsBinding.instance.endOfFrame;
      if (!mounted || _active != event || !_foreground) return;
      if (!await _service.acknowledge(event, 'presented')) return;
      if (mounted &&
          _foreground &&
          _active == event &&
          _service.connected &&
          event.full &&
          _outputsAuthorized &&
          ref.read(alertsProvider).activeAlert == null) {
        await ref
            .read(alertRuntimeServiceProvider)
            .startTestEmergency(
              _asAlert(event),
              ref.read(settingsProvider).alertSound,
            );
      }
    } finally {
      _processing = false;
    }
  }

  AlertEvent _asAlert(ResidentTestEvent event) => AlertEvent(
    eventId: event.id,
    keyword: 'Full Alert TEST',
    confidence: 0,
    timestamp: DateTime.now(),
    source: 'resident_test',
    event: 'test_simulation',
  );
  Future<void> _dismiss() async {
    final event = _active;
    if (event == null) return;
    setState(() => _active = null);
    await _runtime.stopTestEmergency(event.id);
    await _service.acknowledge(event, 'user_acknowledged');
    _update();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _service.removeListener(_update);
    _service.stop();
    final event = _active;
    if (event != null) {
      unawaited(_runtime.stopTestEmergency(event.id));
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(connectionProvider.select((s) => s.isConnected), (
      old,
      connected,
    ) {
      if (connected && _foreground) {
        unawaited(_service.start(ref.read(settingsProvider)));
      } else if (!connected) {
        _service.stop();
        _outputsAuthorized = false;
        unawaited(_dismiss());
      }
    });
    ref.listen(settingsProvider, (old, next) {
      if (old?.host != next.host || old?.port != next.port) {
        _outputsAuthorized = false;
        unawaited(_dismiss());
        unawaited(_service.start(next));
      }
    });
    ref.listen(alertsProvider.select((s) => s.activeAlert), (old, next) {
      if (next != null && _active != null) {
        final event = _active!;
        _active = null;
        unawaited(_service.acknowledge(event, 'deferred_real_emergency'));
        // The real controller starts the real emergency immediately after this
        // state update. Its generation/ownership preempts TEST output; do not
        // schedule separate cleanup that could race real output startup.
        setState(() {});
      }
    });
    final realAlert = ref.watch(alertsProvider.select((s) => s.activeAlert));
    final status = Material(
      color: Theme.of(context).colorScheme.surfaceContainerLow,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    _service.message,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
                if (_service.connected)
                  PopupMenuButton<String>(
                    tooltip: 'Resident TEST controls',
                    onSelected: (action) {
                      if (action == 'disable') {
                        unawaited(_service.disableMute());
                      } else if (_active == null) {
                        setState(
                          () => _outputsAuthorized = !_outputsAuthorized,
                        );
                      }
                    },
                    itemBuilder: (_) => [
                      const PopupMenuItem(
                        value: 'disable',
                        child: Text('Disable remote recognition mute'),
                      ),
                      PopupMenuItem(
                        value: 'outputs',
                        enabled: _active == null,
                        child: Text(
                          _outputsAuthorized
                              ? 'Disable TEST audio / vibration'
                              : 'Authorize TEST audio / vibration this session',
                        ),
                      ),
                    ],
                  ),
              ],
            ),
            if (_service.connected)
              Text(
                _service.state['remote_microphone_muted'] == true
                    ? 'REMOTE MICROPHONE MUTED — KWS acknowledged'
                    : _service.state['mute_state'] == 'resuming'
                    ? 'Recognition resuming — awaiting KWS acknowledgement'
                    : _service.state['remote_mute_available'] == true
                    ? 'Remote mute available • TEST mode'
                    : 'Remote mute unavailable',
                style: TextStyle(
                  color: _service.state['remote_microphone_muted'] == true
                      ? Colors.amber
                      : null,
                ),
              ),
            if (_active != null && !_active!.full)
              Row(
                children: [
                  const Expanded(
                    child: Text('KEYWORD SPOTTED TEST / SIMULATION'),
                  ),
                  TextButton(
                    onPressed: _dismiss,
                    child: const Text('Acknowledge TEST'),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
    return Stack(
      children: [
        widget.builder(status),
        if (_active?.full == true && realAlert == null)
          AlertOverlay(
            event: _asAlert(_active!),
            humanDetected: false,
            isTest: true,
            testOutputsEnabled: _outputsAuthorized,
            onDismiss: _dismiss,
          ),
      ],
    );
  }
}
