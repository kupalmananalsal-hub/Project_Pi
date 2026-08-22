#!/usr/bin/env python3
"""Shared constants and helpers for the Project Pi keyword dataset tools."""

from __future__ import annotations

import csv
import re
from pathlib import Path


KEYWORDS = [
    "help",
    "help me",
    "save me",
    "please help",
    "emergency",
    "rescue",
    "over here",
    "ouch",
    "tulong",
    "saklolo",
    "tulungan niyo ako",
    "tulungan mo ako",
    "kailangan ko ng tulong",
    "ang sakit",
    "aray",
    "sunog",
    "agai",
]

NEGATIVE_CLASSES = ["random_speech", "noise", "silence", "music"]

METADATA_COLUMNS = [
    "path",
    "keyword",
    "label",
    "speaker_id",
    "age_group",
    "gender",
    "distance_m",
    "noise_condition",
    "source",
    "sample_rate",
    "duration_s",
    "notes",
]

DEFAULT_DATASET_DIR = (
    Path(__file__).resolve().parents[2] / "dataset" / "audio" / "keyword_dataset"
)


def slugify_keyword(keyword: str) -> str:
    """Convert a spoken keyword phrase into a stable folder-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", keyword.strip().lower())
    return slug.strip("_")


def ensure_dataset_layout(dataset_dir: Path) -> None:
    """Create positive/negative folders and metadata header if missing."""
    dataset_dir.mkdir(parents=True, exist_ok=True)
    for keyword in KEYWORDS:
        (dataset_dir / "positive" / slugify_keyword(keyword)).mkdir(
            parents=True, exist_ok=True
        )
    for negative_class in NEGATIVE_CLASSES:
        (dataset_dir / "negative" / negative_class).mkdir(parents=True, exist_ok=True)
    metadata_path = dataset_dir / "metadata.csv"
    if not metadata_path.exists():
        with metadata_path.open("w", newline="", encoding="utf-8") as handle:
            csv.DictWriter(handle, fieldnames=METADATA_COLUMNS).writeheader()


def append_metadata(metadata_path: Path, row: dict[str, object]) -> None:
    """Append one metadata row, creating the CSV header when needed."""
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    exists = metadata_path.exists()
    with metadata_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=METADATA_COLUMNS)
        if not exists:
            writer.writeheader()
        writer.writerow({column: row.get(column, "") for column in METADATA_COLUMNS})


def wav_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.wav") if path.is_file())
