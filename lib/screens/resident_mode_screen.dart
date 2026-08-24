import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../services/resident_alert_service.dart';

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

  static const Color _idleRed = Color(0xFFE53935);
  static const Color _darkerRed = Color(0xFFB71C1C);

  @override
  void initState() {
    super.initState();
    _alertService = widget.alertService ?? ResidentAlertService();
  }

  Future<void> _handleHelpPressed() async {
    if (_isSending) return;

    setState(() {
      _isPressed = true;
      _isSending = true;
    });

    HapticFeedback.heavyImpact();

    // 200ms visual confirmation delay
    await Future<void>.delayed(const Duration(milliseconds: 200));
    if (mounted) {
      setState(() {
        _isPressed = false;
      });
    }

    final success = await _alertService.sendManualAlert(
      keyword: 'manual',
      confidence: 1.0,
      source: 'manual_button',
    );

    if (mounted) {
      setState(() {
        _isSending = false;
      });

      ScaffoldMessenger.of(context).clearSnackBars();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            success ? 'Alert sent' : 'Failed to send',
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.bold,
              fontSize: 16,
            ),
          ),
          backgroundColor: success ? Colors.green.shade800 : Colors.red.shade900,
          duration: const Duration(seconds: 2),
          behavior: SnackBarBehavior.floating,
          margin: const EdgeInsets.symmetric(horizontal: 48, vertical: 24),
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
    final buttonSize = math.min(screenSize.width * 0.6, screenSize.height * 0.6);

    return Scaffold(
      backgroundColor: Colors.black,
      body: Center(
        child: SizedBox(
          width: buttonSize,
          height: buttonSize,
          child: GestureDetector(
            onTap: _handleHelpPressed,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 150),
              decoration: BoxDecoration(
                color: _isPressed ? _darkerRed : _idleRed,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: (_isPressed ? _darkerRed : _idleRed).withValues(alpha: 0.5),
                    blurRadius: _isPressed ? 12 : 28,
                    spreadRadius: _isPressed ? 2 : 6,
                  ),
                ],
              ),
              alignment: Alignment.center,
              child: const Text(
                'HELP',
                style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w900,
                  fontSize: 38,
                  letterSpacing: 2.0,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
