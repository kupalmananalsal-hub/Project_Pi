#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import pyaudio

from audio_preprocessor import AudioPreprocessor


DEFAULT_MODEL_DIR = Path("/home/thesis/Project_Pi/raspberry_pi/kws/openwakeword_models")
DEFAULT_PHRASES = ("tulong", "saklolo", "ang sakit", "agai", "aray", "sunog")


def phrase_to_model_path(model_dir: Path, phrase: str) -> Path:
    return model_dir / f"{phrase.replace(' ', '_')}.onnx"


def find_input_device(pa: pyaudio.PyAudio, hint: str) -> int:
    hint = hint.lower()
    fallback = None
    for index in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(index)
        if int(info.get("maxInputChannels", 0)) <= 0:
            continue
        name = str(info.get("name", ""))
        print(f"Input device {index}: {name}", flush=True)
        lowered = name.lower()
        if hint in lowered or "seeed" in lowered or "respeaker" in lowered:
            return index
        if fallback is None:
            fallback = index
    if fallback is None:
        raise RuntimeError("No input device found")
    return fallback


def mono_from_chunk(data: bytes, channels: int) -> np.ndarray:
    samples = np.frombuffer(data, dtype=np.int16)
    if channels <= 1:
        return samples
    usable = samples[: samples.size - (samples.size % channels)]
    if usable.size == 0:
        return np.array([], dtype=np.int16)
    framed = usable.reshape(-1, channels)
    return np.mean(framed[:, :2].astype(np.float32), axis=1).astype(np.int16)


def score_phrase(
    stream: pyaudio.Stream,
    phrase: str,
    model_path: Path,
    args: argparse.Namespace,
) -> tuple[float, float, list[dict[str, object]]]:
    preprocessor = AudioPreprocessor(
        wake_word_models=[str(model_path)],
        vad_threshold=args.vad_threshold,
        wake_word_threshold=args.threshold,
        wake_word_thresholds={phrase: args.threshold},
        enable_speex_noise_suppression=True,
    )
    if not preprocessor.available:
        raise RuntimeError(
            f"openWakeWord failed to load {model_path}: {preprocessor.error}"
        )

    max_score = 0.0
    max_vad = 0.0
    best_scores: list[dict[str, object]] = []
    deadline = time.monotonic() + args.duration
    while time.monotonic() < deadline:
        data = stream.read(args.chunk_frames, exception_on_overflow=False)
        mono = mono_from_chunk(data, args.channels)
        result = preprocessor.process(mono)
        max_vad = max(max_vad, float(result.get("vad_score", 0.0)))
        for score in result.get("scores", []):
            if not isinstance(score, dict):
                continue
            value = float(score.get("score", 0.0))
            if value > max_score:
                max_score = value
                best_scores = [score]

    return max_score, max_vad, best_scores


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record live audio and print openWakeWord scores for Tagalog models."
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path(os.getenv("OPENWAKEWORD_MODEL_DIR", str(DEFAULT_MODEL_DIR))),
    )
    parser.add_argument("--phrases", nargs="*", default=list(DEFAULT_PHRASES))
    parser.add_argument("--duration", type=float, default=3.0)
    parser.add_argument("--threshold", type=float, default=0.30)
    parser.add_argument("--vad-threshold", type=float, default=0.40)
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--chunk-frames", type=int, default=1280)
    parser.add_argument("--channels", type=int, default=2)
    parser.add_argument("--mic-hint", default=os.getenv("MIC_NAME_HINT", "seeed"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_dir = args.model_dir.expanduser()
    phrases = [phrase.strip().lower() for phrase in args.phrases if phrase.strip()]
    model_paths = {
        phrase: phrase_to_model_path(model_dir, phrase)
        for phrase in phrases
    }
    missing = [path for path in model_paths.values() if not path.is_file()]
    if missing:
        print("Missing Tagalog model file(s):", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        return 2

    pa = pyaudio.PyAudio()
    stream = None
    try:
        device_index = find_input_device(pa, args.mic_hint)
        print(f"Using input device index {device_index}", flush=True)
        stream = pa.open(
            rate=args.sample_rate,
            channels=args.channels,
            format=pyaudio.paInt16,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=args.chunk_frames,
        )

        print(
            f"Validation threshold={args.threshold:.2f}, "
            f"VAD threshold={args.vad_threshold:.2f}",
            flush=True,
        )
        for phrase, model_path in model_paths.items():
            input(f"\nPress Enter, then say '{phrase}' clearly for {args.duration:.1f}s...")
            max_score, max_vad, best_scores = score_phrase(
                stream,
                phrase,
                model_path,
                args,
            )
            detected = max_score >= args.threshold
            print(
                f"{phrase}: score={max_score:.3f} "
                f"vad={max_vad:.3f} "
                f"threshold={args.threshold:.3f} "
                f"detected={detected}",
                flush=True,
            )
            if best_scores:
                print(f"  best raw score: {best_scores[0]}", flush=True)
    finally:
        if stream is not None:
            stream.stop_stream()
            stream.close()
        pa.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
