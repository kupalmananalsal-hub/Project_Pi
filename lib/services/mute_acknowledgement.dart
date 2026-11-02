import 'dart:async';

/// Limit a displayed acknowledgement by the remaining server lifetime minus RTT.
class MuteAcknowledgement {
  Timer? _timer;
  void apply(
    Map<String, dynamic> state,
    Duration elapsed,
    void Function() changed,
  ) {
    _timer?.cancel();
    final ttl = state['mute_ack_valid_for_seconds'];
    final remaining = ttl is num && ttl.isFinite && ttl > 0 && ttl <= 2
        ? ttl.toDouble() - elapsed.inMicroseconds / 1000000
        : 0.0;
    if (state['remote_microphone_muted'] != true || remaining <= 0) {
      state['remote_microphone_muted'] = false;
      return;
    }
    _timer = Timer(Duration(microseconds: (remaining * 1000000).floor()), () {
      state['remote_microphone_muted'] = false;
      state['mute_state'] = 'unknown';
      changed();
    });
  }

  void clear() => _timer?.cancel();
}
