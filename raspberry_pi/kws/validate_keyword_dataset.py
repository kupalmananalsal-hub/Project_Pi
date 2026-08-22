#!/usr/bin/env python3
"""Validate Project Pi keyword dataset WAV files and class balance."""

from __future__ import annotations

import argparse
import json
import sys
import wave
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from keyword_dataset_common import DEFAULT_DATASET_DIR, ensure_dataset_layout, wav_files  # noqa: E402

EXPECTED_SAMPLE_RATE = 16000
MIN_DURATION_SECONDS = 1.0
MAX_DURATION_SECONDS = 5.0
CLIPPING_THRESHOLD = 32760


def inspect_wav(path: Path) -> dict[str, object]:
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        sample_rate = handle.getframerate()
        frame_count = handle.getnframes()
        duration = frame_count / float(sample_rate or 1)
        frames = handle.readframes(frame_count)

    clipped = False
    if sample_width == 2:
        for index in range(0, len(frames), 2):
            sample = int.from_bytes(frames[index : index + 2], "little", signed=True)
            if abs(sample) >= CLIPPING_THRESHOLD:
                clipped = True
                break

    return {
        "path": path,
        "channels": channels,
        "sample_width": sample_width,
        "sample_rate": sample_rate,
        "duration_s": duration,
        "clipped": clipped,
    }


def issue_for(info: dict[str, object]) -> str | None:
    if info["sample_rate"] != EXPECTED_SAMPLE_RATE:
        return "sample_rate"
    if info["channels"] != 1:
        return "channels"
    if info["sample_width"] != 2:
        return "sample_width"
    if not (MIN_DURATION_SECONDS <= info["duration_s"] <= MAX_DURATION_SECONDS):
        return "duration"
    if info["clipped"]:
        return "clipping"
    return None


def validate_dataset(dataset_dir: Path) -> dict[str, object]:
    dataset_dir = dataset_dir.resolve()
    files = wav_files(dataset_dir)
    keyword_counts: Counter[str] = Counter()
    negative_counts: Counter[str] = Counter()
    issues = []
    valid_files = 0

    for path in files:
        relative_parts = path.relative_to(dataset_dir).parts
        if len(relative_parts) >= 3 and relative_parts[0] == "positive":
            keyword_counts[relative_parts[1]] += 1
        elif len(relative_parts) >= 3 and relative_parts[0] == "negative":
            negative_counts[relative_parts[1]] += 1

        try:
            info = inspect_wav(path)
            issue = issue_for(info)
        except (wave.Error, EOFError) as exc:
            issue = "unreadable"
            info = {"path": path, "error": str(exc)}

        if issue:
            issues.append(
                {
                    "path": str(path.relative_to(dataset_dir)),
                    "issue": issue,
                    **{k: v for k, v in info.items() if k != "path"},
                }
            )
        else:
            valid_files += 1

    return {
        "dataset_dir": str(dataset_dir),
        "total_files": len(files),
        "valid_files": valid_files,
        "invalid_files": len(issues),
        "keyword_counts": dict(sorted(keyword_counts.items())),
        "negative_counts": dict(sorted(negative_counts.items())),
        "issues": issues,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate sample rate, duration, clipping, and balance."
    )
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument(
        "--init-layout",
        action="store_true",
        help="create expected folders before validating",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.init_layout:
        ensure_dataset_layout(args.dataset_dir)
    report = validate_dataset(args.dataset_dir)
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="utf-8")
    return 1 if report["invalid_files"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
