import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../models/voice_direction.dart';
import 'audio_provider.dart';

final directionProvider = Provider<VoiceDirection>((ref) {
  final latestAudio = ref.watch(audioProvider.select((state) => state.latest));
  return latestAudio?.voiceDirection ?? const VoiceDirection.unknown();
});
