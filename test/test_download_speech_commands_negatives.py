"""Unit tests for download_speech_commands_negatives.py.

All tests are fully offline: a tiny synthetic tar.gz fixture is built in
``setUp()`` using the standard library ``wave`` and ``tarfile`` modules.
No network calls are made.
"""
from __future__ import annotations

import csv
import io
import importlib.util
import re
import struct
import tarfile
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _load_module(rel_path: str):
    """Import a module by relative path from the project root."""
    path = ROOT / rel_path
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_pcm16_wav(
    buf: io.BytesIO,
    sample_rate: int = 16_000,
    channels: int = 1,
    duration_s: float = 4.0,
    amplitude: int = 8_000,
) -> None:
    """Write a raw sine-ish WAV into *buf* (in-memory)."""
    n_frames = int(sample_rate * duration_s)
    total_samples = n_frames * channels
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # Alternating +amplitude / -amplitude for a simple non-silent signal.
        # Tile enough pairs to cover all required samples.
        base = np.array([amplitude, -amplitude], dtype=np.int16)
        repeats = (total_samples // 2) + 1
        samples = np.tile(base, repeats)[:total_samples]
        wf.writeframes(samples.tobytes())


def _make_fixture_tar(
    tmpdir: Path,
    entries: dict[str, bytes],
    archive_name: str = "fixture.tar.gz",
) -> Path:
    """Pack *entries* (name → bytes) into a .tar.gz and return its path."""
    archive = tmpdir / archive_name
    with tarfile.open(archive, "w:gz") as tf:
        for name, data in entries.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return archive


def _wav_bytes(
    sample_rate: int = 16_000,
    channels: int = 1,
    duration_s: float = 4.0,
    amplitude: int = 8_000,
) -> bytes:
    buf = io.BytesIO()
    _write_pcm16_wav(buf, sample_rate=sample_rate, channels=channels,
                     duration_s=duration_s, amplitude=amplitude)
    return buf.getvalue()


def _silent_wav_bytes(sample_rate: int = 16_000, duration_s: float = 2.0) -> bytes:
    """A valid WAV that is completely silent (amplitude = 0)."""
    return _wav_bytes(sample_rate=sample_rate, duration_s=duration_s, amplitude=0)


class DownloadSpeechCommandsNegativesTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.mod = _load_module(
            "raspberry_pi/kws/download_speech_commands_negatives.py"
        )
        self.trainer_mod = _load_module(
            "raspberry_pi/kws/train_openwakeword_models.py"
        )

        # Build fixture archive entries
        self.entries = {
            "_background_noise_/doing_the_dishes.wav": _wav_bytes(
                duration_s=4.0, amplitude=8_000
            ),
            "_background_noise_/running_tap.wav": _wav_bytes(
                duration_s=3.5, amplitude=6_000
            ),
            # Stereo 8 kHz — tests downmix + resample path
            "_background_noise_/stereo_8k.wav": _wav_bytes(
                sample_rate=8_000, channels=2, duration_s=3.0, amplitude=7_000
            ),
            # Silent — must be rejected
            "_background_noise_/silent.wav": _silent_wav_bytes(duration_s=2.0),
            # Non-WAV file — must be ignored
            "_background_noise_/README.md": b"This is a README.",
        }
        self.fixture_archive = _make_fixture_tar(self.tmpdir, self.entries)

        self.output_dir = self.tmpdir / "negative" / "noise"
        self.dataset_dir = self.tmpdir / "dataset"
        self.dataset_dir.mkdir(parents=True)
        self.metadata_path = self.dataset_dir / "metadata.csv"

    def tearDown(self):
        self.tmp.cleanup()

    # ------------------------------------------------------------------
    # 1. Valid WAV format (16 kHz mono 16-bit PCM)
    # ------------------------------------------------------------------
    def test_chunking_produces_valid_wav_format(self):
        extract_dir = self.tmpdir / "extract"
        noise_dir = self.mod._extract_background_noise(self.fixture_archive, extract_dir)
        self.mod.process_noise_files(
            noise_dir=noise_dir,
            output_dir=self.output_dir,
            metadata_path=self.metadata_path,
            min_clips=5,
            seed=42,
        )
        wav_files = list(self.output_dir.glob("*.wav"))
        self.assertGreater(len(wav_files), 0, "No WAV chunks were generated")
        for path in wav_files:
            with wave.open(str(path), "rb") as wf:
                self.assertEqual(wf.getframerate(), 16_000, f"{path.name}: wrong sample rate")
                self.assertEqual(wf.getnchannels(), 1, f"{path.name}: not mono")
                self.assertEqual(wf.getsampwidth(), 2, f"{path.name}: not 16-bit")

    # ------------------------------------------------------------------
    # 2. Duration between 1.0 and 3.0 seconds
    # ------------------------------------------------------------------
    def test_duration_is_always_between_1_and_3_seconds(self):
        extract_dir = self.tmpdir / "extract"
        noise_dir = self.mod._extract_background_noise(self.fixture_archive, extract_dir)
        self.mod.process_noise_files(
            noise_dir=noise_dir,
            output_dir=self.output_dir,
            metadata_path=self.metadata_path,
            min_clips=5,
            seed=42,
        )
        for path in self.output_dir.glob("*.wav"):
            with wave.open(str(path), "rb") as wf:
                duration = wf.getnframes() / wf.getframerate()
            self.assertGreaterEqual(
                duration, 1.0, f"{path.name}: duration {duration:.3f}s < 1.0s"
            )
            self.assertLessEqual(
                duration, 3.0, f"{path.name}: duration {duration:.3f}s > 3.0s"
            )

    # ------------------------------------------------------------------
    # 3. Metadata columns and values
    # ------------------------------------------------------------------
    def test_metadata_columns_and_values(self):
        extract_dir = self.tmpdir / "extract"
        noise_dir = self.mod._extract_background_noise(self.fixture_archive, extract_dir)
        self.mod.process_noise_files(
            noise_dir=noise_dir,
            output_dir=self.output_dir,
            metadata_path=self.metadata_path,
            min_clips=3,
            seed=42,
        )
        self.assertTrue(self.metadata_path.exists(), "metadata.csv not created")
        with self.metadata_path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        self.assertGreater(len(rows), 0, "No metadata rows written")
        for row in rows:
            self.assertEqual(row["keyword"], "negative")
            self.assertEqual(row["label"], "negative")
            self.assertEqual(row["source"], "google_speech_commands")
            self.assertIn("source=", row["notes"])
            self.assertIn("chunk_index=", row["notes"])
            self.assertEqual(row["sample_rate"], "16000")
            dur = float(row["duration_s"])
            self.assertGreaterEqual(dur, 1.0)
            self.assertLessEqual(dur, 3.0)

    # ------------------------------------------------------------------
    # 4. Idempotency — running twice must not duplicate files or metadata
    # ------------------------------------------------------------------
    def test_idempotency_prevents_duplicate_files_and_metadata_rows(self):
        extract_dir = self.tmpdir / "extract"
        noise_dir = self.mod._extract_background_noise(self.fixture_archive, extract_dir)

        def run():
            return self.mod.process_noise_files(
                noise_dir=noise_dir,
                output_dir=self.output_dir,
                metadata_path=self.metadata_path,
                min_clips=5,
                seed=42,
            )

        first = run()
        wav_after_first = sorted(p.name for p in self.output_dir.glob("*.wav"))
        rows_after_first: list[dict] = []
        if self.metadata_path.exists():
            with self.metadata_path.open(newline="", encoding="utf-8") as f:
                rows_after_first = list(csv.DictReader(f))

        second = run()
        wav_after_second = sorted(p.name for p in self.output_dir.glob("*.wav"))
        rows_after_second: list[dict] = []
        with self.metadata_path.open(newline="", encoding="utf-8") as f:
            rows_after_second = list(csv.DictReader(f))

        # File set must be identical
        self.assertEqual(wav_after_first, wav_after_second)
        # Metadata row count must be identical (no duplicates)
        self.assertEqual(len(rows_after_first), len(rows_after_second))
        # Second run generated nothing new
        self.assertEqual(second["generated"], 0)

    # ------------------------------------------------------------------
    # 5. Silent and invalid chunks are rejected and removed
    # ------------------------------------------------------------------
    def test_silent_chunks_are_rejected_and_not_saved(self):
        # Archive with only a silent file
        entries = {
            "_background_noise_/silent.wav": _silent_wav_bytes(duration_s=4.0),
        }
        archive = _make_fixture_tar(self.tmpdir, entries, archive_name="silent_only.tar.gz")
        extract_dir = self.tmpdir / "extract_silent"
        noise_dir = self.mod._extract_background_noise(archive, extract_dir)
        summary = self.mod.process_noise_files(
            noise_dir=noise_dir,
            output_dir=self.output_dir,
            metadata_path=self.metadata_path,
            min_clips=1,
            seed=42,
        )
        self.assertEqual(summary["generated"], 0, "Silent chunks should not be generated")
        self.assertGreater(
            summary["rejected_invalid"], 0, "Silent chunks should be counted as rejected"
        )
        # No WAV files in output
        wav_files = list(self.output_dir.glob("*.wav"))
        self.assertEqual(len(wav_files), 0, "Silent chunks must be deleted from output_dir")

    # ------------------------------------------------------------------
    # 6. Filename format matches noise_<source_stem>_<index:04d>.wav
    # ------------------------------------------------------------------
    def test_naming_convention(self):
        extract_dir = self.tmpdir / "extract"
        noise_dir = self.mod._extract_background_noise(self.fixture_archive, extract_dir)
        self.mod.process_noise_files(
            noise_dir=noise_dir,
            output_dir=self.output_dir,
            metadata_path=self.metadata_path,
            min_clips=3,
            seed=42,
        )
        pattern = re.compile(r"^noise_[a-z0-9_]+_\d{4}\.wav$")
        for path in self.output_dir.glob("*.wav"):
            self.assertRegex(
                path.name, pattern,
                f"Filename does not match naming convention: {path.name}"
            )

    # ------------------------------------------------------------------
    # 7. Missing _background_noise_ folder raises a clear error
    # ------------------------------------------------------------------
    def test_missing_noise_folder_raises_error(self):
        entries = {"some_other_folder/file.wav": _wav_bytes()}
        archive = _make_fixture_tar(self.tmpdir, entries, archive_name="no_bg.tar.gz")
        extract_dir = self.tmpdir / "extract_missing"
        with self.assertRaises(FileNotFoundError) as ctx:
            self.mod._extract_background_noise(archive, extract_dir)
        self.assertIn("_background_noise_", str(ctx.exception))

    # ------------------------------------------------------------------
    # 8. Directory traversal in archive raises ValueError
    # ------------------------------------------------------------------
    def test_directory_traversal_is_rejected(self):
        entries = {"_background_noise_/../../malicious.wav": _wav_bytes()}
        archive = _make_fixture_tar(self.tmpdir, entries, archive_name="evil.tar.gz")
        extract_dir = self.tmpdir / "extract_evil"
        with self.assertRaises(ValueError) as ctx:
            self.mod._extract_background_noise(archive, extract_dir)
        self.assertIn("Unsafe path", str(ctx.exception))

    # ------------------------------------------------------------------
    # 9. Leakage prevention — source-stem grouping in train_openwakeword_models
    # ------------------------------------------------------------------
    def test_source_stem_grouping_prevents_split_leakage(self):
        """All chunks from the same noise source must land in the same split."""
        import random

        # Simulate 6 source groups × 5 chunks = 30 negatives
        source_stems = [
            "doing_the_dishes",
            "dude_miaowing",
            "exercise_bike",
            "pink_noise",
            "running_tap",
            "white_noise",
        ]
        fake_dataset = self.tmpdir / "fake_dataset"
        neg_dir = fake_dataset / "negative" / "noise"
        neg_dir.mkdir(parents=True)

        rows = []
        for stem in source_stems:
            for idx in range(1, 6):
                fname = f"noise_{stem}_{idx:04d}.wav"
                path = neg_dir / fname
                # Write a real WAV to disk so wav_files() finds them
                with wave.open(str(path), "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16_000)
                    samples = np.ones(24_000, dtype=np.int16) * 1000
                    wf.writeframes(samples.tobytes())
                rel = f"negative/noise/{fname}"
                rows.append({
                    "path": rel,
                    "keyword": "negative",
                    "label": "negative",
                    "speaker_id": "",
                    "age_group": "",
                    "gender": "",
                    "distance_m": "",
                    "noise_condition": "background_noise",
                    "source": "google_speech_commands",
                    "sample_rate": "16000",
                    "duration_s": "1.50",
                    "notes": f"source={stem}.wav;chunk_index={idx}",
                })

        metadata_path = fake_dataset / "metadata.csv"
        with metadata_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "path", "keyword", "label", "speaker_id", "age_group", "gender",
                "distance_m", "noise_condition", "source", "sample_rate", "duration_s", "notes",
            ])
            writer.writeheader()
            writer.writerows(rows)

        # Build a metadata_by_path lookup
        metadata_by_path = {r["path"]: r for r in rows}

        # Test _negative_source_group directly
        for row in rows:
            expected_stem = row["notes"].split(";")[0].removeprefix("source=").removesuffix(".wav")
            got = self.trainer_mod._negative_source_group(row["path"], metadata_by_path)
            self.assertEqual(
                got, expected_stem,
                f"Source group mismatch for {row['path']}: expected '{expected_stem}', got '{got}'"
            )

        # Test _build_grouped_negative_split: all chunks from same stem in same split
        negatives = [r["path"] for r in rows]
        rng = random.Random(1337)
        split = self.trainer_mod._build_grouped_negative_split(
            negatives, metadata_by_path, rng
        )

        stem_to_splits: dict[str, set[str]] = {}
        for split_name, paths in split.items():
            for path in paths:
                stem = self.trainer_mod._negative_source_group(path, metadata_by_path)
                stem_to_splits.setdefault(stem, set()).add(split_name)

        for stem, split_set in stem_to_splits.items():
            self.assertEqual(
                len(split_set), 1,
                f"Source stem '{stem}' spans multiple splits: {split_set} — data leakage!"
            )

        # All partitions should be non-empty
        self.assertGreater(len(split["train"]), 0, "train split is empty")
        self.assertGreater(len(split["val"]), 0, "val split is empty")
        self.assertGreater(len(split["test"]), 0, "test split is empty")

    # ------------------------------------------------------------------
    # 10. _negative_source_group fallback: filename pattern
    # ------------------------------------------------------------------
    def test_source_group_uses_filename_pattern_when_no_metadata(self):
        """_negative_source_group falls back to the filename pattern if no notes entry."""
        path = "negative/noise/noise_running_tap_0042.wav"
        group = self.trainer_mod._negative_source_group(path, {})
        self.assertEqual(group, "running_tap")

    # ------------------------------------------------------------------
    # 11. Stereo + non-16kHz source is correctly normalised
    # ------------------------------------------------------------------
    def test_stereo_8khz_source_is_resampled_to_mono_16khz(self):
        # Load the stereo_8k.wav entry from fixture
        entries = {
            "_background_noise_/stereo_8k.wav": _wav_bytes(
                sample_rate=8_000, channels=2, duration_s=3.0, amplitude=7_000
            ),
        }
        archive = _make_fixture_tar(self.tmpdir, entries, archive_name="stereo.tar.gz")
        extract_dir = self.tmpdir / "extract_stereo"
        noise_dir = self.mod._extract_background_noise(archive, extract_dir)

        wav_path = noise_dir / "stereo_8k.wav"
        audio, rate = self.mod._load_source_audio(wav_path)

        self.assertEqual(rate, 16_000, "Sample rate should be resampled to 16000")
        self.assertEqual(audio.ndim, 1, "Audio should be mono (1D)")
        # Expected length: 3.0s * 16000 = 48000 samples (approximately)
        self.assertAlmostEqual(len(audio), 48_000, delta=200)


if __name__ == "__main__":
    unittest.main()
