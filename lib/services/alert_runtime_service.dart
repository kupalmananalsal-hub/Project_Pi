import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:audio_session/audio_session.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:just_audio/just_audio.dart';
import 'package:path_provider/path_provider.dart';
import 'package:vibration/vibration.dart';

import '../models/alert_event.dart';
import '../models/app_settings.dart';

class AlertRuntimeService {
  final _notifications = FlutterLocalNotificationsPlugin();
  final _player = AudioPlayer();
  final _softPlayer = AudioPlayer();

  Timer? _vibrationFallbackTimer;
  bool _initialized = false;

  Future<void> initialize() async {
    if (_initialized) {
      return;
    }

    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    const darwin = DarwinInitializationSettings(
      requestAlertPermission: true,
      requestBadgePermission: true,
      requestSoundPermission: true,
      defaultPresentAlert: true,
      defaultPresentSound: true,
    );

    await _notifications.initialize(
      settings: const InitializationSettings(android: android, iOS: darwin),
    );

    final session = await AudioSession.instance;
    await session.configure(
      const AudioSessionConfiguration(
        avAudioSessionCategory: AVAudioSessionCategory.playback,
        avAudioSessionCategoryOptions: AVAudioSessionCategoryOptions.duckOthers,
        avAudioSessionMode: AVAudioSessionMode.defaultMode,
        avAudioSessionRouteSharingPolicy:
            AVAudioSessionRouteSharingPolicy.defaultPolicy,
        avAudioSessionSetActiveOptions: AVAudioSessionSetActiveOptions.none,
        androidAudioAttributes: AndroidAudioAttributes(
          contentType: AndroidAudioContentType.sonification,
          usage: AndroidAudioUsage.alarm,
        ),
        androidAudioFocusGainType:
            AndroidAudioFocusGainType.gainTransientMayDuck,
        androidWillPauseWhenDucked: false,
      ),
    );

    final androidPlugin = _notifications
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >();
    await androidPlugin?.requestNotificationsPermission();
    await androidPlugin?.requestFullScreenIntentPermission();

    _initialized = true;
  }

  Future<void> startEmergency(
    AlertEvent event,
    AlertSound sound, {
    bool vibrate = true,
  }) async {
    await initialize();
    await _softPlayer.stop();
    await _showNotification(event, vibrate: vibrate);
    await _startAudio(sound);
    if (vibrate) {
      await _startVibration();
    } else {
      await Vibration.cancel();
    }
  }

  Future<void> stopEmergency() async {
    _vibrationFallbackTimer?.cancel();
    _vibrationFallbackTimer = null;
    await Vibration.cancel();
    await _player.stop();
    await _notifications.cancel(id: 1001);
  }

  Future<void> playSoftThermalBeep() async {
    await initialize();
    final session = await AudioSession.instance;
    await session.setActive(true);
    final file = await _softBeepFile();
    await _softPlayer.stop();
    await _softPlayer.setFilePath(file.path);
    await _softPlayer.setLoopMode(LoopMode.off);
    await _softPlayer.setVolume(0.32);
    await _softPlayer.play();
  }

  Future<void> dispose() async {
    await stopEmergency();
    await _softPlayer.stop();
    await _player.dispose();
    await _softPlayer.dispose();
  }

  Future<void> _showNotification(
    AlertEvent event, {
    required bool vibrate,
  }) async {
    const android = AndroidNotificationDetails(
      'keyword_alerts',
      'Keyword Alerts',
      channelDescription: 'Emergency keyword detections from the Pi.',
      importance: Importance.max,
      priority: Priority.max,
      channelBypassDnd: true,
      category: AndroidNotificationCategory.alarm,
      fullScreenIntent: true,
      ongoing: true,
      autoCancel: false,
      playSound: true,
      enableVibration: true,
      audioAttributesUsage: AudioAttributesUsage.alarm,
      visibility: NotificationVisibility.public,
    );
    const darwin = DarwinNotificationDetails(
      presentAlert: true,
      presentSound: true,
      presentBanner: true,
      presentList: true,
      interruptionLevel: InterruptionLevel.timeSensitive,
    );

    await _notifications.show(
      id: 1001,
      title: event.emergencyTitle,
      body:
          'Voice from ${event.directionLabel}. '
          '${vibrate ? 'Thermal human detected.' : 'No thermal human; vibration skipped.'} '
          '${_formatTime(event.timestamp)}',
      notificationDetails: const NotificationDetails(
        android: android,
        iOS: darwin,
      ),
    );
  }

  Future<void> _startAudio(AlertSound sound) async {
    final session = await AudioSession.instance;
    await session.setActive(true);
    final file = await _alarmFile(sound);
    await _player.setFilePath(file.path);
    await _player.setLoopMode(LoopMode.one);
    await _player.setVolume(1);
    await _player.play();
  }

  Future<void> _startVibration() async {
    final hasVibrator = await Vibration.hasVibrator();
    if (!hasVibrator) {
      return;
    }
    await Vibration.vibrate(
      pattern: const [0, 700, 150, 700],
      intensities: const [255, 0, 255, 0],
      repeat: 0,
    );
    _vibrationFallbackTimer?.cancel();
    _vibrationFallbackTimer = Timer.periodic(const Duration(seconds: 4), (_) {
      Vibration.vibrate(
        pattern: const [0, 700, 150, 700],
        intensities: const [255, 0, 255, 0],
        repeat: 0,
      );
    });
  }

  Future<File> _alarmFile(AlertSound sound) async {
    final directory = await getTemporaryDirectory();
    final file = File('${directory.path}/${sound.name}_alarm.wav');
    if (!await file.exists()) {
      await file.writeAsBytes(_buildWave(sound), flush: true);
    }
    return file;
  }

  Future<File> _softBeepFile() async {
    final directory = await getTemporaryDirectory();
    final file = File('${directory.path}/thermal_soft_beep.wav');
    if (!await file.exists()) {
      await file.writeAsBytes(_buildSoftBeepWave(), flush: true);
    }
    return file;
  }

  Uint8List _buildWave(AlertSound sound) {
    final sampleRate = 44100;
    final durationSeconds = sound == AlertSound.bell ? 0.75 : 1.0;
    final samples = (sampleRate * durationSeconds).round();
    final dataBytes = samples * 2;
    final bytes = Uint8List(44 + dataBytes);
    final data = ByteData.view(bytes.buffer);

    void writeAscii(int offset, String value) {
      for (var i = 0; i < value.length; i++) {
        bytes[offset + i] = value.codeUnitAt(i);
      }
    }

    writeAscii(0, 'RIFF');
    data.setUint32(4, 36 + dataBytes, Endian.little);
    writeAscii(8, 'WAVEfmt ');
    data.setUint32(16, 16, Endian.little);
    data.setUint16(20, 1, Endian.little);
    data.setUint16(22, 1, Endian.little);
    data.setUint32(24, sampleRate, Endian.little);
    data.setUint32(28, sampleRate * 2, Endian.little);
    data.setUint16(32, 2, Endian.little);
    data.setUint16(34, 16, Endian.little);
    writeAscii(36, 'data');
    data.setUint32(40, dataBytes, Endian.little);

    for (var i = 0; i < samples; i++) {
      final seconds = i / sampleRate;
      final envelope = sound == AlertSound.bell
          ? math.exp(-seconds * 3.5)
          : (seconds % 0.5 < 0.32 ? 1.0 : 0.15);
      final baseFrequency = switch (sound) {
        AlertSound.alarm => 880.0,
        AlertSound.bell => 1320.0,
        AlertSound.siren => 520.0 + (math.sin(seconds * math.pi * 2) * 220),
      };
      final signal = math.sin(2 * math.pi * baseFrequency * seconds);
      final sample = (signal * envelope * 30000).round();
      data.setInt16(44 + (i * 2), sample, Endian.little);
    }

    return bytes;
  }

  Uint8List _buildSoftBeepWave() {
    const sampleRate = 44100;
    const durationSeconds = 0.48;
    final samples = (sampleRate * durationSeconds).round();
    final dataBytes = samples * 2;
    final bytes = Uint8List(44 + dataBytes);
    final data = ByteData.view(bytes.buffer);

    void writeAscii(int offset, String value) {
      for (var i = 0; i < value.length; i++) {
        bytes[offset + i] = value.codeUnitAt(i);
      }
    }

    writeAscii(0, 'RIFF');
    data.setUint32(4, 36 + dataBytes, Endian.little);
    writeAscii(8, 'WAVEfmt ');
    data.setUint32(16, 16, Endian.little);
    data.setUint16(20, 1, Endian.little);
    data.setUint16(22, 1, Endian.little);
    data.setUint32(24, sampleRate, Endian.little);
    data.setUint32(28, sampleRate * 2, Endian.little);
    data.setUint16(32, 2, Endian.little);
    data.setUint16(34, 16, Endian.little);
    writeAscii(36, 'data');
    data.setUint32(40, dataBytes, Endian.little);

    for (var i = 0; i < samples; i++) {
      final seconds = i / sampleRate;
      final firstBeep = seconds >= 0.03 && seconds <= 0.13;
      final secondBeep = seconds >= 0.25 && seconds <= 0.35;
      final envelope = firstBeep || secondBeep ? 1.0 : 0.0;
      final signal = math.sin(2 * math.pi * 1760 * seconds);
      final sample = (signal * envelope * 18000).round();
      data.setInt16(44 + (i * 2), sample, Endian.little);
    }

    return bytes;
  }

  String _formatTime(DateTime timestamp) {
    final hour = timestamp.hour.toString().padLeft(2, '0');
    final minute = timestamp.minute.toString().padLeft(2, '0');
    final second = timestamp.second.toString().padLeft(2, '0');
    return '$hour:$minute:$second';
  }
}
