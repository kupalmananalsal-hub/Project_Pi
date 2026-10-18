#!/usr/bin/env python3
"""Shared constants and helpers for the Project Pi keyword dataset tools."""

from __future__ import annotations

import csv
import re
import threading
from contextlib import contextmanager
from pathlib import Path

try:  # Pi deployments require coordination with augmentation subprocesses.
    import fcntl
except ImportError:  # Windows tests retain thread-only protection.
    fcntl = None


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

# Module-level lock used by all KWS CLI tools.  The backend imports and aliases
# this as TRAINING_METADATA_LOCK so both code paths share the same mutex.
# Uses RLock so that callers holding the lock can reentrantly call append_metadata().
METADATA_LOCK = threading.RLock()
_METADATA_LOCK_STATE = threading.local()


@contextmanager
def advisory_file_lock(lock_path: Path):
    """Serialize work across local threads and POSIX processes."""
    key = str(lock_path.resolve())
    active = getattr(_METADATA_LOCK_STATE, "active", {})
    entry = active.get(key)
    if entry is not None:
        entry["depth"] += 1
        try:
            yield
        finally:
            entry["depth"] -= 1
        return

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with METADATA_LOCK:
        with lock_path.open("a", encoding="utf-8") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            active[key] = {"depth": 1}
            _METADATA_LOCK_STATE.active = active
            try:
                yield
            finally:
                active.pop(key, None)
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def metadata_file_lock(metadata_path: Path):
    """Serialize a metadata file across threads and POSIX processes."""
    lock_path = metadata_path.with_name(f".{metadata_path.name}.lock")
    with advisory_file_lock(lock_path):
        yield


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
    with metadata_file_lock(metadata_path):
        if not metadata_path.exists():
            with metadata_path.open("w", newline="", encoding="utf-8") as handle:
                csv.DictWriter(handle, fieldnames=METADATA_COLUMNS).writeheader()


def append_metadata(metadata_path: Path, row: dict[str, object]) -> None:
    """Append one metadata row, creating the CSV header when needed.

    Thread-safe: acquires METADATA_LOCK before writing so concurrent callers
    (the download script, the recorder, and the backend) do not interleave rows.
    """
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with metadata_file_lock(metadata_path):
        exists = metadata_path.exists()
        with metadata_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=METADATA_COLUMNS)
            if not exists:
                writer.writeheader()
            writer.writerow({column: row.get(column, "") for column in METADATA_COLUMNS})


def wav_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.wav") if path.is_file())
