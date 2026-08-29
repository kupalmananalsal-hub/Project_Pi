import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/resident_alert_service.dart';
import 'resident_settings_screen.dart';

class ResidentModeScreen extends StatefulWidget {
  const ResidentModeScreen({
    super.key,
    this.alertService,
  });

  final ResidentAlertService? alertService;

  @override
  State<ResidentModeScreen> createState() => _ResidentModeScreenState();
}

class _ResidentModeScreenState extends State<ResidentModeScreen> {
  late final ResidentAlertService _alertService;
  bool _isPressed = false;
  bool _isSending = false;
  DateTime? _lastTapTime;
  Timer? _tapTimer;

  static const Color _idleRed = Color(0xFFE53935);
  static const Color _darkerRed = Color(0xFFB71C1C);

  @override
  void initState() {
    super.initState();
    _alertService = widget.alertService ?? ResidentAlertService();
  }

  @override
  void dispose() {
    _tapTimer?.cancel();
    super.dispose();
  }

  void _openSettings() {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => const ResidentSettingsScreen(),
      ),
    );
  }

  void _handleHelpTap() {
    final now = DateTime.now();
    HapticFeedback.heavyImpact();

    setState(() => _isPressed = true);
    Future.delayed(const Duration(milliseconds: 150), () {
      if (mounted) setState(() => _isPressed = false);
    });

    if (_lastTapTime != null &&
        now.difference(_lastTapTime!) < const Duration(milliseconds: 600)) {
      // Double tap confirmed!
      _tapTimer?.cancel();
      _tapTimer = null;
      _lastTapTime = null;
      _triggerAlert(isDoubleTap: true);
    } else {
      // First tap — wait to see if a second tap follows
      _lastTapTime = now;
      _tapTimer?.cancel();
      _tapTimer = Timer(const Duration(milliseconds: 600), () {
        if (!mounted) return;
        _lastTapTime = null;
        _triggerAlert(isDoubleTap: false);
      });
    }
  }

  Future<void> _triggerAlert({required bool isDoubleTap}) async {
    if (_isSending) return;

    setState(() {
      _isSending = true;
    });

    final success = await _alertService.sendManualAlert(
      keyword: 'manual',
      confidence: isDoubleTap ? 1.0 : 0.75,
      source: isDoubleTap ? 'manual_button' : 'manual_button_single',
    );

    if (mounted) {
      setState(() {
        _isSending = false;
      });

      ScaffoldMessenger.of(context).clearSnackBars();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            success
                ? (isDoubleTap
                    ? 'EMERGENCY ALERT SENT'
                    : 'Notice sent')
                : 'Failed to send alert',
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.bold,
              fontSize: 16,
            ),
          ),
          backgroundColor: success
              ? (isDoubleTap ? Colors.red.shade900 : Colors.orange.shade800)
              : Colors.grey.shade900,
          duration: const Duration(seconds: 2),
          behavior: SnackBarBehavior.floating,
          margin: const EdgeInsets.symmetric(horizontal: 40, vertical: 24),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final screenSize = MediaQuery.of(context).size;
    // Expanded button size for ease of accessibility
    final buttonSize = math.min(screenSize.width * 0.85, screenSize.height * 0.72);

    return Scaffold(
      backgroundColor: Colors.black,
      body: Stack(
        children: [
          // Centered Massive HELP button
          Center(
            child: SizedBox(
              width: buttonSize,
              height: buttonSize,
              child: GestureDetector(
                onTap: _handleHelpTap,
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 150),
                  decoration: BoxDecoration(
                    color: _isPressed ? _darkerRed : _idleRed,
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: (_isPressed ? _darkerRed : _idleRed).withValues(alpha: 0.55),
                        blurRadius: _isPressed ? 16 : 36,
                        spreadRadius: _isPressed ? 4 : 10,
                      ),
                    ],
                  ),
                  alignment: Alignment.center,
                  child: const Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        'HELP',
                        style: TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w900,
                          fontSize: 54,
                          letterSpacing: 3.5,
                        ),
                      ),
                      SizedBox(height: 8),
                      Text(
                        'TAP 2X FOR EMERGENCY',
                        style: TextStyle(
                          color: Colors.white70,
                          fontWeight: FontWeight.w700,
                          fontSize: 13,
                          letterSpacing: 1.2,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),

          // Small unobtrusive gear icon in top-right corner
          SafeArea(
            child: Align(
              alignment: Alignment.topRight,
              child: Padding(
                padding: const EdgeInsets.all(12.0),
                child: IconButton(
                  key: const ValueKey('resident-settings-button'),
                  icon: const Icon(
                    Icons.settings_outlined,
                    color: Colors.white60,
                    size: 26,
                  ),
                  tooltip: 'Settings',
                  onPressed: _openSettings,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
