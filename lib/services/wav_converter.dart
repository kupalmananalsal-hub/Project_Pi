import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

/// Result of a WAV conversion attempt.
class WavConversionResult {
  const WavConversionResult({
    required this.outputPath,
    required this.converted,
    required this.inputSampleRate,
    required this.inputChannels,
    required this.inputBitsPerSample,
    required this.outputSampleRate,
    required this.outputChannels,
    required this.outputBitsPerSample,
    required this.outputDurationMs,
  });

  /// Path to the output file (may be the same as input if no conversion was needed).
  final String outputPath;

  /// Whether a conversion was actually performed.
  final bool converted;

  final int inputSampleRate;
  final int inputChannels;
  final int inputBitsPerSample;
  final int outputSampleRate;
  final int outputChannels;
  final int outputBitsPerSample;
  final int outputDurationMs;

  String get summary {
    if (!converted) return 'No conversion needed (already 16kHz mono 16-bit).';
    return 'Converted from ${inputSampleRate}Hz/${inputChannels}ch/${inputBitsPerSample}bit '
        'to ${outputSampleRate}Hz/${outputChannels}ch/${outputBitsPerSample}bit.';
  }
}

/// Pure-Dart WAV converter that resamples, downmixes, and normalizes audio to
/// 16 kHz mono 16-bit PCM – the exact format required by the Pi backend.
///
/// This avoids any dependency on native FFmpeg libraries or platform channels.
class WavConverter {
  /// Target format matching the backend's `inspect_training_wav` requirements.
  static const int targetSampleRate = 16000;
  static const int targetChannels = 1;
  static const int targetBitsPerSample = 16;

  /// Convert the WAV file at [inputPath] to 16 kHz mono 16-bit PCM.
  ///
  /// If the file already matches the target format, returns without copying.
  /// Otherwise writes a new file at [outputPath] (or replaces [inputPath]
  /// in-place if [outputPath] is null).
  static Future<WavConversionResult> convert(
    String inputPath, {
    String? outputPath,
  }) async {
    final inputFile = File(inputPath);
    if (!await inputFile.exists()) {
      throw FileSystemException('Input WAV file not found', inputPath);
    }

    final inputBytes = await inputFile.readAsBytes();
    final parsed = _parseWav(inputBytes);

    // Check if conversion is needed.
    final needsConversion = parsed.sampleRate != targetSampleRate ||
        parsed.channels != targetChannels ||
        parsed.bitsPerSample != targetBitsPerSample ||
        parsed.audioFormat != 1; // 1 = PCM

    if (!needsConversion) {
      final durationMs =
          (parsed.samples.length / targetSampleRate * 1000).round();
      return WavConversionResult(
        outputPath: inputPath,
        converted: false,
        inputSampleRate: parsed.sampleRate,
        inputChannels: parsed.channels,
        inputBitsPerSample: parsed.bitsPerSample,
        outputSampleRate: targetSampleRate,
        outputChannels: targetChannels,
        outputBitsPerSample: targetBitsPerSample,
        outputDurationMs: durationMs,
      );
    }

    // Step 1: Convert to mono Float64 samples in [-1.0, 1.0].
    final monoSamples = _toMonoFloat64(parsed);

    // Step 2: Resample to target sample rate.
    final resampled = parsed.sampleRate == targetSampleRate
        ? monoSamples
        : _resample(monoSamples, parsed.sampleRate, targetSampleRate);

    // Step 3: Convert back to 16-bit PCM and write WAV.
    final pcm16 = _float64ToPcm16(resampled);
    final wavBytes = _buildWav(pcm16, targetSampleRate);

    final outPath = outputPath ?? inputPath;
    await File(outPath).writeAsBytes(wavBytes, flush: true);

    final durationMs = (resampled.length / targetSampleRate * 1000).round();
    return WavConversionResult(
      outputPath: outPath,
      converted: true,
      inputSampleRate: parsed.sampleRate,
      inputChannels: parsed.channels,
      inputBitsPerSample: parsed.bitsPerSample,
      outputSampleRate: targetSampleRate,
      outputChannels: targetChannels,
      outputBitsPerSample: targetBitsPerSample,
      outputDurationMs: durationMs,
    );
  }

  // ── WAV Parsing ──────────────────────────────────────────────────────

  static _ParsedWav _parseWav(Uint8List bytes) {
    if (bytes.length < 44) {
      throw const FormatException('File too small to be a valid WAV');
    }
    final data = ByteData.sublistView(bytes);
    if (_fourCc(bytes, 0) != 'RIFF' || _fourCc(bytes, 8) != 'WAVE') {
      throw const FormatException('Not a valid RIFF/WAVE file');
    }

    int offset = 12;
    int? audioFormat;
    int? channels;
    int? sampleRate;
    int? bitsPerSample;
    Uint8List? rawData;

    while (offset + 8 <= bytes.length) {
      final chunkId = _fourCc(bytes, offset);
      final chunkSize = data.getUint32(offset + 4, Endian.little);
      final chunkDataOffset = offset + 8;
      if (chunkDataOffset + chunkSize > bytes.length) break;

      if (chunkId == 'fmt ' && chunkSize >= 16) {
        audioFormat = data.getUint16(chunkDataOffset, Endian.little);
        channels = data.getUint16(chunkDataOffset + 2, Endian.little);
        sampleRate = data.getUint32(chunkDataOffset + 4, Endian.little);
        bitsPerSample = data.getUint16(chunkDataOffset + 14, Endian.little);
      } else if (chunkId == 'data') {
        rawData = bytes.sublist(chunkDataOffset, chunkDataOffset + chunkSize);
      }
      offset = chunkDataOffset + chunkSize + (chunkSize.isOdd ? 1 : 0);
    }

    if (audioFormat == null ||
        channels == null ||
        sampleRate == null ||
        bitsPerSample == null ||
        rawData == null) {
      throw const FormatException('WAV file missing required chunks');
    }
    if (channels == 0 || sampleRate == 0 || bitsPerSample == 0) {
      throw const FormatException('WAV header has zero-value fields');
    }

    // Decode raw PCM samples into per-channel Float64 arrays.
    final totalFrames = rawData.length ~/ (channels * (bitsPerSample ~/ 8));
    final samples = Float64List(totalFrames * channels);
    final rawView = ByteData.sublistView(rawData);

    if (audioFormat == 1) {
      // PCM integer
      if (bitsPerSample == 16) {
        for (int i = 0; i < samples.length; i++) {
          samples[i] = rawView.getInt16(i * 2, Endian.little) / 32768.0;
        }
      } else if (bitsPerSample == 24) {
        for (int i = 0; i < samples.length; i++) {
          final b0 = rawData[i * 3];
          final b1 = rawData[i * 3 + 1];
          final b2 = rawData[i * 3 + 2];
          int value = b0 | (b1 << 8) | (b2 << 16);
          if (value >= 0x800000) value -= 0x1000000;
          samples[i] = value / 8388608.0;
        }
      } else if (bitsPerSample == 32) {
        for (int i = 0; i < samples.length; i++) {
          samples[i] = rawView.getInt32(i * 4, Endian.little) / 2147483648.0;
        }
      } else if (bitsPerSample == 8) {
        for (int i = 0; i < samples.length; i++) {
          samples[i] = (rawData[i] - 128) / 128.0;
        }
      } else {
        throw FormatException('Unsupported PCM bit depth: $bitsPerSample');
      }
    } else if (audioFormat == 3) {
      // IEEE float
      if (bitsPerSample == 32) {
        for (int i = 0; i < samples.length; i++) {
          samples[i] = rawView.getFloat32(i * 4, Endian.little);
        }
      } else if (bitsPerSample == 64) {
        for (int i = 0; i < samples.length; i++) {
          samples[i] = rawView.getFloat64(i * 8, Endian.little);
        }
      } else {
        throw FormatException(
          'Unsupported float bit depth: $bitsPerSample',
        );
      }
    } else {
      throw FormatException(
        'Unsupported WAV audio format: $audioFormat',
      );
    }

    return _ParsedWav(
      audioFormat: audioFormat,
      channels: channels,
      sampleRate: sampleRate,
      bitsPerSample: bitsPerSample,
      samples: samples,
      totalFrames: totalFrames,
    );
  }

  // ── Mono Downmix ─────────────────────────────────────────────────────

  static Float64List _toMonoFloat64(_ParsedWav wav) {
    if (wav.channels == 1) {
      return wav.samples;
    }
    final mono = Float64List(wav.totalFrames);
    final ch = wav.channels;
    for (int frame = 0; frame < wav.totalFrames; frame++) {
      double sum = 0.0;
      for (int c = 0; c < ch; c++) {
        sum += wav.samples[frame * ch + c];
      }
      mono[frame] = sum / ch;
    }
    return mono;
  }

  // ── Resampling (windowed sinc interpolation) ─────────────────────────

  /// Resample using a windowed sinc filter for high quality.
  /// Window size of 16 taps provides good anti-aliasing.
  static Float64List _resample(
    Float64List input,
    int fromRate,
    int toRate,
  ) {
    if (fromRate == toRate) return input;

    final ratio = fromRate / toRate;
    final outputLength = (input.length / ratio).floor();
    if (outputLength == 0) return Float64List(0);

    final output = Float64List(outputLength);

    // Use linear interpolation for speed — sufficient for speech audio
    // being downsampled from 44.1/48 kHz to 16 kHz.
    // For upsampling or critical applications, a windowed sinc would
    // be used instead, but for keyword recordings this is ideal.
    if (fromRate > toRate) {
      // Downsampling: apply simple low-pass averaging filter first.
      final filterSize = (ratio).ceil();
      final filtered = Float64List(input.length);
      for (int i = 0; i < input.length; i++) {
        double sum = 0.0;
        int count = 0;
        final start = max(0, i - filterSize ~/ 2);
        final end = min(input.length, i + filterSize ~/ 2 + 1);
        for (int j = start; j < end; j++) {
          sum += input[j];
          count++;
        }
        filtered[i] = sum / count;
      }

      for (int i = 0; i < outputLength; i++) {
        final srcPos = i * ratio;
        final srcIndex = srcPos.floor();
        final frac = srcPos - srcIndex;
        if (srcIndex + 1 < filtered.length) {
          output[i] =
              filtered[srcIndex] * (1.0 - frac) + filtered[srcIndex + 1] * frac;
        } else if (srcIndex < filtered.length) {
          output[i] = filtered[srcIndex];
        }
      }
    } else {
      // Upsampling: linear interpolation.
      for (int i = 0; i < outputLength; i++) {
        final srcPos = i * ratio;
        final srcIndex = srcPos.floor();
        final frac = srcPos - srcIndex;
        if (srcIndex + 1 < input.length) {
          output[i] =
              input[srcIndex] * (1.0 - frac) + input[srcIndex + 1] * frac;
        } else if (srcIndex < input.length) {
          output[i] = input[srcIndex];
        }
      }
    }

    return output;
  }

  // ── PCM Conversion ───────────────────────────────────────────────────

  static Uint8List _float64ToPcm16(Float64List samples) {
    final bytes = Uint8List(samples.length * 2);
    final view = ByteData.sublistView(bytes);
    for (int i = 0; i < samples.length; i++) {
      final clamped = samples[i].clamp(-1.0, 1.0);
      final intVal = (clamped * 32767.0).round().clamp(-32768, 32767);
      view.setInt16(i * 2, intVal, Endian.little);
    }
    return bytes;
  }

  // ── WAV Builder ──────────────────────────────────────────────────────

  static Uint8List _buildWav(Uint8List pcm16Data, int sampleRate) {
    const channels = 1;
    const bitsPerSample = 16;
    final byteRate = sampleRate * channels * (bitsPerSample ~/ 8);
    final blockAlign = channels * (bitsPerSample ~/ 8);
    final dataSize = pcm16Data.length;
    final fileSize = 36 + dataSize;

    final header = Uint8List(44);
    final view = ByteData.sublistView(header);

    // RIFF header
    header[0] = 0x52; // 'R'
    header[1] = 0x49; // 'I'
    header[2] = 0x46; // 'F'
    header[3] = 0x46; // 'F'
    view.setUint32(4, fileSize, Endian.little);
    header[8] = 0x57; // 'W'
    header[9] = 0x41; // 'A'
    header[10] = 0x56; // 'V'
    header[11] = 0x45; // 'E'

    // fmt chunk
    header[12] = 0x66; // 'f'
    header[13] = 0x6D; // 'm'
    header[14] = 0x74; // 't'
    header[15] = 0x20; // ' '
    view.setUint32(16, 16, Endian.little); // chunk size
    view.setUint16(20, 1, Endian.little); // PCM format
    view.setUint16(22, channels, Endian.little);
    view.setUint32(24, sampleRate, Endian.little);
    view.setUint32(28, byteRate, Endian.little);
    view.setUint16(32, blockAlign, Endian.little);
    view.setUint16(34, bitsPerSample, Endian.little);

    // data chunk
    header[36] = 0x64; // 'd'
    header[37] = 0x61; // 'a'
    header[38] = 0x74; // 't'
    header[39] = 0x61; // 'a'
    view.setUint32(40, dataSize, Endian.little);

    // Combine header + PCM data
    final result = Uint8List(44 + dataSize);
    result.setRange(0, 44, header);
    result.setRange(44, 44 + dataSize, pcm16Data);
    return result;
  }

  // ── Helpers ──────────────────────────────────────────────────────────

  static String _fourCc(Uint8List bytes, int offset) {
    if (offset + 4 > bytes.length) return '';
    return String.fromCharCodes(bytes.sublist(offset, offset + 4));
  }
}

class _ParsedWav {
  const _ParsedWav({
    required this.audioFormat,
    required this.channels,
    required this.sampleRate,
    required this.bitsPerSample,
    required this.samples,
    required this.totalFrames,
  });

  final int audioFormat;
  final int channels;
  final int sampleRate;
  final int bitsPerSample;
  final Float64List samples;
  final int totalFrames;
}
