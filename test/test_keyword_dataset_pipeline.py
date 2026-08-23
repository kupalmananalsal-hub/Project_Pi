import csv
import importlib.util
import json
import tempfile
import unittest
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = ROOT / "raspberry_pi" / "kws" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_wav(path, sample_rate=16000, duration_seconds=1.2, amplitude=1200):
    frames = int(sample_rate * duration_seconds)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        sample = int(amplitude).to_bytes(2, "little", signed=True)
        wav.writeframes(sample * frames)


def write_metadata(dataset, rows):
    metadata_path = dataset / "metadata.csv"
    with metadata_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
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
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


class KeywordDatasetPipelineTest(unittest.TestCase):
    def test_keyword_inventory_contains_all_deployed_keywords(self):
        recorder = load_script("record_keyword_dataset.py")

        self.assertEqual(
            recorder.KEYWORDS,
            [
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
            ],
        )
        self.assertEqual(recorder.slugify_keyword("help me"), "help_me")
        self.assertEqual(
            recorder.slugify_keyword("kailangan ko ng tulong"),
            "kailangan_ko_ng_tulong",
        )
        self.assertEqual(recorder.slugify_keyword("agai"), "agai")

    def test_metadata_append_writes_expected_columns(self):
        recorder = load_script("record_keyword_dataset.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata_path = Path(temp_dir) / "metadata.csv"

            recorder.append_metadata(
                metadata_path,
                {
                    "path": "positive/help/help_sp01_001.wav",
                    "keyword": "help",
                    "label": "help",
                    "speaker_id": "sp01",
                    "age_group": "adult",
                    "gender": "female",
                    "distance_m": "1",
                    "noise_condition": "quiet",
                    "source": "real",
                    "sample_rate": "16000",
                    "duration_s": "3.00",
                    "notes": "",
                },
            )

            with metadata_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(
            rows,
            [
                {
                    "path": "positive/help/help_sp01_001.wav",
                    "keyword": "help",
                    "label": "help",
                    "speaker_id": "sp01",
                    "age_group": "adult",
                    "gender": "female",
                    "distance_m": "1",
                    "noise_condition": "quiet",
                    "source": "real",
                    "sample_rate": "16000",
                    "duration_s": "3.00",
                    "notes": "",
                }
            ],
        )

    def test_validate_dataset_reports_valid_and_invalid_wavs(self):
        validator = load_script("validate_keyword_dataset.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = Path(temp_dir) / "keyword_dataset"
            valid_dir = dataset / "positive" / "help"
            invalid_dir = dataset / "positive" / "tulong"
            valid_dir.mkdir(parents=True)
            invalid_dir.mkdir(parents=True)
            write_wav(valid_dir / "help_ok.wav")
            write_wav(invalid_dir / "tulong_bad_rate.wav", sample_rate=8000)

            report = validator.validate_dataset(dataset)

        self.assertEqual(report["total_files"], 2)
        self.assertEqual(report["valid_files"], 1)
        self.assertEqual(report["invalid_files"], 1)
        self.assertEqual(report["keyword_counts"]["help"], 1)
        self.assertEqual(report["issues"][0]["issue"], "sample_rate")

    def test_training_manifest_split_is_deterministic(self):
        trainer = load_script("train_openwakeword_models.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = Path(temp_dir) / "keyword_dataset"
            keyword_dir = dataset / "positive" / "help"
            negative_dir = dataset / "negative" / "noise"
            keyword_dir.mkdir(parents=True)
            negative_dir.mkdir(parents=True)
            for idx in range(10):
                write_wav(keyword_dir / f"help_{idx:02d}.wav")
                write_wav(negative_dir / f"noise_{idx:02d}.wav")
            write_metadata(
                dataset,
                [
                    {
                        "path": f"positive/help/help_{idx:02d}.wav",
                        "keyword": "help",
                        "label": "help",
                        "speaker_id": f"sp{idx % 5:02d}",
                        "age_group": "adult",
                        "gender": "other",
                        "distance_m": "1.0",
                        "noise_condition": "quiet",
                        "source": "real",
                        "sample_rate": "16000",
                        "duration_s": "1.20",
                        "notes": "",
                    }
                    for idx in range(10)
                ],
            )

            manifest = trainer.build_split_manifest(dataset, seed=7)
            second = trainer.build_split_manifest(dataset, seed=7)

        self.assertEqual(manifest, second)
        self.assertEqual(set(manifest), {"split_seed", "speakers", "keywords"})
        self.assertEqual(set(manifest["keywords"]), {"help"})
        self.assertGreaterEqual(len(manifest["keywords"]["help"]["train"]["positive"]), 1)
        self.assertGreaterEqual(len(manifest["keywords"]["help"]["val"]["positive"]), 1)
        self.assertGreaterEqual(len(manifest["keywords"]["help"]["test"]["positive"]), 1)
        self.assertEqual(len(manifest["keywords"]["help"]["train"]["negative"]), 7)

    def test_training_manifest_assigns_each_real_speaker_to_one_split(self):
        trainer = load_script("train_openwakeword_models.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = Path(temp_dir) / "keyword_dataset"
            rows = []
            for speaker in ("sp01", "sp02", "sp03", "sp04", "sp05"):
                for keyword in ("help", "tulong"):
                    keyword_dir = dataset / "positive" / keyword
                    keyword_dir.mkdir(parents=True, exist_ok=True)
                    rel_path = f"positive/{keyword}/{keyword}_{speaker}_001.wav"
                    write_wav(dataset / rel_path)
                    rows.append(
                        {
                            "path": rel_path,
                            "keyword": keyword,
                            "label": keyword,
                            "speaker_id": speaker,
                            "age_group": "adult",
                            "gender": "other",
                            "distance_m": "1.0",
                            "noise_condition": "quiet",
                            "source": "real",
                            "sample_rate": "16000",
                            "duration_s": "1.20",
                            "notes": "",
                        }
                    )
            write_metadata(dataset, rows)

            manifest = trainer.build_split_manifest(dataset, seed=7)

        speakers = manifest["speakers"]
        train = set(speakers["train"])
        val = set(speakers["val"])
        test = set(speakers["test"])
        self.assertFalse(train & val)
        self.assertFalse(train & test)
        self.assertFalse(val & test)
        self.assertEqual(train | val | test, {"sp01", "sp02", "sp03", "sp04", "sp05"})

        file_to_split = {}
        for keyword_data in manifest["keywords"].values():
            for split_name in ("train", "val", "test"):
                for path in keyword_data[split_name]["positive"]:
                    file_to_split[path] = split_name

        for row in rows:
            expected_split = next(
                split
                for split, split_speakers in speakers.items()
                if row["speaker_id"] in split_speakers
            )
            self.assertEqual(file_to_split[row["path"]], expected_split)

    def test_augmented_samples_inherit_their_source_split(self):
        trainer = load_script("train_openwakeword_models.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = Path(temp_dir) / "keyword_dataset"
            source = "positive/help/help_sp01_001.wav"
            augmented = "augmented/positive/help/help_sp01_001_aug_01.wav"
            for rel_path in (source, augmented):
                (dataset / rel_path).parent.mkdir(parents=True, exist_ok=True)
                write_wav(dataset / rel_path)
            rows = [
                {
                    "path": source,
                    "keyword": "help",
                    "label": "help",
                    "speaker_id": "sp01",
                    "age_group": "adult",
                    "gender": "other",
                    "distance_m": "1.0",
                    "noise_condition": "quiet",
                    "source": "real",
                    "sample_rate": "16000",
                    "duration_s": "1.20",
                    "notes": "",
                },
                {
                    "path": augmented,
                    "keyword": "help",
                    "label": "help",
                    "speaker_id": "sp01",
                    "age_group": "augmented",
                    "gender": "unknown",
                    "distance_m": "unknown",
                    "noise_condition": "pitch_child",
                    "source": "augmentation",
                    "sample_rate": "16000",
                    "duration_s": "1.20",
                    "notes": f"source={source}",
                },
            ]
            for speaker in ("sp02", "sp03"):
                rel_path = f"positive/help/help_{speaker}_001.wav"
                (dataset / rel_path).parent.mkdir(parents=True, exist_ok=True)
                write_wav(dataset / rel_path)
                rows.append(
                    {
                        "path": rel_path,
                        "keyword": "help",
                        "label": "help",
                        "speaker_id": speaker,
                        "age_group": "adult",
                        "gender": "other",
                        "distance_m": "1.0",
                        "noise_condition": "quiet",
                        "source": "real",
                        "sample_rate": "16000",
                        "duration_s": "1.20",
                        "notes": "",
                    }
                )
            write_metadata(dataset, rows)

            manifest = trainer.build_split_manifest(dataset, seed=3)

        source_split = trainer.find_manifest_split(manifest, source)
        augmented_split = trainer.find_manifest_split(manifest, augmented)
        self.assertIsNotNone(source_split)
        self.assertEqual(source_split, augmented_split)

    def test_synthetic_samples_are_train_only(self):
        trainer = load_script("train_openwakeword_models.py")
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset = Path(temp_dir) / "keyword_dataset"
            rows = []
            for speaker in ("sp01", "sp02", "sp03"):
                rel_path = f"positive/help/help_{speaker}_001.wav"
                (dataset / rel_path).parent.mkdir(parents=True, exist_ok=True)
                write_wav(dataset / rel_path)
                rows.append(
                    {
                        "path": rel_path,
                        "keyword": "help",
                        "label": "help",
                        "speaker_id": speaker,
                        "age_group": "adult",
                        "gender": "other",
                        "distance_m": "1.0",
                        "noise_condition": "quiet",
                        "source": "real",
                        "sample_rate": "16000",
                        "duration_s": "1.20",
                        "notes": "",
                    }
                )
            synthetic = "positive/help/help_tts_azure_aria_001.wav"
            write_wav(dataset / synthetic)
            rows.append(
                {
                    "path": synthetic,
                    "keyword": "help",
                    "label": "help",
                    "speaker_id": "tts_azure_aria",
                    "age_group": "adult",
                    "gender": "female",
                    "distance_m": "0",
                    "noise_condition": "clean",
                    "source": "tts",
                    "sample_rate": "16000",
                    "duration_s": "1.20",
                    "notes": "",
                }
            )
            write_metadata(dataset, rows)

            manifest = trainer.build_split_manifest(dataset, seed=5)

        self.assertIn(synthetic, manifest["keywords"]["help"]["train"]["positive"])
        self.assertNotIn(synthetic, manifest["keywords"]["help"]["val"]["positive"])
        self.assertNotIn(synthetic, manifest["keywords"]["help"]["test"]["positive"])

    def test_evaluation_metrics_are_computed_from_predictions(self):
        evaluator = load_script("evaluate_keyword_models.py")
        predictions = [
            {"label": 1, "score": 0.9},
            {"label": 1, "score": 0.4},
            {"label": 0, "score": 0.8},
            {"label": 0, "score": 0.2},
        ]

        metrics = evaluator.compute_binary_metrics(
            predictions,
            threshold=0.5,
            negative_hours=0.5,
        )

        self.assertEqual(metrics["true_positives"], 1)
        self.assertEqual(metrics["false_negatives"], 1)
        self.assertEqual(metrics["false_positives"], 1)
        self.assertEqual(metrics["true_negatives"], 1)
        self.assertEqual(metrics["precision"], 0.5)
        self.assertEqual(metrics["recall"], 0.5)
        self.assertEqual(metrics["f1"], 0.5)
        self.assertEqual(metrics["false_accepts_per_hour"], 2.0)

    def test_evaluation_results_are_json_serializable(self):
        evaluator = load_script("evaluate_keyword_models.py")
        metrics = evaluator.compute_binary_metrics([], threshold=0.5)

        json.dumps(metrics)


if __name__ == "__main__":
    unittest.main()
