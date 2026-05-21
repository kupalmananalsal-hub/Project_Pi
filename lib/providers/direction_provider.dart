import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/voice_direction.dart';
import 'alerts_provider.dart';
import 'audio_provider.dart';

final directionProvider = Provider<VoiceDirection>((ref) {
  final guidance = ref.watch(
    alertsProvider.select((state) => state.pendingGuidance),
  );
  if (guidance != null) {
    return guidance.voiceDirection;
  }
  final latestAudio = ref.watch(audioProvider.select((state) => state.latest));
  return latestAudio?.voiceDirection ?? const VoiceDirection.unknown();
});
