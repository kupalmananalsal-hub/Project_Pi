import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';

import '../services/resident_control_client.dart';
import '../services/alert_runtime_service.dart';
import '../models/alert_event.dart';
import '../widgets/alert_overlay.dart';
import 'resident_settings_screen.dart';

class ResidentModeScreen extends StatefulWidget {
  const ResidentModeScreen({super.key, this.control});
  final ResidentControlClient? control;
  @override
  State<ResidentModeScreen> createState() => _ResidentModeScreenState();
}

class _ResidentModeScreenState extends State<ResidentModeScreen>
    with WidgetsBindingObserver {
  late final ResidentControlClient _control;
  bool _pressed = false;
  final _audio = AlertRuntimeService();
  final _tapClock = Stopwatch()..start();
  Timer? _holdTimer;
  int? _pointer, _firstTapAt;
  Offset? _pointerOrigin;
  bool _longPress = false;
  bool? _fullTest;
  String? _audioError;

  void _pointerDown(PointerDownEvent event) {
    if (_pointer != null) return;
    _pointer = event.pointer;
    _pointerOrigin = event.position;
    _longPress = false;
    setState(() => _pressed = true);
    _holdTimer = Timer(const Duration(milliseconds: 500), () {
      _longPress = true;
      _firstTapAt = null;
      unawaited(_control.beginHold());
    });
  }

  void _tap() {
    final now = _tapClock.elapsedMilliseconds;
    final full = _firstTapAt != null && now - _firstTapAt! <= 300;
    _firstTapAt = full ? null : now;
    setState(() {
      _fullTest = full;
      _audioError = null;
    });
    // Foreground output and the authenticated command start independently.
    unawaited(
      _audio.playForegroundTest(full: full).catchError((Object _) {
        if (mounted)
          setState(
            () => _audioError =
                'Local TEST audio unavailable; check device audio output.',
          );
      }),
    );
    unawaited(_control.sendTest(full: full));
  }

  void _stopTest() {
    setState(() => _fullTest = null);
    unawaited(_audio.stopForegroundTest());
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _control = widget.control ?? ResidentControlClient();
    _control.addListener(_update);
    unawaited(_control.connectSaved());
  }

  void _update() {
    if (mounted) setState(() {});
  }

  void _release() {
    _holdTimer?.cancel();
    _pointer = null;
    if (mounted) setState(() => _pressed = false);
    unawaited(_control.release());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_control.connectSaved());
    } else {
      _holdTimer?.cancel();
      _pointer = null;
      _firstTapAt = null;
      _fullTest = null;
      unawaited(_audio.stopForegroundTest());
      _pressed = false;
      unawaited(_control.pause());
    }
  }

  @override
  void dispose() {
    _holdTimer?.cancel();
    unawaited(_audio.dispose());
    WidgetsBinding.instance.removeObserver(this);
    _control.removeListener(_update);
    if (widget.control == null) {
      _control.dispose();
    } else {
      unawaited(_control.pause());
    }
    super.dispose();
  }

  Future<void> _settings() async {
    _stopTest();
    await _control.pause();
    if (!mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => const ResidentSettingsScreen()),
    );
    if (mounted) await _control.connectSaved();
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    final diameter = math.min(size.width * .82, size.height * .48);
    return Stack(
      children: [
        Scaffold(
          backgroundColor: Colors.black,
          body: SafeArea(
            child: LayoutBuilder(
              builder: (context, constraints) => SingleChildScrollView(
                child: ConstrainedBox(
                  constraints: BoxConstraints(minHeight: constraints.maxHeight),
                  child: Column(
                    children: [
                      Row(
                        children: [
                          const SizedBox(width: 16),
                          Expanded(
                            child: Text(
                              _control.connected
                                  ? 'Pi connected • TEST mode'
                                  : 'Pi disconnected',
                              style: const TextStyle(color: Colors.white70),
                            ),
                          ),
                          IconButton(
                            key: const ValueKey('resident-settings-button'),
                            tooltip: 'Settings',
                            onPressed: _settings,
                            icon: const Icon(
                              Icons.settings_outlined,
                              color: Colors.white70,
                            ),
                          ),
                        ],
                      ),
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 24),
                        child: Center(
                          child: Listener(
                            onPointerDown: _pointerDown,
                            onPointerMove: (event) {
                              if (event.pointer == _pointer &&
                                  _pointerOrigin != null &&
                                  (event.position - _pointerOrigin!).distance >
                                      24) {
                                _longPress = true;
                                _release();
                              }
                            },
                            onPointerUp: (event) {
                              if (event.pointer != _pointer) return;
                              final tap = !_longPress;
                              _release();
                              if (tap) _tap();
                            },
                            onPointerCancel: (_) => _release(),
                            child: Semantics(
                              key: const ValueKey('resident-control-button'),
                              button: true,
                              label:
                                  'Keyword TEST. Double tap for Full Alert TEST.',
                              onTap: _tap,
                              child: AnimatedContainer(
                                duration: const Duration(milliseconds: 150),
                                width: diameter,
                                height: diameter,
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: _pressed
                                      ? const Color(0xFFB71C1C)
                                      : const Color(0xFFE53935),
                                ),
                                alignment: Alignment.center,
                                child: const Text(
                                  'HELP',
                                  style: TextStyle(
                                    color: Colors.white,
                                    fontSize: 54,
                                    fontWeight: FontWeight.w900,
                                    letterSpacing: 3,
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 24),
                        child: Text(
                          'Tap: Keyword TEST\nDouble tap: Full Alert TEST\nHold-to-mute: ${_control.muteAvailable ? 'available with Pi authorization' : 'disabled'}',
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            color: Colors.white70,
                            height: 1.6,
                          ),
                        ),
                      ),
                      Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          children: [
                            if (_fullTest == false) ...[
                              const Text(
                                'KEYWORD SPOTTED',
                                style: TextStyle(
                                  color: Colors.amber,
                                  fontSize: 28,
                                  fontWeight: FontWeight.w900,
                                ),
                              ),
                              const Text(
                                'TEST / SIMULATION',
                                style: TextStyle(color: Colors.white70),
                              ),
                              TextButton(
                                onPressed: _stopTest,
                                child: const Text('Stop TEST sound'),
                              ),
                            ],
                            if (_audioError != null)
                              Text(
                                _audioError!,
                                style: const TextStyle(color: Colors.amber),
                              ),
                            Text(
                              _control.muted
                                  ? 'Listening paused — acknowledged by KWS'
                                  : _control.holding
                                  ? 'Awaiting KWS mute acknowledgement'
                                  : _control.state['mute_state'] == 'resuming'
                                  ? 'Resuming — awaiting KWS acknowledgement'
                                  : _control.state['mute_state'] == 'unmuted'
                                  ? 'Listening resumed — acknowledged by KWS'
                                  : _control.muteAvailable
                                  ? 'Remote mute available'
                                  : 'Remote mute unavailable',
                              key: const ValueKey('resident-mute-state'),
                              textAlign: TextAlign.center,
                              style: const TextStyle(
                                color: Colors.amber,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              _control.message,
                              key: const ValueKey('resident-send-status'),
                              textAlign: TextAlign.center,
                              style: const TextStyle(color: Colors.white70),
                            ),
                            if (_control.connected)
                              Text(
                                _control.state['main_connected'] == true
                                    ? 'Main App recently seen'
                                    : 'Main App not recently seen',
                                textAlign: TextAlign.center,
                                style: const TextStyle(color: Colors.white54),
                              ),
                            const SizedBox(height: 8),
                            const Text(
                              'TEST controls do not replace a real emergency call.',
                              textAlign: TextAlign.center,
                              style: TextStyle(color: Colors.white54),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
        if (_fullTest == true)
          AlertOverlay(
            event: AlertEvent(
              eventId: 'test-local-resident',
              keyword: 'Full Alert TEST',
              confidence: 0,
              timestamp: DateTime.now(),
              source: 'resident_test',
              event: 'test_simulation',
            ),
            humanDetected: false,
            isTest: true,
            testOutputsEnabled: true,
            onDismiss: _stopTest,
          ),
      ],
    );
  }
}
