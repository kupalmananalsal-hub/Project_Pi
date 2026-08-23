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


import gc
import os
import time
from typing import Callable


def _set_low_priority() -> None:
    """Lower CPU priority and limit multithreading so the web backend stays responsive."""
    try:
        if hasattr(os, "nice"):
            os.nice(10)
    except Exception:
        pass
    for env_var in (
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "OMP_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ.setdefault(env_var, "1")


def _check_available_memory(min_mb: float = 500.0) -> None:
    """Ensure at least min_mb of memory is available before memory-heavy operations."""
    try:
        import psutil
        available_mb = psutil.virtual_memory().available / (1024 * 1024)
        if available_mb < min_mb:
            raise RuntimeError(
                f"Insufficient memory for audio augmentation (requires at least {min_mb:.0f} MB free RAM, "
                f"found {available_mb:.1f} MB). Close unused processes before running."
            )
    except ImportError:
        pass


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
    try:
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
    finally:
        del audio
        gc.collect()
    return operation


def augment_dataset(
    dataset_dir: Path,
    output_dir: Path,
    copies_per_file: int = 2,
    seed: int = 1337,
    progress_callback: Callable[[int, int, str], None] | None = None,
    max_source_files: int = 1000,
    min_memory_mb: float = 500.0,
) -> dict[str, int]:
    ensure_dataset_layout(dataset_dir)
    _set_low_priority()
    _check_available_memory(min_memory_mb)

    rng = random.Random(seed)
    all_positives = wav_files(dataset_dir / "positive")
    # Filter to original non-augmented source files to avoid re-augmenting generated files
    positives = [
        p for p in all_positives
        if "_aug_" not in p.name and not p.is_relative_to(output_dir)
    ]
    if len(positives) > max_source_files:
        raise ValueError(
            f"Too many source files for augmentation ({len(positives)} > {max_source_files}). "
            f"Please clean up dataset or reduce file count."
        )

    metadata_path = dataset_dir / "metadata.csv"
    created = 0
    operations: dict[str, int] = {}
    total_copies = len(positives) * copies_per_file

    if total_copies == 0:
        return {"source_files": 0, "created_files": 0}

    for file_idx, source_path in enumerate(positives):
        # Check memory periodically
        if file_idx > 0 and file_idx % 10 == 0:
            _check_available_memory(min_memory_mb)

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
            if progress_callback:
                progress_callback(
                    created,
                    total_copies,
                    f"Augmenting {keyword_slug} ({created}/{total_copies})",
                )
            # Yield CPU briefly between files to prevent starving the event loop
            time.sleep(0.01)

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
