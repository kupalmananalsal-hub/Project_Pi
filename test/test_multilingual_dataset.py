import csv
import hashlib
import io
import json
import sys
import tarfile
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "raspberry_pi/kws"))
import import_keyword_datasets as ingest
from dataset_integrity import grouped_split, validated_rows, evaluate_scores
from keyword_dataset_common import ensure_dataset_layout, append_metadata


def wav_data(amplitude=1000, seconds=1.1):
    import numpy as np

    stream = io.BytesIO()
    samples = (amplitude * np.sin(np.arange(int(16000 * seconds)) * 0.07)).astype("<i2")
    with wave.open(stream, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(samples.tobytes())
    return stream.getvalue()


def archive(path, entries):
    with tarfile.open(path, "w:gz") as tar:
        for name, data in entries:
            item = tarfile.TarInfo(name)
            item.size = len(data)
            tar.addfile(item, io.BytesIO(data))


def fixture_rows():
    rows = []
    for i in range(9):
        for kind, label in [("positive", "help"), ("negative", "hello")]:
            rows.append(
                {
                    "path": f"{kind}/{label}/{i}.wav",
                    "kind": kind,
                    "label": label,
                    "language": "en",
                    "speaker_id": f"speaker-{i}",
                    "source_group": f"recording-{kind}-{i}",
                    "pcm_sha256": f"{kind}-{i}",
                    "source": "real",
                }
            )
    return rows


class DatasetIntegrationTest(unittest.TestCase):
    def test_source_parsers_do_not_infer_positive_substrings(self):
        log = 'SpeakerID = "private-name"\nclip.wav "prompts.txt" "help"\nother.wav "prompts.txt" "helpful"\n'
        rows = ingest.parse_pld("PLD/ENG/0001/session.log", log)
        self.assertEqual(rows[0][1], "en")
        self.assertNotIn("private-name", rows[0][2])
        self.assertEqual(ingest.classify(rows[0][4]), ("positive", "help"))
        self.assertEqual(ingest.classify(rows[1][4]), ("negative", "helpful"))
        self.assertIsNone(ingest.classify("I need help right now"))
        for lang, code in [("FIL", "fil"), ("CEB", "ceb")]:
            self.assertEqual(ingest.parse_pld(f"PLD/{lang}/1/s.log", log)[0][1], code)

    def test_mswc_requires_valid_and_speaker(self):
        text = "LINK,WORD,VALID,SPEAKER,GENDER\nhelp/a.opus,help,True,abc,M\nhelp/b.opus,help,False,xyz,M\nhelp/c.opus,help,True,,M\n"
        rows = ingest.parse_mswc("mswc/en/en_train.csv", text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "mswc/en/clips/help/a.opus")

    def test_bounded_incremental_pld_import_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tar = root / "source.tar.gz"
            catalog = root / "source.sqlite"
            dataset = root / "dataset"
            log = 'SpeakerID = "0001"\na.wav "prompt" "help"\nb.wav "prompt" "hello"\nc.wav "prompt" "I need help now"\n'
            archive(
                tar,
                [
                    ("PLD/ENG/0001/session.log", log.encode()),
                    ("PLD/ENG/0001/a.wav", wav_data()),
                    ("PLD/ENG/0001/b.wav", wav_data(1200)),
                    ("PLD/ENG/0001/c.wav", wav_data(1300)),
                ],
            )
            report = ingest.scan_archive(tar, catalog, "pld")
            self.assertEqual(report["audio_members"], 3)
            first = ingest.import_archive(tar, catalog, dataset, per_label=5)
            second = ingest.import_archive(tar, catalog, dataset, per_label=5)
            self.assertEqual(first["outcomes"], {"imported": 1})
            self.assertEqual(second["outcomes"], {"existing": 1})
            rows = validated_rows(dataset)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["license"], "CC-BY-NC-4.0")
            self.assertTrue((dataset / "provenance/licenses/pld.json").exists())
            with (tar).open("ab") as f:
                f.write(b"changed")
            with self.assertRaisesRegex(ValueError, "changed"):
                ingest.import_archive(tar, catalog, dataset)

    def test_reviewed_sentence_crop_requires_audio_review_and_valid_times(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tar = root / "source.tar.gz"
            catalog = root / "catalog"
            member = "PLD/ENG/0001/a.wav"
            archive(
                tar,
                [
                    (
                        "PLD/ENG/0001/session.log",
                        b'SpeakerID = "0001"\na.wav "prompt" "please help me now"\n',
                    ),
                    (member, wav_data(seconds=3)),
                ],
            )
            ingest.scan_archive(tar, catalog, "pld")
            review = root / "review.jsonl"
            row = {
                "member": member,
                "transcript": "help me",
                "start_s": 0.4,
                "end_s": 1.6,
                "audio_reviewed": False,
                "reviewer_id": "reviewer_01",
            }
            review.write_text(json.dumps(row), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "explicit audio review"):
                ingest.import_archive(
                    tar, catalog, root / "data", reviewed_segments=review
                )
            row["audio_reviewed"] = True
            review.write_text(json.dumps(row), encoding="utf-8")
            report = ingest.import_archive(
                tar, catalog, root / "data", reviewed_segments=review
            )
            self.assertEqual(report["outcomes"], {"imported": 1})
            records = validated_rows(root / "data")
            self.assertEqual(records[0]["label"], "help_me")
            self.assertEqual(
                records[0]["verification"], "human_audio_and_transcript_review"
            )
            row["end_s"] = 99
            review.write_text(json.dumps(row), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "timestamps"):
                ingest.import_archive(
                    tar, catalog, root / "data", reviewed_segments=review
                )

    def test_archive_security(self):
        for name in (
            "../escape.wav",
            "/absolute.wav",
            "C:/drive.wav",
            "a\\b.wav",
            "a/../../x",
        ):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                tar = root / "unsafe.tar.gz"
                archive(tar, [(name, b"bad")])
                with self.assertRaises(ValueError):
                    ingest.scan_archive(tar, root / "catalog", "pld")
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                tar = root / "unsafe.tar.gz"
                with tarfile.open(tar, "w:gz") as out:
                    member = tarfile.TarInfo("link")
                    member.type = kind
                    member.linkname = "../escape"
                    out.addfile(member)
                with self.assertRaises(ValueError):
                    ingest.scan_archive(tar, root / "catalog", "pld")

    def test_speech_commands_words_noise_silence_and_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tar = root / "gsc.tar.gz"
            catalog = root / "catalog"
            archive(
                tar,
                [
                    ("yes/speaker_nohash_0.wav", wav_data()),
                    ("_background_noise_/room.wav", wav_data(0, 3)),
                    ("LICENSE", b"CC BY 4.0"),
                    ("validation_list.txt", b"yes/speaker_nohash_0.wav\n"),
                ],
            )
            with patch.object(ingest, "GSC_SHA256", ingest.file_digest(tar)):
                ingest.scan_archive(tar, catalog, "speech_commands")
            report = ingest.import_archive(tar, catalog, root / "dataset")
            labels = {row["label"] for row in report["counts"]}
            self.assertEqual(labels, {"random_speech", "silence"})
            records = validated_rows(root / "dataset")
            self.assertEqual(len(records), 2)
            self.assertEqual(
                next(r for r in records if r["label"] == "random_speech")[
                    "official_split"
                ],
                "val",
            )

    def test_validation_rejects_missing_metadata_duplicate_and_wrong_labels(self):
        import numpy as np

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_dataset_layout(root)
            samples = np.sin(np.arange(16000) * 0.07).astype(np.float32) * 0.1
            info = {"archive_sha256": "test", "license": "test-only"}
            row = {
                "source": "fixture",
                "kind": "positive",
                "label": "help",
                "sample_id": "one",
                "speaker_id": "s1",
                "source_group": "one",
                "language": "en",
                "verification": "fixture",
            }
            ingest.store_audio(root, samples, row, info)
            self.assertEqual(len(validated_rows(root)), 1)
            with self.assertRaisesRegex(ValueError, "duplicate_audio"):
                ingest.store_audio(root, samples, {**row, "sample_id": "two"}, info)
            # Independently introduce a duplicate to test validation of legacy data.
            path = "positive/help/fixture_two.wav"
            (root / path).write_bytes(
                (root / "positive/help/fixture_one.wav").read_bytes()
            )
            original = ingest.load_provenance(root, "positive/help/fixture_one.wav")
            ingest.write_provenance(root, path, {**original, "path": path})
            append_metadata(
                root / "metadata.csv",
                {"path": path, "label": "help", "speaker_id": "s1"},
            )
            with self.assertRaisesRegex(ValueError, "Duplicate audio"):
                validated_rows(root)
            path = "positive/help/fixture_two.wav"
            p = ingest.load_provenance(root, path)
            p["label"] = "hello"
            ingest.write_provenance(root, path, p)
            with self.assertRaisesRegex(ValueError, "Invalid label"):
                validated_rows(root)
            ingest.provenance_path(root, path).unlink()
            with self.assertRaisesRegex(ValueError, "Missing provenance"):
                validated_rows(root)

    def test_normalization_rejects_clipping_and_unsupported_audio(self):
        with self.assertRaises(ValueError):
            ingest.normalized_audio(wav_data(32767))
        with self.assertRaises(Exception):
            ingest.normalized_audio(b"not audio")

    def test_splits_are_globally_disjoint_and_augmentation_inherits(self):
        rows = fixture_rows()
        original = rows[0]
        rows.append(
            {
                **original,
                "path": "augmented/positive/help/aug.wav",
                "source": "augmentation",
                "parent_path": original["path"],
                "pcm_sha256": "aug",
            }
        )
        result = grouped_split(rows, 42)
        self.assertEqual(result, grouped_split(rows, 42))
        self.assertEqual(
            result["path_splits"][rows[-1]["path"]],
            result["path_splits"][original["path"]],
        )
        for field in ("speaker_id", "source_group"):
            for identity in {r[field] for r in rows}:
                self.assertEqual(
                    len(
                        {
                            result["path_splits"][r["path"]]
                            for r in rows
                            if r[field] == identity
                        }
                    ),
                    1,
                )
        self.assertEqual(set(result["path_splits"].values()), {"train", "val", "test"})

    def test_rejects_insufficient_or_linked_coverage(self):
        rows = fixture_rows()
        for row in rows:
            row["source_group"] = "one-connected-session"
        with self.assertRaisesRegex(ValueError, "Insufficient"):
            grouped_split(rows)
        rows = fixture_rows()
        rows[0]["source"] = "augmentation"
        rows[0]["parent_path"] = "missing"
        with self.assertRaisesRegex(ValueError, "Unknown augmentation"):
            grouped_split(rows)

    def test_evaluation_language_counts_and_missing_predictions(self):
        rows = [
            {"path": "a", "kind": "positive", "language": "fil"},
            {"path": "b", "kind": "negative", "language": "fil"},
            {"path": "c", "kind": "positive", "language": "ceb"},
        ]
        result = evaluate_scores(rows, {"a": 0.9, "b": 0.8, "c": 0.1})
        self.assertEqual(result["fil"]["tp"], 1)
        self.assertEqual(result["fil"]["fp"], 1)
        self.assertEqual(result["ceb"]["fn"], 1)
        with self.assertRaises(ValueError):
            evaluate_scores(rows, {"a": 0.1})

    def test_positive_availability_and_missing_recordings(self):
        from dataset_readiness import audit_positives, audit_records

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(audit_positives(root)["state"], "SOURCE_UNAVAILABLE")
            ensure_dataset_layout(root)
            self.assertEqual(audit_positives(root)["state"], "EMPTY")
            (root / "positive/help/sample.wav").write_bytes(wav_data())
            self.assertEqual(audit_positives(root)["wav_files"], 1)
            records, issues, _ = audit_records(root)
            self.assertFalse(records)
            self.assertIn("missing_metadata", [x["issue"] for x in issues])
            append_metadata(
                root / "metadata.csv",
                {"path": "positive/help/missing.wav", "label": "help"},
            )
            self.assertTrue(
                any(x["path"].endswith("missing.wav") for x in audit_records(root)[1])
            )

    def test_unknown_speaker_and_physical_holdout_rejected(self):
        rows = fixture_rows()
        rows[0]["speaker_id"] = "unknown"
        with self.assertRaisesRegex(ValueError, "Unknown speaker"):
            grouped_split(rows)
        rows = fixture_rows()
        rows[0]["path"] = "physical_holdout/help.wav"
        with self.assertRaisesRegex(ValueError, "Physical holdout"):
            grouped_split(rows)

    def test_official_split_conflict_and_source_chunks(self):
        rows = fixture_rows()
        rows[0]["official_split"] = "test"
        result = grouped_split(rows)
        self.assertEqual(result["path_splits"][rows[0]["path"]], "test")
        rows[1]["official_split"] = "train"
        with self.assertRaisesRegex(ValueError, "Official split conflicts"):
            grouped_split(rows)
        rows = fixture_rows()
        rows[2]["source_group"] = rows[0]["source_group"]
        result = grouped_split(rows)
        self.assertEqual(
            result["path_splits"][rows[0]["path"]],
            result["path_splits"][rows[2]["path"]],
        )

    def test_near_duplicate_gain_variation(self):
        from dataset_readiness import near_duplicate_pairs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.wav").write_bytes(wav_data(1000))
            (root / "b.wav").write_bytes(wav_data(2000))
            pairs = near_duplicate_pairs(root, [{"path": "a.wav"}, {"path": "b.wav"}])
            self.assertEqual(len(pairs), 1)
            self.assertEqual(pairs[0]["state"], "REVIEW_REQUIRED")

    def test_dry_run_missing_target_and_no_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.tar.gz"
            archive(
                source,
                [
                    (
                        "mswc/en/en_train.csv",
                        b"LINK,WORD,VALID,SPEAKER\ncat/a.opus,cat,True,s1\n",
                    ),
                    ("mswc/en/clips/cat/a.opus", b"fixture"),
                ],
            )
            ingest.scan_archive(source, root / "catalog", "mswc")
            with patch(
                "subprocess.run",
                side_effect=AssertionError("No training subprocess permitted"),
            ):
                result = ingest.import_archive(
                    source, root / "catalog", root / "data", dry_run=True
                )
            self.assertEqual(result["selected_count"], 1)
            self.assertNotIn("help", {r["label"] for r in result["selected"]})
            self.assertFalse((root / "data").exists())

    def test_private_outputs_are_git_ignored(self):
        import subprocess

        paths = [
            "dataset/audio/keyword_dataset/positive/help/private.wav",
            "dataset/audio/keyword_dataset/metadata.csv",
            "dataset/audio/keyword_dataset/provenance/private.json",
            "dataset/audio/keyword_dataset/reports/sample_inventory.csv",
            "dataset/archives/source.tar.gz",
        ]
        result = subprocess.run(
            ["git", "check-ignore", *paths],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(set(result.stdout.splitlines()), set(paths))

    def test_restricted_exports(self):
        from dataset_integrity import validate_export

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, "third-party"):
                validate_export([{"source": "pld"}], root, root / "archives")
            with self.assertRaisesRegex(ValueError, "destination"):
                validate_export([], root, root.parent / "outside")
            validate_export([{"source": "mswc"}], root, root / "archives")

    def test_reviewed_hard_negative_crop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.tar.gz"
            member = "PLD/ENG/1/a.wav"
            archive(
                source,
                [
                    (
                        "PLD/ENG/1/s.log",
                        b'SpeakerID = "one"\na.wav "prompt" "say hello today"\n',
                    ),
                    (member, wav_data(seconds=3)),
                ],
            )
            ingest.scan_archive(source, root / "catalog", "pld")
            review = root / "review.jsonl"
            review.write_text(
                json.dumps(
                    {
                        "member": member,
                        "transcript": "hello",
                        "kind": "negative",
                        "audio_reviewed": True,
                        "reviewer_id": "r1",
                        "start_s": 0.2,
                        "end_s": 1.5,
                    }
                )
            )
            ingest.import_archive(
                source, root / "catalog", root / "data", reviewed_segments=review
            )
            rows = validated_rows(root / "data")
            self.assertTrue(rows[0]["path"].startswith("negative/hard_negative/hello/"))
            self.assertEqual(
                rows[0]["verification"], "human_audio_and_transcript_review"
            )


if __name__ == "__main__":
    unittest.main()
