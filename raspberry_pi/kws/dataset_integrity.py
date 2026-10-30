"""Strict provenance validation and globally grouped speaker-disjoint splits."""

from __future__ import annotations
import collections
import csv
import hashlib
import json
import random
import wave
from pathlib import Path
from keyword_dataset_common import (
    KEYWORDS,
    NEGATIVE_CLASSES,
    slugify_keyword,
    sample_subdirectory,
)
from import_keyword_datasets import safe_path, load_provenance, file_digest, classify
from validate_keyword_dataset import inspect_wav, issue_for


def validated_rows(root):
    root = Path(root).resolve()
    with (root / "metadata.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    paths = set()
    output = []
    audio_hashes = {}
    for row in rows:
        relative = row.get("path", "").replace("\\", "/")
        if relative in paths:
            raise ValueError("Duplicate metadata path: " + relative)
        paths.add(relative)
        path = safe_path(root, relative)
        info = inspect_wav(path)
        issue = issue_for(info)
        if issue:
            raise ValueError(issue + ": " + relative)
        provenance = load_provenance(root, relative)
        required = (
            "language",
            "source_group",
            "license",
            "verification",
            "sha256",
            "pcm_sha256",
            "kind",
            "label",
        )
        if any(not provenance.get(k) for k in required):
            raise ValueError("Missing provenance fields: " + relative)
        if provenance["sha256"] != file_digest(path):
            raise ValueError("Audio checksum mismatch: " + relative)
        with wave.open(str(path), "rb") as wav:
            pcm = wav.readframes(wav.getnframes())
        pcm_sha = hashlib.sha256(pcm).hexdigest()
        if pcm_sha != provenance["pcm_sha256"]:
            raise ValueError("PCM checksum mismatch: " + relative)
        label = provenance["label"]
        kind = provenance["kind"]
        if provenance.get("transcript") and not provenance.get("parent_path"):
            expected = classify(provenance["transcript"])
            if expected != (kind, label) and not (
                provenance["transcript"] == "noise" and label == "silence"
            ):
                raise ValueError("Transcript label mismatch: " + relative)
        if kind not in ("positive", "negative"):
            raise ValueError("Invalid kind")
        if label not in (
            [slugify_keyword(x) for x in KEYWORDS]
            if kind == "positive"
            else NEGATIVE_CLASSES
        ):
            raise ValueError("Invalid label: " + relative)
        actual_relative = relative.removeprefix("augmented/")
        if not actual_relative.startswith(sample_subdirectory(kind, label) + "/"):
            raise ValueError("Path label mismatch: " + relative)
        if slugify_keyword(row.get("label", "")) != label:
            raise ValueError("Metadata label mismatch: " + relative)
        if not provenance.get("speaker_id") and label not in (
            "noise",
            "silence",
            "music",
        ):
            raise ValueError("Missing anonymous speaker: " + relative)
        if label not in ("noise", "silence", "music") and provenance[
            "language"
        ] not in ("en", "fil", "ceb"):
            raise ValueError("Speech requires explicit supported language: " + relative)
        if row.get("speaker_id", "") != provenance.get("speaker_id", ""):
            raise ValueError("Speaker metadata mismatch: " + relative)
        if pcm_sha in audio_hashes:
            raise ValueError(
                "Duplicate audio: " + relative + " and " + audio_hashes[pcm_sha]
            )
        audio_hashes[pcm_sha] = relative
        output.append({**row, **provenance, "path": relative})
    actual = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*.wav")
        if ".tmp" not in p.parts and "models" not in p.parts
    }
    if actual != paths:
        raise ValueError("Unindexed or missing audio files")
    for pattern in ("*.mp3", "*.opus", "*.flac", "*.ogg"):
        if any(root.rglob(pattern)):
            raise ValueError("Unsupported dataset audio format: " + pattern)
    return output


def grouped_split(rows, seed=1337, negative_only=False):
    """Union speaker AND recording AND parent links before any split assignment."""
    for row in rows:
        if row["path"].startswith("physical_holdout/"):
            raise ValueError("Physical holdout cannot enter preparation splits")
        if row.get("label") not in ("noise", "silence", "music") and row.get(
            "speaker_id"
        ) in (None, "", "unknown"):
            raise ValueError("Unknown speaker requires review before splitting")
    by_path = {r["path"]: r for r in rows}
    if len(by_path) != len(rows):
        raise ValueError("Duplicate paths")
    parent = {p: p for p in by_path}

    def find(p):
        while parent[p] != p:
            parent[p] = parent[parent[p]]
            p = parent[p]
        return p

    def union(a, b):
        parent[find(a)] = find(b)

    seen = {}
    for row in rows:
        for key in (
            "speaker_id",
            "source_group",
            "session_id",
            "pcm_sha256",
            "near_duplicate_group",
        ):
            value = row.get(key)
            if value and value != "unknown":
                identity = (key, value)
                if identity in seen:
                    union(row["path"], seen[identity])
                else:
                    seen[identity] = row["path"]
        source_parent = row.get("parent_path")
        if row.get("source") == "augmentation" and not source_parent:
            raise ValueError("Missing augmentation parent")
        if source_parent:
            if source_parent not in by_path:
                raise ValueError("Unknown augmentation parent")
            original = by_path[source_parent]
            if any(
                row.get(k) != original.get(k)
                for k in ("kind", "label", "language", "speaker_id", "source_group")
            ):
                raise ValueError("Augmentation lineage mismatch")
            union(row["path"], source_parent)
    groups = collections.defaultdict(list)
    for row in rows:
        groups[find(row["path"])].append(row)

    # Require real, non-augmented examples of every language/positive label and
    # every negative language in all splits. Scarcity is an error, never leakage.
    def strata(row):
        return (
            row["language"],
            row["label"] if row["kind"] == "positive" else "__negative__",
        )

    real = lambda r: not r.get("parent_path") and r.get("source") not in (
        "tts",
        "synthetic",
        "augmentation",
    )
    needed = set() if negative_only else {strata(r) for r in rows if real(r)}
    for language, label in needed:
        if label != "__negative__" and (language, "__negative__") not in needed:
            raise ValueError("Missing language-matched negatives: " + language)
    for item in needed:
        n = sum(any(real(r) and strata(r) == item for r in g) for g in groups.values())
        if n < 3:
            raise ValueError(
                f"Insufficient disjoint coverage for {item}: {n} groups; need at least 3"
            )
    if not negative_only and not any(r["kind"] == "positive" for r in rows):
        raise ValueError("No positive examples")
    if not any(r["kind"] == "negative" for r in rows):
        raise ValueError("No negative examples")
    names = ("train", "val", "test")
    assignments = None
    # Deterministic bounded search over connected components; never split a group.
    for attempt in range(2000):
        rng = random.Random(seed + attempt)
        candidate = {}
        coverage = {s: set() for s in names}
        keys = sorted(groups)
        rng.shuffle(keys)
        for key in keys:
            group = groups[key]
            synthetic = any(r.get("source") in ("tts", "synthetic") for r in group)
            official = {
                r.get("official_split")
                for r in group
                if r.get("official_split") in names
            }
            if len(official) > 1:
                raise ValueError(
                    "Official split conflicts with speaker/source independence"
                )
            if synthetic and official and official != {"train"}:
                raise ValueError("Synthetic/official split conflict")
            split = (
                next(iter(official))
                if official
                else (
                    "train"
                    if synthetic
                    else rng.choices(names, weights=(0.7, 0.15, 0.15))[0]
                )
            )
            candidate[key] = split
            coverage[split].update(strata(r) for r in group if real(r))
        if all(coverage[s] >= needed for s in names):
            assignments = candidate
            break
    if assignments is None:
        raise ValueError(
            "Cannot satisfy disjoint coverage with available connected groups"
        )
    path_splits = {r["path"]: assignments[k] for k, g in groups.items() for r in g}
    for key in (
        "speaker_id",
        "source_group",
        "session_id",
        "pcm_sha256",
        "near_duplicate_group",
    ):
        mapping = collections.defaultdict(set)
        for r in rows:
            if r.get(key) and r[key] != "unknown":
                mapping[r[key]].add(path_splits[r["path"]])
        if any(len(v) > 1 for v in mapping.values()):
            raise ValueError("Leakage: " + key)
    keywords = {}
    for label in sorted({r["label"] for r in rows if r["kind"] == "positive"}):
        keywords[label] = {
            s: {
                "positive": [
                    r["path"]
                    for r in rows
                    if path_splits[r["path"]] == s
                    and r["kind"] == "positive"
                    and r["label"] == label
                ],
                "negative": [
                    r["path"]
                    for r in rows
                    if path_splits[r["path"]] == s and r["kind"] == "negative"
                ],
            }
            for s in names
        }
    return {
        "schema_version": 2,
        "purpose": (
            "negative_only_no_positive_training"
            if negative_only
            else "training_preparation"
        ),
        "split_seed": seed,
        "path_splits": path_splits,
        "keywords": keywords,
        "speakers": {
            s: sorted(
                {
                    r["speaker_id"]
                    for r in rows
                    if r.get("speaker_id") and path_splits[r["path"]] == s
                }
            )
            for s in names
        },
        "records": sorted(rows, key=lambda r: r["path"]),
    }


def build_strict_manifest(root, seed=1337):
    from dataset_readiness import audit_records

    records, issues, _ = audit_records(Path(root))
    if issues:
        raise ValueError("Dataset review/validation required: " + issues[0]["issue"])
    return grouped_split(records, seed)


def evaluate_scores(records, scores, threshold=0.5):
    if not 0 <= threshold <= 1:
        raise ValueError("Invalid threshold")
    import math

    if set(scores) != {r["path"] for r in records}:
        raise ValueError("Scores must cover exactly the evaluation records")
    groups = collections.defaultdict(
        lambda: collections.Counter(tp=0, fp=0, tn=0, fn=0)
    )
    for r in records:
        score = float(scores[r["path"]])
        if not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("Invalid score")
        positive = r["kind"] == "positive"
        predicted = score >= threshold
        outcome = (
            "tp"
            if positive and predicted
            else "fn" if positive else "fp" if predicted else "tn"
        )
        groups[r["language"]][outcome] += 1
    return {
        lang: {
            **c,
            "recall": c["tp"] / max(1, c["tp"] + c["fn"]),
            "false_positive_rate": c["fp"] / max(1, c["fp"] + c["tn"]),
            "precision": c["tp"] / max(1, c["tp"] + c["fp"]),
        }
        for lang, c in sorted(groups.items())
    }


def validate_export(records, root, destination):
    """Only local dataset exports; restricted corpora cannot enter downloadable ZIPs."""
    if (
        not Path(destination)
        .resolve()
        .is_relative_to(Path(root).resolve() / "archives")
    ):
        raise ValueError("Restricted dataset export destination")
    if any(r.get("source") == "pld" for r in records):
        raise ValueError(
            "UP-DSP prohibits third-party sharing without written consent; export blocked"
        )
