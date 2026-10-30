#!/usr/bin/env python3
"""Collect unapproved Cebuano phrases into a separate manual-review area."""

import argparse
import json
import re
import uuid
from pathlib import Path
from record_keyword_dataset import record_wav
from import_keyword_datasets import anonymous, file_digest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phrase", required=True)
    p.add_argument("--speaker-id", required=True)
    p.add_argument("--session-id", required=True)
    p.add_argument("--seconds", type=float, default=3)
    p.add_argument("--device")
    p.add_argument("--recording-device-description", default="unknown")
    args = p.parse_args()
    if not 1 <= args.seconds <= 5 or not args.phrase.strip():
        p.error("Nonempty phrase and 1–5 seconds required")
    root = (
        Path(__file__).resolve().parents[2]
        / "dataset/audio/processed/cebuano_candidates"
    )
    root.mkdir(parents=True, exist_ok=True)
    sample = uuid.uuid4().hex
    path = root / (sample + ".wav")
    input(
        "Record only with consent. Press Enter to record the Cebuano candidate for review: "
    )
    record_wav(path, args.seconds, args.device)
    metadata = {
        "sample_id": sample,
        "path": path.name,
        "language": "ceb",
        "candidate_phrase": args.phrase.strip(),
        "speaker_id": anonymous("local", args.speaker_id),
        "session_id": anonymous("local-session", args.session_id),
        "recording_device": args.recording_device_description,
        "sha256": file_digest(path),
        "state": "REVIEW_REQUIRED",
        "label_verification": "unapproved",
        "runtime_activation": False,
        "license": "local-consented-research-no-redistribution",
    }
    path.with_suffix(".json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(
        "Saved candidate for competent Cebuano-speaker review; not added to positive training data."
    )


if __name__ == "__main__":
    main()
