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
        if (connecting)
          const SizedBox(
            width: 16,
            height: 16,
            child: CircularProgressIndicator(strokeWidth: 2),
          )
        else
          Container(
            width: 12,
            height: 12,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
        const SizedBox(width: 8),
        Flexible(
          child: Text(
            label,
            style: const TextStyle(fontWeight: FontWeight.w600),
          ),
        ),
      ],
    );
  }
}
