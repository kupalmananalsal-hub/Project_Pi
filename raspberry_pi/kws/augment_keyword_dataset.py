#!/usr/bin/env python3
"""Create augmented keyword-dataset WAV files when audio packages are available."""

from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from keyword_dataset_common import (  # noqa: E402
    DEFAULT_DATASET_DIR,
    append_metadata,
    ensure_dataset_layout,
    wav_files,
)


def _require_audio_packages():
    try:
        import librosa
        import numpy as np
        import soundfile as sf
    except ImportError as exc:
        raise SystemExit(
            "Augmentation requires optional packages: librosa numpy soundfile. "
            "Install in Colab or on the Pi with: pip install librosa soundfile numpy"
        ) from exc
    return librosa, np, sf


def _load_noise_files(dataset_dir: Path) -> list[Path]:
    return wav_files(dataset_dir / "negative" / "noise")


def augment_file(source_path: Path, output_path: Path, sample_rate: int, rng) -> str:
    librosa, np, sf = _require_audio_packages()
    audio, sr = librosa.load(source_path, sr=sample_rate, mono=True)
    operation = rng.choice(
        [
            "pitch_child",
            "pitch_teen",
            "pitch_elder",
            "time_stretch",
            "volume",
            "channel_dropout",
        ]
    )
    if operation == "pitch_child":
        audio = librosa.effects.pitch_shift(audio, sr=sr, n_steps=6)
    elif operation == "pitch_teen":
        audio = librosa.effects.pitch_shift(audio, sr=sr, n_steps=2)
    elif operation == "pitch_elder":
        audio = librosa.effects.pitch_shift(audio, sr=sr, n_steps=-3)
    elif operation == "time_stretch":
        audio = librosa.effects.time_stretch(audio, rate=rng.uniform(0.92, 1.08))
    elif operation == "volume":
        audio = audio * rng.uniform(0.55, 1.25)
    elif operation == "channel_dropout":
        start = rng.randrange(0, max(1, len(audio)))
        stop = min(len(audio), start + int(sr * rng.uniform(0.05, 0.25)))
        audio[start:stop] = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, np.clip(audio, -1.0, 1.0), sr, subtype="PCM_16")
    return operation


def augment_dataset(
    dataset_dir: Path,
    output_dir: Path,
    copies_per_file: int,
    seed: int,
) -> dict[str, int]:
    ensure_dataset_layout(dataset_dir)
    rng = random.Random(seed)
    positives = wav_files(dataset_dir / "positive")
    metadata_path = dataset_dir / "metadata.csv"
    created = 0
    operations: dict[str, int] = {}

    for source_path in positives:
        rel = source_path.relative_to(dataset_dir / "positive")
        keyword_slug = rel.parts[0]
        for copy_index in range(copies_per_file):
            output_path = (
                output_dir
                / "positive"
                / keyword_slug
                / f"{source_path.stem}_aug_{copy_index + 1:02d}.wav"
            )
            operation = augment_file(source_path, output_path, 16000, rng)
            operations[operation] = operations.get(operation, 0) + 1
            append_metadata(
                metadata_path,
                {
                    "path": output_path.relative_to(dataset_dir).as_posix()
                    if output_path.is_relative_to(dataset_dir)
                    else output_path.as_posix(),
                    "keyword": keyword_slug,
                    "label": keyword_slug,
                    "speaker_id": "synthetic",
                    "age_group": "augmented",
                    "gender": "unknown",
                    "distance_m": "unknown",
                    "noise_condition": operation,
                    "source": "augmentation",
                    "sample_rate": "16000",
                    "duration_s": "",
                    "notes": f"source={source_path.relative_to(dataset_dir)}",
                },
            )
            created += 1

    return {"source_files": len(positives), "created_files": created, **operations}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Augment recorded keyword WAV files with pitch/time/volume effects."
    )
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_DATASET_DIR / "augmented",
        help="output folder; ignored by Git",
    )
    parser.add_argument("--copies-per-file", type=int, default=2)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument(
        "--list-operations",
        action="store_true",
        help="print supported augmentations and exit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_operations:
        print(
            "pitch_child,pitch_teen,pitch_elder,time_stretch,volume,channel_dropout"
        )
        return 0
    summary = augment_dataset(
        args.dataset_dir.resolve(),
        args.output_dir.resolve(),
        args.copies_per_file,
        args.seed,
    )
    print(csv.DictWriter(sys.stdout, fieldnames=summary.keys()).fieldnames)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
