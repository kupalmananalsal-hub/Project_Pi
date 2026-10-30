"""Explicit recording evidence and non-destructive legacy provenance review."""

from __future__ import annotations
import argparse
import csv
import json
import re
import wave
from pathlib import Path
from keyword_dataset_common import (
    KEYWORD_LANGUAGES,
    slugify_keyword,
    metadata_file_lock,
)
from import_keyword_datasets import (
    load_provenance,
    safe_path,
    provenance_path,
    write_provenance,
    file_digest,
    digest,
)
from validate_keyword_dataset import inspect_wav, issue_for


def recording_evidence(root, row, review=None):
    """Measure bytes; never infer consent, hardware, session or spoken language."""
    review = review or {}
    path = safe_path(root, row["path"])
    info = inspect_wav(path)
    if issue_for(info):
        raise ValueError("Invalid recording: " + issue_for(info))
    sha = file_digest(path)
    if review.get("expected_sha256") and review["expected_sha256"] != sha:
        raise ValueError("Review checksum mismatch")
    keyword = row["label"].replace("_", " ")
    if keyword not in KEYWORD_LANGUAGES:
        raise ValueError("Not a deployed positive keyword")
    if not row["path"].startswith("positive/" + slugify_keyword(keyword) + "/"):
        raise ValueError("Path/keyword mismatch")
    speaker = row.get("speaker_id") or "unknown"
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", speaker):
        raise ValueError(
            "Use a stable anonymous speaker ID; repair metadata with collection evidence first"
        )
    if review.get("speaker_id", speaker) != speaker:
        raise ValueError("Review cannot silently replace the original speaker ID")
    language = review.get("language", "und")
    if language != "und" and language != KEYWORD_LANGUAGES[keyword]:
        raise ValueError("Positive keyword language mismatch")
    session = review.get("session_id") or "unknown"
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", session):
        raise ValueError("Session must be an anonymous ID")
    device = review.get("recording_device") or "unknown"
    capture = review.get("capture_device") or "unknown"
    consent = review.get("consent_reference") or "unknown"
    verified = (
        review.get("audio_reviewed") is True
        and review.get("reviewer_id") not in (None, "", "unknown")
        and review.get("expected_sha256") == sha
        and language != "und"
        and speaker != "unknown"
        and session != "unknown"
        and device != "unknown"
        and capture != "unknown"
        and review.get("device_verified") is True
        and review.get("consent_confirmed") is True
        and consent != "unknown"
    )
    with wave.open(str(path), "rb") as wav:
        pcm = wav.readframes(wav.getnframes())
    return {
        "path": row["path"],
        "kind": "positive",
        "label": slugify_keyword(keyword),
        "keyword": keyword,
        "language": language,
        "speaker_id": speaker,
        "session_id": session,
        "source": "real",
        "source_group": "local-pcm-" + digest(pcm),
        "recording_device": device,
        "capture_device": capture,
        "device_verification": (
            "operator_and_capture_record"
            if review.get("device_verified") is True and capture != "unknown"
            else "unknown"
        ),
        "capture_origin": review.get("capture_origin", "legacy_unknown"),
        "consent_reference": consent,
        "consent_confirmed": review.get("consent_confirmed") is True,
        "license": (
            "local-consented-research-no-redistribution"
            if review.get("consent_confirmed") is True and consent != "unknown"
            else "unknown"
        ),
        "verification": (
            "operator_verified_recording" if verified else "unverified_recording"
        ),
        "validation_state": "PASS" if verified else "REVIEW_REQUIRED",
        "reviewer_id": review.get("reviewer_id") or "unknown",
        "sha256": sha,
        "processed_sha256": sha,
        "pcm_sha256": digest(pcm),
        # For legacy files the original capture bytes are not known; hash only the supplied WAV.
        "original_sha256": (
            sha if review.get("capture_origin") == "pi_recorder" else "unknown"
        ),
        "original_sample_rate": (
            info["sample_rate"]
            if review.get("capture_origin") == "pi_recorder"
            else "unknown"
        ),
        "sample_rate": info["sample_rate"],
        "channels": info["channels"],
        "duration_s": info["duration_s"],
        "start_ms": 0,
        "end_ms": info["duration_s"] * 1000,
        "noise_condition": row.get("noise_condition", "unknown"),
        "transform": (
            "No file conversion; recorded PCM16 mono"
            if review.get("capture_origin") == "pi_recorder"
            else "Legacy processing history unknown"
        ),
    }


def migrate(root, reviews=None, apply=False):
    """Dry-run; preserve WAV/CSV and approved evidence; explicitly review pending sidecars."""
    reviews = reviews or {}
    result = []
    with metadata_file_lock(root / "metadata.csv"):
        with (root / "metadata.csv").open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if len({r["path"] for r in rows}) != len(rows):
            raise ValueError("Duplicate metadata paths")
        if set(reviews) - {r["path"] for r in rows}:
            raise ValueError("Review references missing metadata")
        pending = []
        for row in rows:
            if not row["path"].startswith("positive/"):
                continue
            review = dict(reviews.get(row["path"], {}))
            existing = None
            if provenance_path(root, row["path"]).exists():
                existing = load_provenance(root, row["path"])
                if not review:
                    result.append({"path": row["path"], "state": "EXISTING_UNCHANGED"})
                    continue
                if existing.get("validation_state") != "REVIEW_REQUIRED":
                    raise ValueError("Cannot overwrite approved provenance")
                if review.get("expected_sha256") != file_digest(
                    safe_path(root, row["path"])
                ):
                    raise ValueError(
                        "Explicit current checksum required for pending review"
                    )
            if existing and existing.get("capture_origin") == "pi_recorder":
                if "capture_device" in review and review[
                    "capture_device"
                ] != existing.get("capture_device"):
                    raise ValueError("Cannot replace recorded capture-device evidence")
                review["capture_device"] = existing.get("capture_device", "unknown")
            # Migration cannot claim this program performed a historic capture.
            review["capture_origin"] = "legacy_review"
            evidence = recording_evidence(root, row, review)
            if existing:
                evidence["previous_provenance"] = existing
                evidence["previous_verification"] = existing.get(
                    "verification", "unknown"
                )
                evidence["capture_origin"] = existing.get(
                    "capture_origin", "legacy_unknown"
                )
                evidence["original_sha256"] = existing.get("original_sha256", "unknown")
                evidence["original_sample_rate"] = existing.get(
                    "original_sample_rate", "unknown"
                )
            pending.append((row["path"], evidence))
            result.append({"path": row["path"], "state": evidence["validation_state"]})
        if apply:
            for relative, evidence in pending:
                write_provenance(root, relative, evidence)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument(
        "--reviews",
        type=Path,
        help="Private JSONL with path and explicit collection/review evidence",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create missing sidecars; otherwise preview only",
    )
    args = parser.parse_args()
    reviews = {}
    if args.reviews:
        for line in args.reviews.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["path"] in reviews:
                raise ValueError("Duplicate review path")
            reviews[row["path"]] = row
    print(
        json.dumps(migrate(args.dataset_dir.resolve(), reviews, args.apply), indent=2)
    )


if __name__ == "__main__":
    main()
