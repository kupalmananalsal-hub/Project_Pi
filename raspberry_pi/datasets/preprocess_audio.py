#!/usr/bin/env python3
from __future__ import annotations

import audioop
import json
import math
import random
import wave
from pathlib import Path

import numpy as np


SAMPLE_RATE = 16000
OUTPUT_ROOT = Path.home() / "thesis_dataset" / "processed_audio"
SNR_LEVELS = (-5, 0, 5, 10, 15)


def resample_to_16khz(audio_path: str | Path, output_path: str | Path | None = None) -> Path:
    audio_path = Path(audio_path).expanduser()
    output_path = Path(output_path or OUTPUT_ROOT / f"{audio_path.stem}_16k.wav").expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(audio_path), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        frame_rate = source.getframerate()
        frames = source.readframes(source.getnframes())

    if channels > 1:
        frames = audioop.tomono(frames, sample_width, 0.5, 0.5)
        channels = 1

    if sample_width != 2:
        frames = audioop.lin2lin(frames, sample_width, 2)
        sample_width = 2

    if frame_rate != SAMPLE_RATE:
        frames, _ = audioop.ratecv(frames, sample_width, channels, frame_rate, SAMPLE_RATE, None)
        frame_rate = SAMPLE_RATE

    with wave.open(str(output_path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(frame_rate)
        output.writeframes(frames)

    return output_path


def generate_noisy_speech_pairs(
    clean_root: str | Path | None = None,
    noise_root: str | Path | None = None,
    output_root: str | Path | None = None,
) -> Path:
    clean_root = Path(clean_root or Path.home() / "thesis_dataset" / "speech_commands").expanduser()
    noise_root = Path(noise_root or Path.home() / "thesis_dataset" / "MS-SNSD").expanduser()
    output_root = Path(output_root or OUTPUT_ROOT / "noisy_pairs").expanduser()
    output_root.mkdir(parents=True, exist_ok=True)

    clean_files = list(clean_root.rglob("*.wav"))
    noise_files = list(noise_root.rglob("*.wav"))
    manifest_path = output_root / "manifest.jsonl"

    if not clean_files or not noise_files:
        manifest_path.write_text("", encoding="utf-8")
        return manifest_path

    random.seed(7)
    with manifest_path.open("w", encoding="utf-8") as manifest:
        for clean_path in clean_files[: min(100, len(clean_files))]:
            clean_wave = _read_wave_as_float(resample_to_16khz(clean_path))
            for snr_db in SNR_LEVELS:
                noise_path = random.choice(noise_files)
                noise_wave = _read_wave_as_float(resample_to_16khz(noise_path))
                mixed = _mix_at_snr(clean_wave, noise_wave, snr_db)

                output_name = f"{clean_path.stem}_{Path(noise_path).stem}_{snr_db}db.wav"
                noisy_output = output_root / "noisy" / output_name
                clean_output = output_root / "clean" / output_name
                noisy_output.parent.mkdir(parents=True, exist_ok=True)
                clean_output.parent.mkdir(parents=True, exist_ok=True)

                _write_wave(noisy_output, mixed)
                _write_wave(clean_output, clean_wave)

                manifest.write(
                    json.dumps(
                        {
                            "clean_audio": str(clean_output),
                            "noisy_audio": str(noisy_output),
                            "snr_db": snr_db,
                            "noise_source": str(noise_path),
                        }
                    )
                    + "\n"
                )

    return manifest_path


def create_keyword_dataset(
    keyword_root: str | Path | None = None,
    output_path: str | Path | None = None,
) -> Path:
    keyword_root = Path(keyword_root or Path.home() / "thesis_dataset" / "keywords").expanduser()
    output_path = Path(output_path or OUTPUT_ROOT / "keyword_dataset.jsonl").expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    keyword_aliases = {
        "tulong": "keyword",
        "help": "keyword",
        "please_help": "keyword",
        "non_keyword": "non_keyword",
        "noise": "noise",
    }

    rows_written = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for wav_path in keyword_root.rglob("*.wav"):
            parent_label = wav_path.parent.name.lower()
            label = keyword_aliases.get(parent_label, "unknown")
            normalized = resample_to_16khz(wav_path, OUTPUT_ROOT / "resampled" / wav_path.name)
            for snr_db in SNR_LEVELS:
                handle.write(
                    json.dumps(
                        {
                            "audio_path": str(normalized),
                            "label": label,
                            "keyword": parent_label,
                            "snr_db": snr_db,
                            "sample_rate": SAMPLE_RATE,
                        }
                    )
                    + "\n"
                )
                rows_written += 1

    print(f"Wrote {rows_written} keyword dataset rows to {output_path}")
    return output_path


def _read_wave_as_float(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
        data = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
    return data / 32768.0


def _write_wave(path: Path, audio: np.ndarray) -> None:
    clipped = np.clip(audio, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())


def _mix_at_snr(clean: np.ndarray, noise: np.ndarray, snr_db: int) -> np.ndarray:
    if noise.size < clean.size:
        repeats = math.ceil(clean.size / noise.size)
        noise = np.tile(noise, repeats)
    noise = noise[: clean.size]

    clean_power = np.mean(np.square(clean)) + 1e-9
    noise_power = np.mean(np.square(noise)) + 1e-9
    desired_noise_power = clean_power / (10 ** (snr_db / 10.0))
    scale = math.sqrt(desired_noise_power / noise_power)
    return clean + (noise * scale)


if __name__ == "__main__":
    generate_noisy_speech_pairs()
    create_keyword_dataset()
