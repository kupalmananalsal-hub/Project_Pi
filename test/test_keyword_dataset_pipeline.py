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


class KeywordDatasetPipelineTest(unittest.TestCase):
    def test_keyword_inventory_contains_all_deployed_keywords(self):
        recorder = load_script("record_keyword_dataset.py")

        self.assertEqual(len(recorder.KEYWORDS), 17)
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

            manifest = trainer.build_split_manifest(dataset, seed=7)
            second = trainer.build_split_manifest(dataset, seed=7)

        self.assertEqual(manifest, second)
        self.assertEqual(set(manifest), {"help"})
        self.assertEqual(len(manifest["help"]["train"]["positive"]), 7)
        self.assertEqual(len(manifest["help"]["val"]["positive"]), 1)
        self.assertEqual(len(manifest["help"]["test"]["positive"]), 2)
        self.assertEqual(len(manifest["help"]["train"]["negative"]), 7)

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
