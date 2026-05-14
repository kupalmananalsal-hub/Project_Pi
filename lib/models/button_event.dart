class ButtonEvent {
  const ButtonEvent({
    required this.pressed,
    this.lastPressedAt,
    this.pressCount,
  });

  final bool pressed;
  final DateTime? lastPressedAt;
  final int? pressCount;

  factory ButtonEvent.fromJson(Map<String, dynamic> json) {
    return ButtonEvent(
      pressed: _asBool(json['pressed'] ?? json['is_pressed'] ?? json['state']),
      lastPressedAt: DateTime.tryParse(
        (json['last_pressed'] ?? json['timestamp'] ?? '').toString(),
      ),
      pressCount: _asInt(json['press_count'] ?? json['count']),
    );
  }

  static bool _asBool(dynamic value) {
    if (value is bool) {
      return value;
    }
    if (value is num) {
      return value != 0;
    }
    if (value is String) {
      final normalized = value.toLowerCase();
      return normalized == 'true' ||
          normalized == 'pressed' ||
          normalized == 'down' ||
          normalized == '1';
    }
    return false;
  }

  static int? _asInt(dynamic value) {
    if (value is int) {
      return value;
    }
    if (value is num) {
      return value.round();
    }
    if (value is String) {
      return int.tryParse(value);
    }
    return null;
  }
}
