import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';

import '../services/resident_control_client.dart';
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
    if (mounted) setState(() => _pressed = false);
    unawaited(_control.release());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(_control.connectSaved());
    } else {
      _pressed = false;
      unawaited(_control.pause());
    }
  }

  @override
  void dispose() {
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
    return Scaffold(
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
                        onPointerCancel: (_) => _release(),
                        child: GestureDetector(
                          key: const ValueKey('resident-control-button'),
                          onTap: () => _control.sendTest(full: false),
                          onDoubleTap: () => _control.sendTest(full: true),
                          onLongPressStart: (_) {
                            setState(() => _pressed = true);
                            // Consume the long press without sending tap or mute commands.
                          },
                          onLongPressEnd: (_) => _release(),
                          onLongPressCancel: _release,
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
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 24),
                    child: Text(
                      'Tap: Keyword TEST\nDouble tap: Full Alert TEST\nHold-to-mute: disabled',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.white70, height: 1.6),
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      children: [
                        Text(
                          _control.muted
                              ? 'MUTED — acknowledged by KWS'
                              : _control.holding
                              ? 'Awaiting KWS mute acknowledgement'
                              : _control.state['mute_state'] == 'resuming'
                              ? 'Resuming — awaiting KWS acknowledgement'
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
    );
  }
}
