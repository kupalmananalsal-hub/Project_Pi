#!/usr/bin/env python3
"""Prepare and launch openWakeWord training jobs for Project Pi keywords."""

from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from keyword_dataset_common import DEFAULT_DATASET_DIR, wav_files  # noqa: E402


def _split(items: list[str]) -> dict[str, list[str]]:
    train_end = int(len(items) * 0.70)
    val_end = train_end + int(len(items) * 0.15)
    return {
        "train": items[:train_end],
        "val": items[train_end:val_end],
        "test": items[val_end:],
    }


def build_split_manifest(dataset_dir: Path, seed: int = 1337) -> dict[str, object]:
    dataset_dir = dataset_dir.resolve()
    rng = random.Random(seed)
    negatives = [
        path.relative_to(dataset_dir).as_posix()
        for path in wav_files(dataset_dir / "negative")
    ]
    rng.shuffle(negatives)
    negative_split = _split(negatives)
    manifest: dict[str, object] = {}

    for keyword_dir in sorted((dataset_dir / "positive").glob("*")):
        if not keyword_dir.is_dir():
            continue
        positives = [
            path.relative_to(dataset_dir).as_posix() for path in wav_files(keyword_dir)
        ]
        if not positives:
            continue
        rng.shuffle(positives)
        positive_split = _split(positives)
        manifest[keyword_dir.name] = {
            split: {
                "positive": positive_split[split],
                "negative": negative_split[split],
            }
            for split in ("train", "val", "test")
        }
    return manifest


def write_manifest(manifest: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def train_with_openwakeword(
    manifest_path: Path,
    output_dir: Path,
    openwakeword_command: str | None,
) -> int:
    if not openwakeword_command:
        print(
            "No openWakeWord training command supplied. Manifest was created; "
            "run this script in Colab with --openwakeword-command when the "
            "training environment is ready."
        )
        return 0
    if shutil.which(openwakeword_command.split()[0]) is None:
        raise SystemExit(f"Training command not found: {openwakeword_command}")
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        *openwakeword_command.split(),
        "--manifest",
        str(manifest_path),
        "--output-dir",
        str(output_dir),
    ]
    return subprocess.call(command)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create train/val/test manifests and optionally run training."
    )
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument(
        "--manifest-out",
        type=Path,
        default=DEFAULT_DATASET_DIR / "splits" / "openwakeword_split.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_DATASET_DIR / "models",
        help="training outputs; ignored by Git",
    )
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument(
        "--openwakeword-command",
        help="Colab/openWakeWord training entrypoint to execute after manifest creation",
    )
    parser.add_argument(
        "--manifest-only",
        action="store_true",
        help="create split manifest and do not run training",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = build_split_manifest(args.dataset_dir, seed=args.seed)
    write_manifest(manifest, args.manifest_out)
    print(f"Wrote split manifest: {args.manifest_out}")
    print(f"Keywords with samples: {len(manifest)}")
    if args.manifest_only:
        return 0
    return train_with_openwakeword(
        args.manifest_out,
        args.output_dir,
        args.openwakeword_command,
    )


if __name__ == "__main__":
    raise SystemExit(main())
