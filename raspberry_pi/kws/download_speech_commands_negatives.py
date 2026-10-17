#!/usr/bin/env python3
"""Download and chunk Google Speech Commands background noise as negative training data.

Downloads the Google Speech Commands Dataset v0.02, extracts only the
``_background_noise_`` folder, and slices the long recordings into short WAV
clips suitable for openWakeWord negative-sample training.

Usage
-----
Download fresh archive::

    python raspberry_pi/kws/download_speech_commands_negatives.py

Use a pre-downloaded archive (skips download)::

    python raspberry_pi/kws/download_speech_commands_negatives.py \\
        --local-archive /path/to/speech_commands_v0.02.tar.gz

All options::

    python raspberry_pi/kws/download_speech_commands_negatives.py \\
        --output-dir dataset/audio/keyword_dataset/negative/noise \\
        --min-clips 500 \\
        --keep-archive \\
        --cleanup
"""
from __future__ import annotations

import argparse
import csv
import random
import re
import shutil
import struct
import sys
import tarfile
import tempfile
import wave
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from keyword_dataset_common import (  # noqa: E402
    DEFAULT_DATASET_DIR,
    METADATA_COLUMNS,
    append_metadata,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SPEECH_COMMANDS_URL = (
    "http://download.tensorflow.org/data/speech_commands_v0.02.tar.gz"
)
ARCHIVE_NAME = "speech_commands_v0.02.tar.gz"
BACKGROUND_NOISE_DIR = "_background_noise_"

TARGET_SAMPLE_RATE = 16_000
TARGET_CHANNELS = 1
TARGET_SAMPLE_WIDTH = 2  # bytes (16-bit PCM)

MIN_CHUNK_SECONDS = 1.0
MAX_CHUNK_SECONDS = 3.0
OVERLAP_SECONDS = 0.2
MIN_PEAK_AMPLITUDE = 0.01  # fraction of full-scale (32767)

SOURCE_LABEL = "google_speech_commands"


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _download_archive(url: str, dest: Path) -> None:
    """Stream-download *url* to *dest* with progress output."""
    if dest.exists():
        print(f"[download] Using existing archive: {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "ProjectPiDatasetDownloader/1.0"})
    print(f"[download] Fetching {url}")
    with urlopen(request) as response:
        total = int(response.headers.get("Content-Length", 0)) or None
        downloaded = 0
        chunk_bytes = 256 * 1024
        with dest.open("wb") as out:
            while True:
                block = response.read(chunk_bytes)
                if not block:
                    break
                out.write(block)
                downloaded += len(block)
                if total:
                    pct = downloaded / total * 100
                    mb_done = downloaded / 1_048_576
                    mb_total = total / 1_048_576
                    print(
                        f"\r[download] {mb_done:.1f} / {mb_total:.1f} MB"
                        f"  ({pct:.0f}%)",
                        end="",
                        flush=True,
                    )
                else:
                    print(
                        f"\r[download] {downloaded / 1_048_576:.1f} MB",
                        end="",
                        flush=True,
                    )
    print()
    print(f"[download] Saved {dest}")


# ---------------------------------------------------------------------------
# Safe extraction (background noise only)
# ---------------------------------------------------------------------------

def _extract_background_noise(archive_path: Path, extract_dir: Path) -> Path:
    """Extract only ``_background_noise_/*.wav`` from *archive_path*.

    Returns the path to the extracted ``_background_noise_`` folder.
    Raises ``ValueError`` on directory-traversal attempts.
    """
    extract_dir.mkdir(parents=True, exist_ok=True)
    dest_resolved = extract_dir.resolve()

    print(f"[extract] Scanning archive for {BACKGROUND_NOISE_DIR}/ ...")
    with tarfile.open(archive_path, "r:gz") as tf:
        members = [
            m for m in tf.getmembers()
            if m.name.startswith(BACKGROUND_NOISE_DIR + "/")
               and (m.isfile() or m.isdir())
        ]
        if not members:
            raise FileNotFoundError(
                f"Archive does not contain a '{BACKGROUND_NOISE_DIR}/' folder. "
                "Verify the archive is a valid Google Speech Commands v0.02 tarball."
            )
        print(f"[extract] Extracting {len(members)} entries ...")
        for member in members:
            member_path = (dest_resolved / member.name).resolve()
            if member_path != dest_resolved and dest_resolved not in member_path.parents:
                raise ValueError(
                    f"Unsafe path detected in archive: {member.name!r}"
                )
            if member.isdir():
                member_path.mkdir(parents=True, exist_ok=True)
                continue
            member_path.parent.mkdir(parents=True, exist_ok=True)
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            with extracted, member_path.open("wb") as out:
                shutil.copyfileobj(extracted, out)

    noise_dir = extract_dir / BACKGROUND_NOISE_DIR
    wav_count = sum(1 for _ in noise_dir.glob("*.wav"))
    if wav_count == 0:
        raise FileNotFoundError(
            f"Extraction succeeded but no WAV files found in {noise_dir}. "
            "The archive may be corrupted."
        )
    print(f"[extract] Done. Found {wav_count} WAV file(s) in {noise_dir}")
    return noise_dir


# ---------------------------------------------------------------------------
# Audio helpers (wave + numpy only — no librosa / scipy / audioop)
# ---------------------------------------------------------------------------

def _read_wav_as_float(path: Path) -> tuple[np.ndarray, int]:
    """Read a WAV file and return (float32 array in [-1, 1], sample_rate).

    Supports 8-bit, 16-bit, 24-bit, and 32-bit PCM.
    Stereo / multi-channel arrays are returned as-is (shape: [frames, channels]).
    """
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frame_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    dtype_map = {1: np.uint8, 2: np.int16, 4: np.int32}
    if sample_width == 3:
        # 24-bit PCM: unpack manually
        samples_count = n_frames * channels
        data = np.zeros(samples_count, dtype=np.int32)
        for i in range(samples_count):
            chunk = raw[i * 3: i * 3 + 3]
            val = struct.unpack("<i", chunk + (b"\x00" if chunk[2] < 0x80 else b"\xff"))[0]
            data[i] = val >> 8
        audio = data.astype(np.float32) / 2_147_483_648.0
    elif sample_width in dtype_map:
        dtype = dtype_map[sample_width]
        audio = np.frombuffer(raw, dtype=dtype).astype(np.float32)
        if sample_width == 1:
            audio = (audio - 128.0) / 128.0
        elif sample_width == 2:
            audio = audio / 32768.0
        else:  # 32-bit
            audio = audio / 2_147_483_648.0
    else:
        raise ValueError(f"Unsupported sample width: {sample_width} bytes in {path}")

    if channels > 1:
        audio = audio.reshape(-1, channels)
    return audio, frame_rate


def _to_mono(audio: np.ndarray) -> np.ndarray:
    """Average all channels into a single mono channel."""
    if audio.ndim == 1:
        return audio
    return audio.mean(axis=1)


def _resample(audio: np.ndarray, orig_rate: int, target_rate: int) -> np.ndarray:
    """Linear resample mono float32 array from *orig_rate* to *target_rate*."""
    if orig_rate == target_rate:
        return audio
    orig_len = len(audio)
    target_len = int(round(orig_len * target_rate / orig_rate))
    return np.interp(
        np.linspace(0.0, orig_len - 1, target_len, endpoint=False),
        np.arange(orig_len),
        audio,
    ).astype(np.float32)


def _to_pcm16(audio: np.ndarray) -> bytes:
    """Clip float32 audio and convert to 16-bit PCM bytes."""
    samples = np.clip(audio, -1.0, 1.0)
    pcm = (samples * 32767.0).astype(np.int16)
    return pcm.tobytes()


def _write_wav(path: Path, pcm_bytes: bytes, sample_rate: int = TARGET_SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(TARGET_CHANNELS)
        wf.setsampwidth(TARGET_SAMPLE_WIDTH)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)


def _peak_amplitude(pcm_bytes: bytes) -> float:
    """Return peak amplitude as a fraction of full-scale in [0, 1]."""
    if not pcm_bytes:
        return 0.0
    samples = np.frombuffer(pcm_bytes, dtype=np.int16)
    return float(np.max(np.abs(samples))) / 32767.0


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_chunk(path: Path) -> str | None:
    """Return an error string if the chunk is invalid, else None."""
    try:
        with wave.open(str(path), "rb") as wf:
            if wf.getframerate() != TARGET_SAMPLE_RATE:
                return f"sample_rate={wf.getframerate()}"
            if wf.getnchannels() != TARGET_CHANNELS:
                return f"channels={wf.getnchannels()}"
            if wf.getsampwidth() != TARGET_SAMPLE_WIDTH:
                return f"sample_width={wf.getsampwidth()}"
            n_frames = wf.getnframes()
            duration = n_frames / TARGET_SAMPLE_RATE
            if not (MIN_CHUNK_SECONDS <= duration <= MAX_CHUNK_SECONDS):
                return f"duration={duration:.3f}s"
            raw = wf.readframes(n_frames)
        if _peak_amplitude(raw) <= MIN_PEAK_AMPLITUDE:
            return "silent"
    except (wave.Error, EOFError) as exc:
        return f"unreadable: {exc}"
    return None


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _load_source_audio(wav_path: Path) -> tuple[np.ndarray, int]:
    """Load a WAV, convert to mono, and resample to TARGET_SAMPLE_RATE."""
    audio, orig_rate = _read_wav_as_float(wav_path)
    audio = _to_mono(audio)
    audio = _resample(audio, orig_rate, TARGET_SAMPLE_RATE)
    return audio, TARGET_SAMPLE_RATE


def _generate_chunks_from_audio(
    audio: np.ndarray,
    rng,
    overlap_samples: int,
    min_samples: int,
    max_samples: int,
) -> list[np.ndarray]:
    """Yield raw float32 chunks from *audio* with a sliding, random-length window."""
    chunks: list[np.ndarray] = []
    total = len(audio)
    pos = 0
    while pos < total - min_samples:
        available = total - pos
        chunk_len = rng.randint(min_samples, min(max_samples, available))
        chunk = audio[pos: pos + chunk_len]
        if len(chunk) >= min_samples:
            chunks.append(chunk)
        step = max(1, chunk_len - overlap_samples)
        pos += step
    return chunks


def process_noise_files(
    noise_dir: Path,
    output_dir: Path,
    metadata_path: Path,
    min_clips: int,
    seed: int,
) -> dict[str, int]:
    """Chunk background noise WAVs and save to *output_dir*.

    Returns a summary dict with ``{generated, skipped_existing, rejected_invalid}``.
    """
    rng = random.Random(seed)

    output_dir.mkdir(parents=True, exist_ok=True)

    wav_sources = sorted(noise_dir.glob("*.wav"))
    if not wav_sources:
        raise FileNotFoundError(
            f"No WAV files found in {noise_dir}. "
            "Verify extraction succeeded."
        )

    # Load all source files once (they are each a few MB)
    source_audio: dict[str, np.ndarray] = {}
    for src in wav_sources:
        print(f"[audio]   Loading {src.name} ...")
        try:
            audio, _ = _load_source_audio(src)
            source_audio[src.stem] = audio
        except Exception as exc:  # noqa: BLE001
            print(f"[audio]   WARNING: skipping {src.name}: {exc}")

    if not source_audio:
        raise FileNotFoundError("No loadable WAV files found in background noise directory.")

    # Read existing metadata to avoid duplicating rows
    existing_paths: set[str] = set()
    if metadata_path.exists():
        with metadata_path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing_paths.add(row.get("path", ""))

    # Determine per-source chunk target using global counter
    min_samples = int(MIN_CHUNK_SECONDS * TARGET_SAMPLE_RATE)
    max_samples = int(MAX_CHUNK_SECONDS * TARGET_SAMPLE_RATE)
    overlap_samples = int(OVERLAP_SECONDS * TARGET_SAMPLE_RATE)

    generated = 0
    # Seed skipped_existing from paths already recorded in metadata so the
    # while loop exits immediately when min_clips clips are already present.
    skipped_existing = len(existing_paths)
    rejected_invalid = 0

    # Per-source index counters — initialised from files already on disk so
    # subsequent runs do not reuse indices, which would attempt to skip files
    # that already exist and then correctly count them as skipped.
    index_counters: dict[str, int] = {}
    _noise_pattern = re.compile(r"^noise_(.+)_(\d{4})\.wav$")
    for existing_file in output_dir.glob("*.wav"):
        m = _noise_pattern.match(existing_file.name)
        if m:
            stem_key, idx_str = m.group(1), m.group(2)
            index_counters[stem_key] = max(
                index_counters.get(stem_key, 0), int(idx_str)
            )


    # We do multiple passes until we hit min_clips
    pass_number = 0
    while generated + skipped_existing < min_clips:
        pass_number += 1
        new_this_pass = 0
        for stem, audio in source_audio.items():
            # Jitter the starting offset on each pass so we get different chunks
            offset_jitter = rng.randint(0, max(0, int(0.5 * TARGET_SAMPLE_RATE)))
            audio_pass = audio[offset_jitter:]
            chunks = _generate_chunks_from_audio(
                audio_pass, rng, overlap_samples, min_samples, max_samples
            )
            rng.shuffle(chunks)
            for chunk in chunks:
                idx = index_counters.get(stem, 0) + 1
                index_counters[stem] = idx
                filename = f"noise_{stem}_{idx:04d}.wav"
                out_path = output_dir / filename
                # Build path relative to dataset root (metadata.csv lives at dataset root)
                try:
                    rel_path = out_path.relative_to(metadata_path.parent).as_posix()
                except ValueError:
                    rel_path = filename

                if rel_path in existing_paths or out_path.exists():
                    skipped_existing += 1
                    continue

                duration = len(chunk) / TARGET_SAMPLE_RATE
                pcm = _to_pcm16(chunk)
                _write_wav(out_path, pcm)

                # Validate immediately; reject silent/malformed chunks
                issue = _validate_chunk(out_path)
                if issue:
                    out_path.unlink(missing_ok=True)
                    rejected_invalid += 1
                    continue

                append_metadata(
                    metadata_path,
                    {
                        "path": rel_path,
                        "keyword": "negative",
                        "label": "negative",
                        "speaker_id": "",
                        "age_group": "",
                        "gender": "",
                        "distance_m": "",
                        "noise_condition": "background_noise",
                        "source": SOURCE_LABEL,
                        "sample_rate": str(TARGET_SAMPLE_RATE),
                        "duration_s": f"{duration:.2f}",
                        "notes": f"source={stem}.wav;chunk_index={idx}",
                    },
                )
                existing_paths.add(rel_path)
                generated += 1
                new_this_pass += 1

                total_accepted = generated + skipped_existing
                if total_accepted >= min_clips:
                    break
            if generated + skipped_existing >= min_clips:
                break

        if new_this_pass == 0:
            # All sources exhausted with no new chunks — stop to prevent infinite loop
            break

    return {
        "generated": generated,
        "skipped_existing": skipped_existing,
        "rejected_invalid": rejected_invalid,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download Google Speech Commands Dataset v0.02 and chunk its "
            "background noise recordings into negative training samples."
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_DATASET_DIR / "negative" / "noise",
        help="Directory where chunked WAV files are saved.",
    )
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=DEFAULT_DATASET_DIR,
        help="Root keyword dataset directory (metadata.csv lives here).",
    )
    parser.add_argument(
        "--metadata-path",
        type=Path,
        default=None,
        help="Path to metadata.csv.  Defaults to <dataset-dir>/metadata.csv.",
    )
    parser.add_argument(
        "--min-clips",
        type=int,
        default=500,
        help="Minimum number of valid negative clips to generate (default: 500).",
    )
    parser.add_argument(
        "--local-archive",
        type=Path,
        default=None,
        help="Path to an already-downloaded speech_commands_v0.02.tar.gz, skips download.",
    )
    parser.add_argument(
        "--keep-archive",
        action="store_true",
        help="Keep the downloaded archive file after extraction.",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete the temporary extraction folder after chunking completes.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=1337,
        help="Random seed for reproducible chunking (default: 1337).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    dataset_dir = args.dataset_dir.resolve()
    output_dir = args.output_dir.resolve()
    metadata_path = (
        args.metadata_path.resolve()
        if args.metadata_path
        else dataset_dir / "metadata.csv"
    )

    # ---- Obtain the archive ----
    archive_path: Path
    archive_owned = False  # True if we downloaded it and should clean it up
    if args.local_archive:
        archive_path = args.local_archive.resolve()
        if not archive_path.exists():
            print(f"ERROR: --local-archive path not found: {archive_path}", file=sys.stderr)
            return 1
        print(f"[archive] Using local archive: {archive_path}")
    else:
        archive_dir = dataset_dir.parents[2] / "dataset" / "archives"
        archive_path = archive_dir / ARCHIVE_NAME
        _download_archive(SPEECH_COMMANDS_URL, archive_path)
        archive_owned = True

    # ---- Extract only _background_noise_ ----
    extract_root = tempfile.mkdtemp(prefix="speech_commands_extract_")
    extract_path = Path(extract_root)
    try:
        noise_dir = _extract_background_noise(archive_path, extract_path)

        # ---- Remove archive unless asked to keep it ----
        if archive_owned and not args.keep_archive:
            archive_path.unlink(missing_ok=True)
            print(f"[archive] Removed archive {archive_path.name}")

        # ---- Process and chunk ----
        print(
            f"[chunk]   Generating ≥{args.min_clips} clips → {output_dir}"
        )
        summary = process_noise_files(
            noise_dir=noise_dir,
            output_dir=output_dir,
            metadata_path=metadata_path,
            min_clips=args.min_clips,
            seed=args.seed,
        )

    finally:
        if args.cleanup:
            shutil.rmtree(extract_root, ignore_errors=True)
            print(f"[cleanup] Removed extraction folder {extract_root}")

    # ---- Report ----
    total_accepted = summary["generated"] + summary["skipped_existing"]
    print(
        f"\n[result]  generated={summary['generated']}"
        f"  skipped_existing={summary['skipped_existing']}"
        f"  rejected_invalid={summary['rejected_invalid']}"
        f"  total_accepted={total_accepted}"
    )
    if total_accepted < args.min_clips:
        print(
            f"WARNING: only {total_accepted} clips available "
            f"(requested {args.min_clips}).",
            file=sys.stderr,
        )
        return 1
    print(f"[result]  ✓ Saved {total_accepted} negative clips to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
