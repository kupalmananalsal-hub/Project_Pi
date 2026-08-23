#!/usr/bin/env python3
"""Prepare and launch openWakeWord training jobs for Project Pi keywords."""

from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from keyword_dataset_common import DEFAULT_DATASET_DIR, slugify_keyword, wav_files  # noqa: E402


def _split(items: list[str], require_validation: bool = False) -> dict[str, list[str]]:
    if require_validation and len(items) >= 3:
        train_count = max(1, int(len(items) * 0.70))
        train_count = min(train_count, len(items) - 2)
        val_count = max(1, int(len(items) * 0.15))
        val_count = min(val_count, len(items) - train_count - 1)
        train_end = train_count
        val_end = train_count + val_count
    else:
        train_end = int(len(items) * 0.70)
        val_end = train_end + int(len(items) * 0.15)
    return {
        "train": items[:train_end],
        "val": items[train_end:val_end],
        "test": items[val_end:],
    }


def read_metadata(dataset_dir: Path) -> list[dict[str, str]]:
    metadata_path = dataset_dir / "metadata.csv"
    if not metadata_path.exists():
        return []
    with metadata_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _source_path_from_notes(notes: str) -> str | None:
    for token in notes.split():
        if token.startswith("source="):
            return token.removeprefix("source=").strip()
    return None


def _is_synthetic(row: dict[str, str]) -> bool:
    source = row.get("source", "").strip().lower()
    speaker_id = row.get("speaker_id", "").strip().lower()
    return source in {"tts", "synthetic"} or speaker_id.startswith("tts_")


def _real_speaker_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if row.get("source", "").strip().lower() == "real"
        and row.get("speaker_id", "").strip()
    ]


def assign_speakers(rows: list[dict[str, str]], seed: int) -> dict[str, list[str]]:
    speakers = sorted({row["speaker_id"].strip() for row in _real_speaker_rows(rows)})
    rng = random.Random(seed)
    rng.shuffle(speakers)
    return _split(speakers, require_validation=True)


def _positive_files_from_metadata(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if row.get("path", "").endswith(".wav")
        and (
            row["path"].startswith("positive/")
            or row["path"].startswith("augmented/positive/")
        )
    ]


def _positive_files_without_metadata(dataset_dir: Path) -> list[dict[str, str]]:
    rows = []
    for path in [
        *wav_files(dataset_dir / "positive"),
        *wav_files(dataset_dir / "augmented" / "positive"),
    ]:
        relative = path.relative_to(dataset_dir).as_posix()
        parts = relative.split("/")
        keyword = parts[1] if parts[0] == "positive" else parts[2]
        rows.append(
            {
                "path": relative,
                "keyword": keyword,
                "label": keyword,
                "speaker_id": "unknown",
                "source": "real",
                "notes": "",
            }
        )
    return rows


def _row_split(
    row: dict[str, str],
    speakers: dict[str, list[str]],
    source_split_by_path: dict[str, str],
) -> str:
    source = row.get("source", "").strip().lower()
    if source == "augmentation":
        source_path = _source_path_from_notes(row.get("notes", ""))
        if source_path and source_path in source_split_by_path:
            return source_split_by_path[source_path]
    if _is_synthetic(row):
        return "train"
    speaker_id = row.get("speaker_id", "").strip()
    for split_name, split_speakers in speakers.items():
        if speaker_id in split_speakers:
            return split_name
    return "train"


def build_split_manifest(dataset_dir: Path, seed: int = 1337) -> dict[str, object]:
    dataset_dir = dataset_dir.resolve()
    rng = random.Random(seed)
    negatives = [
        path.relative_to(dataset_dir).as_posix()
        for path in wav_files(dataset_dir / "negative")
    ]
    rng.shuffle(negatives)
    negative_split = _split(negatives)

    metadata_rows = read_metadata(dataset_dir)
    positive_rows = (
        _positive_files_from_metadata(metadata_rows)
        if metadata_rows
        else _positive_files_without_metadata(dataset_dir)
    )
    speakers = assign_speakers(metadata_rows or positive_rows, seed)
    keywords: dict[str, dict[str, dict[str, list[str]]]] = {}
    source_split_by_path: dict[str, str] = {}

    for row in positive_rows:
        if row.get("source", "").strip().lower() == "augmentation":
            continue
        split_name = _row_split(row, speakers, source_split_by_path)
        relative_path = row["path"]
        keyword = slugify_keyword(row.get("keyword") or row.get("label") or "")
        if not keyword:
            parts = relative_path.split("/")
            keyword = parts[1] if parts[0] == "positive" else parts[2]
        keyword_entry = keywords.setdefault(
            keyword,
            {
                split: {
                    "positive": [],
                    "negative": negative_split[split],
                }
                for split in ("train", "val", "test")
            },
        )
        keyword_entry[split_name]["positive"].append(relative_path)
        source_split_by_path[relative_path] = split_name

    for row in positive_rows:
        if row.get("source", "").strip().lower() != "augmentation":
            continue
        split_name = _row_split(row, speakers, source_split_by_path)
        relative_path = row["path"]
        keyword = slugify_keyword(row.get("keyword") or row.get("label") or "")
        keyword_entry = keywords.setdefault(
            keyword,
            {
                split: {
                    "positive": [],
                    "negative": negative_split[split],
                }
                for split in ("train", "val", "test")
            },
        )
        keyword_entry[split_name]["positive"].append(relative_path)

    return {
        "split_seed": seed,
        "speakers": speakers,
        "keywords": keywords,
    }


def find_manifest_split(manifest: dict[str, object], relative_path: str) -> str | None:
    keywords = manifest.get("keywords", {})
    for keyword_data in keywords.values():
        for split_name in ("train", "val", "test"):
            if relative_path in keyword_data[split_name]["positive"]:
                return split_name
    return None


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
    print(f"Keywords with samples: {len(manifest['keywords'])}")
    if args.manifest_only:
        return 0
    return train_with_openwakeword(
        args.manifest_out,
        args.output_dir,
        args.openwakeword_command,
    )


if __name__ == "__main__":
    raise SystemExit(main())
