import 'package:flutter/material.dart';

class ConnectionIndicator extends StatelessWidget {
  const ConnectionIndicator({
    super.key,
    required this.connected,
    required this.connecting,
  });

  final bool connected;
  final bool connecting;

  @override
  Widget build(BuildContext context) {
    final color = connecting
        ? Colors.amber
        : connected
        ? Colors.greenAccent
        : Colors.redAccent;
    final label = connecting
        ? 'Connecting'
        : connected
        ? 'Connected'
        : 'Disconnected';

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 12,
          height: 12,
          decoration: BoxDecoration(
            color: color,
            shape: BoxShape.circle,
            boxShadow: [
              BoxShadow(color: color.withValues(alpha: 0.5), blurRadius: 10),
            ],
          ),
        ),
        const SizedBox(width: 8),
        Text(label),
      ],
    );
  }
}
