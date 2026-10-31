#!/usr/bin/env python3
"""Bounded, transcript-driven imports. No archive is extracted with extractall()."""

from __future__ import annotations
import argparse
import collections
import csv
import hashlib
import io
import json
import math
import re
import sqlite3
import tarfile
import urllib.request
import unicodedata
import wave
from pathlib import Path, PurePosixPath
from keyword_dataset_common import (
    KEYWORDS,
    HARD_NEGATIVE_CLASSES,
    NEGATIVE_CLASSES,
    DEFAULT_DATASET_DIR,
    append_metadata,
    ensure_dataset_layout,
    metadata_file_lock,
    slugify_keyword,
    sample_subdirectory,
)

SOURCES = {
    "pld": {
        "license": "CC-BY-NC-4.0",
        "url": "https://mozilladatacollective.com/datasets/cmmxhw46c00tqnw07xyr94zjk",
    },
    "mswc": {
        "license": "CC-BY-4.0",
        "url": "https://mlcommons.org/datasets/multilingual-spoken-words/",
    },
    "speech_commands": {
        "license": "CC-BY-4.0",
        "url": "https://storage.googleapis.com/download.tensorflow.org/data/speech_commands_v0.02.tar.gz",
    },
}
GSC_SHA256 = "af14739ee7dc311471de98f5f9d2c9191b18aedfe957f4a6ff791c709868ff58"
GSC_WORDS = set(
    "backward bed bird cat dog down eight five follow forward four go happy house learn left marvin nine no off on one right seven sheila six stop three tree two up visual wow yes zero".split()
)
LANGUAGES = {"FIL": "fil", "TAG": "fil", "CEB": "ceb", "ENG": "en"}
MAX_MEMBER = 64 * 1024 * 1024
MAX_EXPANDED_BYTES = 200 * 1024**3
MAX_OUTPUT_BYTES = 2 * 1024**3


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def anonymous(source, value):
    return source + "-" + digest(str(value).encode())[:24]


def safe_name(name):
    # Reject Windows drives/ADS, backslashes, absolute paths, traversal and links.
    p = PurePosixPath(name)
    if not name or "\\" in name or ":" in name or p.is_absolute() or ".." in p.parts:
        raise ValueError("Unsafe archive/metadata path")
    return p.as_posix().removeprefix("./")


def safe_path(root, name):
    target = (root / safe_name(name)).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Path escapes dataset")
    return target


def normalized(text):
    text = "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def classify(text):
    text = normalized(text)
    if text in KEYWORDS:
        return "positive", slugify_keyword(text)
    if text in NEGATIVE_CLASSES:
        return "negative", text
    # A sentence containing a target is not an isolated positive or a negative.
    if not text or any(re.search(r"\b" + re.escape(k) + r"\b", text) for k in KEYWORDS):
        return None
    return "negative", "random_speech"


def parse_pld(name, text):
    parts = PurePosixPath(name).parts
    if len(parts) < 4 or parts[1] not in LANGUAGES:
        return []
    speaker = re.search(r'^SpeakerID\s*=\s*"([^"]+)"', text, re.M)
    if not speaker:
        return []
    rows = []
    for line in text.splitlines():
        match = re.fullmatch(r'\s*([^\s]+\.wav)\s+"[^"]*"\s+"([^"]*)"\s*', line)
        if not match:
            continue
        filename, transcript = match.groups()
        member = safe_name(str(PurePosixPath(name).parent / safe_name(filename)))
        rows.append(
            (
                member,
                LANGUAGES[parts[1]],
                anonymous("pld", speaker[1]),
                anonymous("pld-recording", member),
                transcript,
                "source_transcript",
            )
        )
    return rows


def parse_mswc(name, text):
    parent = PurePosixPath(name).parent
    language = parent.name
    if language not in ("en", "es"):
        return []
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("VALID", "").lower() != "true" or not row.get("SPEAKER", "").strip():
            continue
        link = safe_name(row["LINK"])
        member = str(parent / "clips" / link)
        # Different words cut from one Common Voice sentence share this group.
        group = anonymous("mswc-recording", language + "/" + PurePosixPath(link).stem)
        rows.append(
            (
                member,
                language,
                anonymous("commonvoice", row["SPEAKER"]),
                group,
                row["WORD"],
                "source_validated_word",
            )
        )
    return rows


def scan_archive(archive, catalog, source):
    if catalog.exists():
        raise ValueError(
            "Catalog exists; use a new output name or reuse the existing catalog"
        )
    catalog.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(catalog)
    con.executescript(
        "CREATE TABLE assets(name TEXT PRIMARY KEY,size INTEGER); CREATE TABLE annotations(name TEXT PRIMARY KEY, language TEXT,speaker_id TEXT,source_group TEXT,transcript TEXT,verification TEXT); CREATE TABLE info(key TEXT PRIMARY KEY,value TEXT);"
    )
    counts = collections.Counter()
    expanded_bytes = 0
    try:
        with tarfile.open(archive, "r|gz") as tar:
            for member in tar:
                name = safe_name(member.name)
                if member.isdir():
                    continue
                if not member.isfile() or member.size > MAX_MEMBER:
                    raise ValueError(
                        "Unsafe archive member type or excessive member size: " + name
                    )
                expanded_bytes += member.size
                if expanded_bytes > MAX_EXPANDED_BYTES:
                    raise ValueError("Expanded archive volume exceeds limit")
                con.execute("INSERT INTO assets VALUES(?,?)", (name, member.size))
                if source == "speech_commands" and PurePosixPath(name).name in (
                    "validation_list.txt",
                    "testing_list.txt",
                ):
                    con.execute(
                        "INSERT INTO info VALUES(?,?)",
                        (
                            "official_split:" + PurePosixPath(name).name,
                            tar.extractfile(member).read().decode("utf-8"),
                        ),
                    )
                counts[PurePosixPath(name).suffix.lower()] += 1
                suffix = PurePosixPath(name).suffix.lower()
                rows = []
                if source == "pld" and suffix == ".log":
                    rows = parse_pld(
                        name,
                        tar.extractfile(member)
                        .read()
                        .decode("utf-8-sig", errors="strict"),
                    )
                elif source == "mswc" and suffix == ".csv":
                    rows = parse_mswc(
                        name, tar.extractfile(member).read().decode("utf-8-sig")
                    )
                elif source == "speech_commands" and suffix == ".wav":
                    parts = PurePosixPath(name).parts
                    word = parts[-2]
                    if word in GSC_WORDS:
                        speaker = PurePosixPath(name).stem.split("_nohash_")[0]
                        rows = [
                            (
                                name,
                                "en",
                                anonymous("gsc", speaker),
                                anonymous("gsc-recording", name),
                                word,
                                "source_word_label",
                            )
                        ]
                    elif word == "_background_noise_":
                        rows = [
                            (
                                name,
                                "und",
                                "",
                                anonymous("gsc-recording", name),
                                "noise",
                                "source_noise_label",
                            )
                        ]
                for row in rows:
                    existing = con.execute(
                        "SELECT * FROM annotations WHERE name=?", (row[0],)
                    ).fetchone()
                    if existing and tuple(existing) != tuple(row):
                        raise ValueError("Conflicting source annotations: " + row[0])
                    con.execute(
                        "INSERT OR IGNORE INTO annotations VALUES(?,?,?,?,?,?)", row
                    )
                if (
                    PurePosixPath(name).name.lower()
                    in (
                        "license",
                        "license.txt",
                        "readme.md",
                        "mswc_microset_readme.txt",
                    )
                    and member.size < 100000
                ):
                    text = (
                        tar.extractfile(member).read().decode("utf-8", errors="replace")
                    )
                    con.execute(
                        "INSERT OR REPLACE INTO info VALUES(?,?)",
                        ("source_notice:" + name, text),
                    )
        archive_sha = file_digest(archive)
        if source == "speech_commands" and archive_sha != GSC_SHA256:
            raise ValueError("Speech Commands v0.02 archive checksum mismatch")
        info = {
            "source": source,
            "archive_sha256": archive_sha,
            "license": SOURCES[source]["license"],
            "source_url": SOURCES[source]["url"],
            "archive_bytes": archive.stat().st_size,
            "extensions": dict(counts),
            "complete": True,
        }
        con.execute("INSERT INTO info VALUES(?,?)", ("manifest", json.dumps(info)))
        con.commit()
        return summarize_catalog(con, info)
    finally:
        con.close()


def summarize_catalog(con, info):
    coverage = collections.Counter()
    for language, transcript in con.execute(
        "SELECT language,transcript FROM annotations JOIN assets USING(name)"
    ):
        decision = classify(transcript)
        if decision:
            coverage[(language, *decision)] += 1
    return {
        **info,
        "transcript_matches": [
            {"language": k[0], "kind": k[1], "label": k[2], "count": v}
            for k, v in sorted(coverage.items())
        ],
        "languages": dict(
            con.execute("SELECT language,count(*) FROM annotations GROUP BY language")
        ),
        "audio_members": con.execute(
            "SELECT count(*) FROM assets WHERE name LIKE '%.wav' OR name LIKE '%.opus'"
        ).fetchone()[0],
    }


def provenance_path(root, relative):
    return root / "provenance" / (digest(relative.encode()) + ".json")


def write_provenance(root, relative, row):
    p = provenance_path(root, relative)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(p)


def load_provenance(root, relative):
    p = provenance_path(root, relative)
    if not p.exists():
        raise ValueError("Missing provenance: " + relative)
    return json.loads(p.read_text(encoding="utf-8"))


def normalized_audio(data):
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly

    samples, rate = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    if (
        not 8000 <= rate <= 192000
        or len(samples) == 0
        or samples.shape[1] > 2
        or not np.isfinite(samples).all()
    ):
        raise ValueError("Unsupported or empty audio")
    # Reject clipping before downmix/resampling can hide it.
    if np.max(np.abs(samples)) >= 32760 / 32768:
        raise ValueError("clipping")
    samples = samples.mean(axis=1)
    if rate != 16000:
        divisor = math.gcd(rate, 16000)
        samples = resample_poly(samples, 16000 // divisor, rate // divisor)
    if np.max(np.abs(samples)) >= 32760 / 32768:
        raise ValueError("resampled_clipping")
    return samples


def store_audio(root, samples, row, source_info):
    import numpy as np

    if not 0 < len(samples) <= 80000:
        raise ValueError("duration_over_5s_or_empty")
    if len(samples) < 16000:
        samples = np.pad(samples, (0, 16000 - len(samples)))
    pcm = (samples * 32768).round().astype("<i2").tobytes()
    pcm_sha = digest(pcm)
    relative = f"{sample_subdirectory(row['kind'], row['label'])}/{row['source']}_{row['sample_id']}.wav"
    target = safe_path(root, relative)
    metadata_path = root / "metadata.csv"
    with metadata_file_lock(metadata_path):
        with metadata_path.open(newline="", encoding="utf-8") as f:
            existing = {r["path"]: r for r in csv.DictReader(f)}
        if relative in existing:
            old = load_provenance(root, relative)
            if old.get("pcm_sha256") != pcm_sha or old.get(
                "archive_sha256"
            ) != source_info.get("archive_sha256"):
                raise ValueError("Existing import identity conflict")
            if not target.exists() or file_digest(target) != old.get("sha256"):
                raise ValueError("Existing import file missing or changed")
            write_provenance(root, relative, {**old, **source_info, **row})
            return "existing"
        for other in existing:
            evidence = provenance_path(root, other)
            if (
                evidence.exists()
                and load_provenance(root, other).get("pcm_sha256") == pcm_sha
            ):
                raise ValueError("duplicate_audio")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ValueError("Unindexed file already exists: " + relative)
        with wave.open(str(target), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(16000)
            out.writeframes(pcm)
        provenance = {
            **source_info,
            **row,
            "path": relative,
            "sha256": file_digest(target),
            "pcm_sha256": pcm_sha,
            "sample_rate": 16000,
            "duration_s": len(samples) / 16000,
            "transform": "mono; polyphase resample 16k; right-pad to 1s; no loudness normalization",
        }
        write_provenance(root, relative, provenance)
        append_metadata(
            metadata_path,
            {
                "path": relative,
                "keyword": row["label"].replace("_", " "),
                "label": row["label"],
                "speaker_id": row["speaker_id"],
                "source": "real",
                "sample_rate": 16000,
                "duration_s": len(samples) / 16000,
                "notes": "provenance=" + provenance_path(root, relative).name,
            },
        )
    return "imported"


def load_reviewed_segments(path, con):
    """Explicit human audio review is required for crops from sentence recordings."""
    selected = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        name = safe_name(row["member"])
        source = con.execute(
            "SELECT * FROM annotations JOIN assets USING(name) WHERE name=?", (name,)
        ).fetchone()
        if source is None:
            raise ValueError("Reviewed member lacks source transcript")
        label = normalized(row["transcript"])
        kind = row.get("kind", "positive")
        if (
            kind not in ("positive", "negative")
            or label not in (KEYWORDS if kind == "positive" else HARD_NEGATIVE_CLASSES)
            or row.get("audio_reviewed") is not True
            or not row.get("reviewer_id")
        ):
            raise ValueError(
                "Positive crop requires exact target transcript and explicit audio review"
            )
        if not re.search(
            r"\b" + re.escape(label) + r"\b", normalized(source["transcript"])
        ):
            raise ValueError("Reviewed phrase absent from source transcript")
        start, end = float(row["start_s"]), float(row["end_s"])
        if (
            not math.isfinite(start)
            or not math.isfinite(end)
            or not 0 <= start < end
            or end - start > 5
        ):
            raise ValueError("Invalid crop timestamps")
        if name in selected:
            raise ValueError(
                "One reviewed crop per member per import; use separate review files for further crops"
            )
        selected[name] = {
            **dict(source),
            "kind": kind,
            "label": slugify_keyword(label),
            "transcript": row["transcript"],
            "verification": "human_audio_and_transcript_review",
            "reviewer_id": anonymous("reviewer", row["reviewer_id"]),
            "start_s": start,
            "end_s": end,
        }
    return selected


def import_archive(
    archive,
    catalog,
    root,
    languages=("fil", "ceb", "en", "und"),
    per_label=100,
    reviewed_segments=None,
    dry_run=False,
):
    import numpy as np

    if per_label < 1:
        raise ValueError("per-label must be positive")
    con = sqlite3.connect(catalog)
    con.row_factory = sqlite3.Row
    try:
        info_row = con.execute("SELECT value FROM info WHERE key='manifest'").fetchone()
        if not info_row:
            raise ValueError("Incomplete catalog; scan must finish successfully first")
        info = json.loads(info_row[0])
        if file_digest(archive) != info["archive_sha256"]:
            raise ValueError("Archive changed since catalog scan")
        if not dry_run:
            ensure_dataset_layout(root)
        notices = dict(
            con.execute("SELECT key,value FROM info WHERE key LIKE 'source_notice:%'")
        )
        if not dry_run:
            licenses = root / "provenance" / "licenses"
            licenses.mkdir(parents=True, exist_ok=True)
            (licenses / (info["source"] + ".json")).write_text(
                json.dumps({**info, "notices": notices}, indent=2), encoding="utf-8"
            )
        selected = {}
        counts = collections.Counter()
        # Sort by speaker before file name, then round-robin speakers per language/label.
        buckets = collections.defaultdict(lambda: collections.defaultdict(list))
        for r in con.execute(
            "SELECT annotations.* FROM annotations JOIN assets USING(name) ORDER BY name"
        ):
            if r["language"] not in languages:
                continue
            decision = classify(r["transcript"])
            if decision and decision[0] != "positive":
                buckets[(r["language"], *decision)][r["speaker_id"]].append(dict(r))
        for key, speakers in sorted(buckets.items()):
            limit = per_label
            while speakers and limit:
                for speaker in sorted(list(speakers)):
                    r = speakers[speaker].pop(0)
                    selected[r["name"]] = {**r, "kind": key[1], "label": key[2]}
                    limit -= 1
                    if not speakers[speaker]:
                        del speakers[speaker]
                    if not limit:
                        break
        if reviewed_segments:
            selected = load_reviewed_segments(reviewed_segments, con)
            for row in selected.values():
                if row["language"] not in languages or row["language"] not in ("en", "fil", "ceb"):
                    raise ValueError("Reviewed language is outside the selected supported languages")
                if row["kind"] == "positive" and row["language"] == "ceb":
                    raise ValueError("Cebuano positives require an approved inventory")
        official = {}
        for key, text in con.execute(
            "SELECT key,value FROM info WHERE key LIKE 'official_split:%'"
        ):
            split = "val" if "validation" in key else "test"
            for line in text.splitlines():
                member_name = safe_name(line.strip())
                if member_name in official and official[member_name] != split:
                    raise ValueError("Conflicting official split")
                official[member_name] = split
        for name, row in selected.items():
            row["official_split"] = (
                official.get(name, "train")
                if info["source"] == "speech_commands"
                else "unknown"
            )
            if info["source"] == "pld":
                stem = PurePosixPath(name).stem.rsplit(".", 1)[0]
                row["session_id"] = anonymous("pld-session", stem)
            else:
                row["session_id"] = "unknown"
        if dry_run:
            return {
                "source": info["source"],
                "dry_run": True,
                "selected": list(selected.values()),
                "selected_count": len(selected),
            }
    finally:
        con.close()
    rejected = collections.Counter()
    outcomes = collections.Counter()
    output_bytes = 0
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            name = safe_name(member.name)
            if not member.isdir() and (not member.isfile() or member.size > MAX_MEMBER):
                raise ValueError("Unsafe archive member")
            if name not in selected:
                continue
            row = selected.pop(name)
            data = tar.extractfile(member).read()
            try:
                import soundfile as sf

                original_info = sf.info(io.BytesIO(data))
                samples = normalized_audio(data)
                offset_start = 0
                if "start_s" in row:
                    offset_start = int(row["start_s"] * 16000)
                    end = int(row["end_s"] * 16000)
                    if end > len(samples):
                        raise ValueError("Crop exceeds source audio")
                    samples = samples[offset_start:end]
                chunks = [(offset_start, samples)]
                if row["label"] == "noise":
                    chunks = [
                        (i, samples[i : i + 48000])
                        for i in range(0, len(samples) - 15999, 48000)
                    ]
                for offset, chunk in chunks:
                    label = row["label"]
                    if label == "noise" and float(np.sqrt(np.mean(chunk**2))) < 0.001:
                        label = "silence"
                    sample_id = digest(
                        (
                            info["archive_sha256"]
                            + ":"
                            + name
                            + ":"
                            + str(offset)
                            + (":" + str(row["end_s"]) if "end_s" in row else "")
                        ).encode()
                    )[:24]
                    output_bytes += max(len(chunk), 16000) * 2
                    if output_bytes > MAX_OUTPUT_BYTES:
                        raise OverflowError("Selected output exceeds 2 GiB limit")
                    item = {
                        **row,
                        "label": label,
                        "source": info["source"],
                        "sample_id": sample_id,
                        "source_member_sha256": digest(data),
                        "offset_samples": offset,
                        "start_ms": offset / 16,
                        "end_ms": (offset + len(chunk)) / 16,
                        "original_sample_rate": original_info.samplerate,
                        "original_channels": original_info.channels,
                        "recording_device": "unknown",
                        "noise_condition": "unknown",
                        "speech_label": (
                            "nonspeech"
                            if label in ("noise", "silence", "music")
                            else "speech"
                        ),
                        "label_verification": (
                            "source_transcript_checked"
                            if "reviewer_id" not in row
                            else "human_audio_reviewed"
                        ),
                        "validation_state": "PASS",
                        "assigned_split": "unassigned",
                        "audio_verified": "decoded_format_duration_clipping_checked",
                    }
                    if (
                        label != "silence"
                        and float(np.sqrt(np.mean(chunk**2))) < 0.0001
                    ):
                        raise ValueError("silent_non_silence_label")
                    outcome = store_audio(root, chunk, item, info)
                    outcomes[outcome] += 1
                    counts[(row["language"], row["kind"], label)] += 1
            except (ValueError, RuntimeError) as exc:
                rejected[str(exc).split(":")[0]] += 1
    if selected:
        raise ValueError("Selected source members missing")
    return {
        "source": info["source"],
        "archive_sha256": info["archive_sha256"],
        "outcomes": dict(outcomes),
        "rejected": dict(rejected),
        "counts": [
            {"language": k[0], "kind": k[1], "label": k[2], "count": v}
            for k, v in sorted(counts.items())
        ],
    }


def download_speech_commands(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if file_digest(path) != GSC_SHA256:
            raise ValueError("Existing archive checksum mismatch")
        return
    tmp = path.with_suffix(".partial")
    with urllib.request.urlopen(
        SOURCES["speech_commands"]["url"], timeout=60
    ) as response, tmp.open("wb") as out:
        while block := response.read(1024 * 1024):
            out.write(block)
    if file_digest(tmp) != GSC_SHA256:
        raise ValueError("Downloaded archive checksum mismatch")
    tmp.replace(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["scan", "import", "download-speech-commands"])
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--catalog", type=Path)
    p.add_argument("--source", choices=SOURCES)
    p.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    p.add_argument("--per-label", type=int, default=100)
    p.add_argument("--report", type=Path)
    p.add_argument("--reviewed-segments", type=Path)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--languages",
        nargs="+",
        choices=["en", "fil", "ceb", "und"],
        default=["en", "fil", "ceb", "und"],
    )
    args = p.parse_args()
    if args.action == "download-speech-commands":
        download_speech_commands(args.archive)
        return
    if not args.catalog:
        p.error("--catalog required")
    if args.action == "scan":
        if not args.source:
            p.error("--source required")
        report = scan_archive(args.archive, args.catalog, args.source)
    else:
        report = import_archive(
            args.archive,
            args.catalog,
            args.dataset_dir,
            per_label=args.per_label,
            reviewed_segments=args.reviewed_segments,
            dry_run=args.dry_run,
            languages=args.languages,
        )
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
