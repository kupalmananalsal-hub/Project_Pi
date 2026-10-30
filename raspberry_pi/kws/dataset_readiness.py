#!/usr/bin/env python3
"""Factual source audit, manual-review queue, unified inventory and readiness."""

from __future__ import annotations
import argparse
import collections
import csv
import hashlib
import json
import re
import sqlite3
import wave
from pathlib import Path
from keyword_dataset_common import (
    KEYWORDS,
    KEYWORD_LANGUAGES,
    HARD_NEGATIVE_CLASSES,
    NEGATIVE_CLASSES,
    DEFAULT_DATASET_DIR,
    slugify_keyword,
    sample_subdirectory,
)
from import_keyword_datasets import (
    load_provenance,
    normalized,
    classify,
    file_digest,
    safe_path,
)
from validate_keyword_dataset import inspect_wav, issue_for
from dataset_integrity import grouped_split

INVENTORY_COLUMNS = [
    "Language",
    "Keyword/Negative Class",
    "Data Source",
    "Valid Samples",
    "Distinct Speakers",
    "Sessions",
    "Train",
    "Validation",
    "Test",
    "Missing Samples",
    "Issues",
]
SUMMARY_COLUMNS = [
    "Source Dataset",
    "Archive Accessible",
    "Archive SHA256",
    "Files Inspected",
    "Audio Files Imported",
    "Audio Files Rejected",
    "Transcript Matches",
    "Verified Samples",
    "Review-Required Samples",
    "License Restrictions",
    "Import Status",
]
READINESS_COLUMNS = [
    "Language",
    "Keyword",
    "Verified Positive Samples",
    "Verified Hard Negatives",
    "Distinct Positive Speakers",
    "Independent Source Groups",
    "Validation Coverage",
    "Test Coverage",
    "Training Readiness",
    "Blocking Issues",
]
SAMPLE_COLUMNS = [
    "Sample ID",
    "Relative Path",
    "Language",
    "Keyword/Negative Class",
    "Ground Truth Label",
    "Source Dataset",
    "Source Recording ID",
    "Speaker ID",
    "Session ID",
    "Parent Recording ID",
    "Start Time (ms)",
    "End Time (ms)",
    "Original Sample Rate",
    "Processed Sample Rate",
    "Duration (ms)",
    "Recording Device",
    "Noise Condition",
    "Transcript Verification",
    "Label Verification",
    "Assigned Split",
    "Source License",
    "SHA256",
    "Notes",
]


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


def audit_positives(root):
    folder = root / "positive"
    files = list(folder.rglob("*.wav")) if folder.exists() else []
    by_keyword = collections.Counter(p.parent.name for p in files)
    return {
        "directory": str(folder.resolve()),
        "state": (
            "SOURCE_UNAVAILABLE"
            if not folder.exists()
            else "EMPTY" if not files else "AVAILABLE"
        ),
        "wav_files": len(files),
        "by_keyword": {
            slugify_keyword(k): by_keyword[slugify_keyword(k)] for k in KEYWORDS
        },
        "respeaker_capture": "UNKNOWN unless supported by per-sample recording_device evidence",
    }


def near_duplicate_pairs(root, records, correlation=0.995):
    """Conservative waveform correlation screen, not a semantic/audio proof.

    Uses 1kHz signed waveform, zero mean and amplitude normalization. Flags
    gain/near-identical recordings of similar duration with up to 10ms offset.
    Human review is required; different recordings of the same word are not
    automatically treated as duplicates based on their transcript alone.
    """
    import numpy as np
    from scipy.signal import resample_poly

    features = []
    pairs = []
    for row in records:
        with wave.open(str(safe_path(root, row["path"])), "rb") as f:
            x = np.frombuffer(f.readframes(f.getnframes()), dtype="<i2").astype(
                np.float32
            )
        x = resample_poly(x, 1, 16)
        x = x - x.mean()
        norm = float(np.linalg.norm(x))
        if norm < 1e-8:
            continue
        x = x / norm
        for other, y in features:
            if abs(len(x) - len(y)) > max(10, int(0.02 * len(x))):
                continue
            best = 0.0
            for lag in (-10, -5, 0, 5, 10):
                a = x[max(0, lag) :]
                b = y[max(0, -lag) :]
                n = min(len(a), len(b))
                denom = float(np.linalg.norm(a[:n]) * np.linalg.norm(b[:n]))
                score = abs(float(np.dot(a[:n], b[:n]))) / max(denom, 1e-12)
                best = max(best, score)
            if best >= correlation:
                pairs.append(
                    {
                        "a": other["path"],
                        "b": row["path"],
                        "correlation": round(best, 6),
                        "state": "REVIEW_REQUIRED",
                    }
                )
        features.append((row, x))
    return pairs


def audit_records(root):
    metadata = root / "metadata.csv"
    rows = []
    if metadata.exists():
        with metadata.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    records = []
    issues = []
    seen = {}
    seen_paths = set()
    for row in rows:
        relative = row.get("path", "").replace("\\", "/")
        if relative.startswith("physical_holdout/"):
            continue
        try:
            if relative in seen_paths:
                raise ValueError("duplicate_metadata")
            seen_paths.add(relative)
            path = safe_path(root, relative)
            info = inspect_wav(path)
            issue = issue_for(info)
            if issue:
                raise ValueError(issue)
            p = load_provenance(root, relative)
            for field in (
                "license",
                "source_group",
                "language",
                "kind",
                "label",
                "verification",
                "sha256",
                "pcm_sha256",
            ):
                if not p.get(field):
                    raise ValueError("missing_" + field)
            if p["sha256"] != file_digest(path):
                raise ValueError("checksum_mismatch")
            with wave.open(str(path), "rb") as f:
                pcm = f.readframes(f.getnframes())
            if hashlib.sha256(pcm).hexdigest() != p["pcm_sha256"]:
                raise ValueError("pcm_checksum_mismatch")
            if p["kind"] not in ("positive", "negative"):
                raise ValueError("invalid_kind")
            allowed = (
                [slugify_keyword(k) for k in KEYWORDS]
                if p["kind"] == "positive"
                else NEGATIVE_CLASSES
            )
            if p["label"] not in allowed:
                raise ValueError("incorrect_label")
            if not relative.removeprefix("augmented/").startswith(
                sample_subdirectory(p["kind"], p["label"]) + "/"
            ):
                raise ValueError("path_label_mismatch")
            if slugify_keyword(row.get("label", "")) != p["label"]:
                raise ValueError("metadata_label_mismatch")
            if p.get("language") not in ("en", "fil", "ceb", "und"):
                raise ValueError("incorrect_language")
            if p["kind"] == "positive" and p["language"] != KEYWORD_LANGUAGES.get(
                p["label"].replace("_", " ")
            ):
                raise ValueError(
                    "unknown_positive_language"
                    if p["language"] == "und"
                    else "positive_language_mismatch"
                )
            if p.get("validation_state") == "REVIEW_REQUIRED":
                raise ValueError("unverified_recording_provenance")
            if p["kind"] == "positive" and p["language"] == "ceb":
                raise ValueError("Cebuano_positive_inventory_not_approved")
            if p["label"] not in ("noise", "silence", "music"):
                if not p.get("speaker_id") or p.get("speaker_id") == "unknown":
                    raise ValueError("unknown_speaker")
                if p["language"] == "und":
                    raise ValueError("unknown_speech_language")
            if row.get("speaker_id", "") != p.get("speaker_id", ""):
                raise ValueError("speaker_mismatch")
            if p.get("transcript"):
                expected = classify(p["transcript"])
                if expected != (p["kind"], p["label"]) and not (
                    p["transcript"] == "noise" and p["label"] == "silence"
                ):
                    raise ValueError("negative_contains_keyword_or_transcript_mismatch")
            if p["kind"] == "positive" and p.get("verification") not in (
                "operator_verified_recording",
                "human_audio_and_transcript_review",
                "source_validated_word",
            ):
                raise ValueError("unverified_positive")
            if p["pcm_sha256"] in seen:
                raise ValueError("duplicate_audio:" + seen[p["pcm_sha256"]])
            seen[p["pcm_sha256"]] = relative
            records.append(
                {
                    **row,
                    **p,
                    "path": relative,
                    "duration_s": info["duration_s"],
                    "state": "PASS",
                }
            )
        except (ValueError, OSError, EOFError, wave.Error) as exc:
            reason = str(exc)
            review = any(
                x in reason
                for x in ("unknown", "unverified", "Cebuano", "negative_contains")
            )
            issues.append(
                {
                    "path": relative,
                    "state": "REVIEW_REQUIRED" if review else "FAIL",
                    "issue": reason,
                }
            )
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        relative = p.relative_to(root).as_posix()
        if p.suffix.lower() in (".opus", ".mp3", ".flac", ".ogg"):
            issues.append(
                {
                    "path": relative,
                    "state": "FAIL",
                    "issue": "unsupported_dataset_audio",
                }
            )
        if (
            p.suffix.lower() == ".wav"
            and relative not in seen_paths
            and not relative.startswith((".tmp/", "models/", "physical_holdout/"))
        ):
            issues.append(
                {"path": relative, "state": "FAIL", "issue": "missing_metadata"}
            )
    by_path = {r["path"]: r for r in records}
    for row in records:
        parent = row.get("parent_path")
        if row.get("source") == "augmentation" and not parent:
            issues.append(
                {"path": row["path"], "state": "FAIL", "issue": "missing_parent"}
            )
        if parent:
            source = by_path.get(parent)
            if source is None or any(
                source.get(k) != row.get(k)
                for k in ("language", "kind", "label", "speaker_id", "source_group")
            ):
                issues.append(
                    {
                        "path": row["path"],
                        "state": "FAIL",
                        "issue": "augmentation_ancestry",
                    }
                )
    bad = {x["path"] for x in issues}
    records = [r for r in records if r["path"] not in bad]
    pairs = near_duplicate_pairs(root, records)
    for pair in pairs:
        for path in (pair["a"], pair["b"]):
            issues.append(
                {
                    "path": path,
                    "state": "REVIEW_REQUIRED",
                    "issue": "near_duplicate_audio",
                }
            )
    bad = {x["path"] for x in issues}
    return [r for r in records if r["path"] not in bad], issues, pairs


def mine_transcript_candidates(catalog, output):
    con = sqlite3.connect(catalog)
    con.row_factory = sqlite3.Row
    rows = []
    hard = collections.Counter()
    positive = collections.Counter()
    try:
        for r in con.execute(
            "SELECT annotations.* FROM annotations JOIN assets USING(name)"
        ):
            if r["language"] not in ("en", "fil", "ceb"):
                continue
            text = normalized(r["transcript"])
            targets = [
                k for k in KEYWORDS if re.search(r"\b" + re.escape(k) + r"\b", text)
            ]
            negatives = [
                k
                for k in HARD_NEGATIVE_CLASSES
                if re.search(r"\b" + re.escape(k) + r"\b", text)
            ]
            for kind, words, counter in [
                ("positive_candidate", targets, positive),
                ("hard_negative_candidate", negatives, hard),
            ]:
                for label in words:
                    counter[(r["language"], label)] += 1
                    rows.append(
                        {
                            "member": r["name"],
                            "language": r["language"],
                            "candidate_label": label,
                            "kind": kind,
                            "transcript": r["transcript"],
                            "speaker_id": r["speaker_id"],
                            "source_group": r["source_group"],
                            "state": "REVIEW_REQUIRED",
                            "audio_reviewed": False,
                            "start_s": None,
                            "end_s": None,
                            "issue": (
                                "timestamps_and_audio_verification_required"
                                if kind == "positive_candidate" or targets
                                else "verify_whole_clip_label"
                            ),
                        }
                    )
    finally:
        con.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {
        "candidates": len(rows),
        "candidate_recordings": len({r["member"] for r in rows}),
        "positive_matches": [
            {"language": k[0], "label": k[1], "count": v}
            for k, v in sorted(positive.items())
        ],
        "hard_negative_matches": [
            {"language": k[0], "label": k[1], "count": v}
            for k, v in sorted(hard.items())
        ],
    }


def sample_inventory(rows, splits):
    result = []
    for r in rows:
        values = [
            r.get("sample_id", Path(r["path"]).stem),
            r["path"],
            r["language"],
            r["label"],
            r["kind"],
            r.get("source", "unknown"),
            r["source_group"],
            r.get("speaker_id") or "unknown",
            r.get("session_id", "unknown"),
            r.get("parent_path", "unknown"),
            r.get("start_ms", "unknown"),
            r.get("end_ms", "unknown"),
            r.get("original_sample_rate", "unknown"),
            16000,
            round(r["duration_s"] * 1000),
            r.get("recording_device", "unknown"),
            r.get("noise_condition", "unknown"),
            r.get("verification", "unknown"),
            r.get("label_verification", r.get("verification", "unknown")),
            splits.get(r["path"], "unassigned"),
            r["license"],
            r["sha256"],
            r.get("notes", ""),
        ]
        result.append(dict(zip(SAMPLE_COLUMNS, values)))
    return result


def generate_report(root, out, seed=1337):
    out.mkdir(parents=True, exist_ok=True)
    records, issues, near = audit_records(root)
    positives = audit_positives(root)
    split_error = None
    manifest = None
    if records:
        try:
            manifest = grouped_split(
                records,
                seed,
                negative_only=not any(r["kind"] == "positive" for r in records),
            )
        except ValueError as exc:
            split_error = str(exc)
    splits = manifest["path_splits"] if manifest else {}
    if manifest:
        directory = root / "splits"
        directory.mkdir(exist_ok=True)
        (
            directory / "negative_only_split.json"
            if not any(r["kind"] == "positive" for r in records)
            else directory / "prepared_split.json"
        ).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    inventory = []
    keys = sorted(
        {(r["language"], r["label"], r.get("source", "unknown")) for r in records}
    )
    for language, label, source in keys:
        group = [
            r
            for r in records
            if (r["language"], r["label"], r.get("source", "unknown"))
            == (language, label, source)
        ]
        values = [
            language,
            label,
            source,
            len(group),
            len(
                {
                    r["speaker_id"]
                    for r in group
                    if r.get("speaker_id") and r["speaker_id"] != "unknown"
                }
            ),
            len(
                {
                    r["session_id"]
                    for r in group
                    if r.get("session_id") not in (None, "unknown")
                }
            ),
            *[
                sum(splits.get(r["path"]) == s for r in group)
                for s in ("train", "val", "test")
            ],
            "NOT_SPECIFIED",
            split_error or "PASS: source transcript labels; no recognition claim",
        ]
        inventory.append(dict(zip(INVENTORY_COLUMNS, values)))
    readiness = []
    for language, keywords in [
        ("en", KEYWORDS[:8]),
        ("fil", KEYWORDS[8:]),
        ("ceb", ["NO_APPROVED_POSITIVE_INVENTORY"]),
    ]:
        for keyword in keywords:
            label = slugify_keyword(keyword)
            group = [
                r
                for r in records
                if r["kind"] == "positive"
                and r["language"] == language
                and r["label"] == label
            ]
            negatives = [
                r
                for r in records
                if r["kind"] == "negative" and r["language"] == language
            ]
            hard = [r for r in negatives if r["label"] in HARD_NEGATIVE_CLASSES]
            speakers = {r["speaker_id"] for r in group}
            groups = {r["source_group"] for r in group}
            state = (
                "INSUFFICIENT_POSITIVES"
                if not group
                else (
                    "INSUFFICIENT_SPEAKERS"
                    if len(speakers) < 3
                    else (
                        "INSUFFICIENT_NEGATIVES"
                        if not negatives or not hard
                        else (
                            "LEAKAGE_DETECTED"
                            if split_error
                            else "READY_FOR_EXPERIMENT"
                        )
                    )
                )
            )
            coverage = [
                sum(splits.get(r["path"]) == s for r in group) for s in ("val", "test")
            ]
            if state == "READY_FOR_EXPERIMENT" and not all(coverage):
                state = "INSUFFICIENT_SPEAKERS"
            values = [
                language,
                keyword,
                len(group),
                len(hard),
                len(speakers),
                len(groups),
                *coverage,
                state,
                (
                    "No verified positives; public transcript matches require review"
                    if not group
                    else (
                        split_error
                        or (
                            "No verified hard negatives"
                            if not hard
                            else (
                                "Insufficient independent evaluation coverage"
                                if state != "READY_FOR_EXPERIMENT"
                                else "none"
                            )
                        )
                    )
                ),
            ]
            readiness.append(dict(zip(READINESS_COLUMNS, values)))
    hard_status = []
    for label in HARD_NEGATIVE_CLASSES:
        count = sum(r["kind"] == "negative" and r["label"] == label for r in records)
        hard_status.append(
            {
                "expression": label,
                "verified_samples": count,
                "status": "AVAILABLE" if count else "MISSING",
                "collection": "Consenting speakers; stable anonymous speaker/session IDs; actual ReSpeaker device recorded explicitly; do not utter a target keyword; keep physical holdout separate",
            }
        )
    write_csv(out / "dataset_inventory.csv", INVENTORY_COLUMNS, inventory)
    write_csv(out / "training_readiness.csv", READINESS_COLUMNS, readiness)
    write_csv(
        out / "sample_inventory.csv", SAMPLE_COLUMNS, sample_inventory(records, splits)
    )
    report = {
        "positive_audit": positives,
        "valid_samples": len(records),
        "issues": issues,
        "near_duplicate_pairs": near,
        "split_error": split_error,
        "split_counts": dict(collections.Counter(splits.values())),
        "hard_negatives": hard_status,
        "model_training": "NOT RUN; forbidden in this phase",
        "physical_holdout": "Not supplied; keep separate from import/mining/training",
        "criteria": "Verified labels/provenance; no duplicate/near-duplicate issues; >=3 independent real speaker/source groups per positive language/label, positives and negatives in each split, verified hard negatives; no minimum sample target specified.",
        "statuses": {
            "PASS": len(records),
            "FAIL": sum(x["state"] == "FAIL" for x in issues),
            "REVIEW_REQUIRED": sum(x["state"] == "REVIEW_REQUIRED" for x in issues),
            "WARNING": 1 if not positives["wav_files"] else 0,
        },
    }
    (out / "readiness.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def import_summary(root, out, records, catalog_paths):
    from import_keyword_datasets import SOURCES

    summary = []
    for source, catalog in catalog_paths.items():
        con = sqlite3.connect(catalog)
        info = json.loads(
            con.execute("SELECT value FROM info WHERE key='manifest'").fetchone()[0]
        )
        con.close()
        mining = mine_transcript_candidates(
            catalog, out / (source + "-review-candidates.jsonl")
        )
        (out / (source + "-mining-summary.json")).write_text(
            json.dumps(mining, indent=2), encoding="utf-8"
        )
        imported_path = root / "reports" / (source + "-import.json")
        if source == "speech_commands":
            imported_path = root / "reports/gsc-import.json"
        imported = (
            json.loads(imported_path.read_text()) if imported_path.exists() else {}
        )
        source_rows = [r for r in records if r.get("source") == source]
        values = [
            source,
            "YES",
            info["archive_sha256"],
            sum(info["extensions"].values()),
            sum(x["count"] for x in imported.get("counts", [])),
            sum(imported.get("rejected", {}).values()),
            sum(x["count"] for x in mining["positive_matches"]),
            len(source_rows),
            mining["candidate_recordings"],
            info["license"]
            + (
                "; research only; no third-party sharing/redistribution without written consent; no speaker identification"
                if source == "pld"
                else "; attribution required; no speaker identification; no public data in this change"
            ),
            (
                "IMPORTED_WITH_REJECTIONS"
                if imported.get("rejected")
                else "IMPORTED" if imported else "CATALOG_ONLY"
            ),
        ]
        summary.append(dict(zip(SUMMARY_COLUMNS, values)))
    write_csv(out / "import_summary.csv", SUMMARY_COLUMNS, summary)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_DATASET_DIR / "reports")
    p.add_argument("--catalog", type=Path)
    p.add_argument("--seed", type=int, default=1337)
    p.add_argument("--all-source-summaries", action="store_true")
    args = p.parse_args()
    # Generated detailed sample/transcript reports are private and local only.
    allowed = args.dataset_dir.resolve() / "reports"
    if not args.output_dir.resolve().is_relative_to(allowed):
        p.error("Detailed reports must stay inside dataset-dir/reports")
    report = generate_report(args.dataset_dir, args.output_dir, args.seed)
    if args.catalog:
        report["transcript_mining"] = mine_transcript_candidates(
            args.catalog, args.output_dir / "review_candidates.jsonl"
        )
    if args.all_source_summaries:
        records, _, _ = audit_records(args.dataset_dir)
        catalog_paths = {
            source: args.dataset_dir / "catalogs" / name
            for source, name in [
                ("pld", "pld.sqlite"),
                ("mswc", "mswc.sqlite"),
                ("speech_commands", "gsc-v2.sqlite"),
            ]
        }
        report["imports"] = import_summary(
            args.dataset_dir, args.output_dir, records, catalog_paths
        )
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("issues", "near_duplicate_pairs")
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
