import asyncio
import csv
import os
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path

from test.test_backend_alert_smoke import load_backend_module, restore_modules


class FakeUploadFile:
    def __init__(self, filename, data):
        self.filename = filename
        self._data = data

    async def read(self):
        return self._data


def wav_bytes(
    sample_rate=16000,
    channels=1,
    duration_seconds=1.2,
    sample_width=2,
):
    fd, raw_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    path = Path(raw_path)
    try:
        frames = int(sample_rate * duration_seconds)
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(channels)
            handle.setsampwidth(sample_width)
            handle.setframerate(sample_rate)
            sample = (120).to_bytes(sample_width, "little", signed=True)
            handle.writeframes(sample * frames * channels)
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


class TrainingApiTest(unittest.TestCase):
    def load_module(self, temp_dir):
        module, previous = load_backend_module(temp_dir)
        module.PROJECT_ROOT = Path(temp_dir)
        module.DATASET_DIR = Path(temp_dir) / "dataset"
        module.KEYWORD_DATASET_DIR = (
            module.DATASET_DIR / "audio" / "keyword_dataset"
        )
        module.KEYWORD_METADATA_PATH = module.KEYWORD_DATASET_DIR / "metadata.csv"
        module.OPENWAKEWORD_MODEL_DIR = (
            module.DATASET_DIR / "audio" / "openwakeword_models"
        )
        module.DATASET_ARCHIVES_DIR = module.DATASET_DIR / "archives"
        return module, previous

    def cleanup(self, module, previous):
        if hasattr(module.button, "close"):
            module.button.close()
        if hasattr(module.audio, "close"):
            module.audio.close()
        module.alert_store = None
        restore_modules(previous)

    def test_upload_training_record_stores_valid_wav_and_metadata(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                result = asyncio.run(
                    module.upload_training_record(
                        file=FakeUploadFile("recording.wav", wav_bytes()),
                        keyword="help",
                        speaker_id="sp01",
                        age_group="adult",
                        gender="female",
                        distance_m=1.0,
                        noise_condition="quiet",
                    )
                )

                self.assertEqual(result["keyword"], "help")
                self.assertEqual(result["speaker_id"], "sp01")
                self.assertEqual(result["sample_rate"], 16000)
                self.assertEqual(result["channels"], 1)
                self.assertTrue(result["path"].startswith("positive/help/"))
                stored = module.KEYWORD_DATASET_DIR / result["path"]
                self.assertTrue(stored.exists())
                with module.KEYWORD_METADATA_PATH.open(newline="", encoding="utf-8") as handle:
                    rows = list(csv.DictReader(handle))
                self.assertEqual(len(rows), 1)
                self.assertEqual(
                    set(rows[0]),
                    set(module.TRAINING_METADATA_COLUMNS),
                )
                self.assertEqual(rows[0]["source"], "real")
                self.assertEqual(rows[0]["path"], result["path"])
                self.assertEqual(rows[0]["keyword"], "help")
                self.assertEqual(rows[0]["label"], "help")
                self.assertEqual(rows[0]["speaker_id"], "sp01")
                self.assertEqual(rows[0]["age_group"], "adult")
                self.assertEqual(rows[0]["gender"], "female")
                self.assertEqual(rows[0]["distance_m"], "1.0")
                self.assertEqual(rows[0]["noise_condition"], "quiet")
                self.assertEqual(rows[0]["sample_rate"], "16000")
                self.assertEqual(rows[0]["duration_s"], "1.20")
            finally:
                self.cleanup(module, previous)

    def test_upload_training_record_rejects_invalid_keyword(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                with self.assertRaises(module.HTTPException) as raised:
                    asyncio.run(
                        module.upload_training_record(
                            file=FakeUploadFile("recording.wav", wav_bytes()),
                            keyword="not-a-deployed-keyword",
                            speaker_id="sp01",
                            age_group="adult",
                            gender="female",
                            distance_m=1.0,
                            noise_condition="quiet",
                        )
                    )
                self.assertEqual(raised.exception.status_code, 400)
                self.assertFalse(module.KEYWORD_METADATA_PATH.exists())
            finally:
                self.cleanup(module, previous)

    def test_upload_training_record_rejects_invalid_metadata_values(self):
        invalid_cases = {
            "age_group": {"age_group": "ancient"},
            "gender": {"gender": "invalid"},
            "distance_below": {"distance_m": 0.49},
            "distance_above": {"distance_m": 5.01},
            "distance_nan": {"distance_m": float("nan")},
            "noise_condition": {"noise_condition": "storm"},
        }
        for case_name, override in invalid_cases.items():
            with self.subTest(case_name=case_name):
                with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
                    module, previous = self.load_module(temp_dir)
                    try:
                        values = {
                            "keyword": "help",
                            "speaker_id": "sp01",
                            "age_group": "adult",
                            "gender": "female",
                            "distance_m": 1.0,
                            "noise_condition": "quiet",
                        }
                        values.update(override)
                        with self.assertRaises(module.HTTPException) as raised:
                            asyncio.run(
                                module.upload_training_record(
                                    file=FakeUploadFile("recording.wav", wav_bytes()),
                                    **values,
                                )
                            )
                        self.assertEqual(raised.exception.status_code, 400)
                        self.assertFalse(module.KEYWORD_METADATA_PATH.exists())
                        self.assertEqual(
                            list(module.KEYWORD_DATASET_DIR.rglob("*.wav")), []
                        )
                    finally:
                        self.cleanup(module, previous)

    def test_upload_training_record_rejects_unsafe_speaker_without_file(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                with self.assertRaises(module.HTTPException) as raised:
                    asyncio.run(
                        module.upload_training_record(
                            file=FakeUploadFile("recording.wav", wav_bytes()),
                            keyword="help",
                            speaker_id="../bad",
                            age_group="adult",
                            gender="female",
                            distance_m=1.0,
                            noise_condition="quiet",
                        )
                    )
                self.assertEqual(raised.exception.status_code, 400)
                self.assertFalse(module.KEYWORD_METADATA_PATH.exists())
                self.assertEqual(
                    list(module.KEYWORD_DATASET_DIR.rglob("*.wav")),
                    [],
                )
            finally:
                self.cleanup(module, previous)

    def test_upload_training_record_rejects_corrupt_wav(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                with self.assertRaises(module.HTTPException) as raised:
                    asyncio.run(
                        module.upload_training_record(
                            file=FakeUploadFile("recording.wav", b"not a wav"),
                            keyword="help",
                            speaker_id="sp01",
                            age_group="adult",
                            gender="female",
                            distance_m=1.0,
                            noise_condition="quiet",
                        )
                    )
                self.assertEqual(raised.exception.status_code, 400)
                self.assertEqual(list(module.KEYWORD_DATASET_DIR.rglob("*.wav")), [])
            finally:
                self.cleanup(module, previous)

    def test_upload_training_record_rejects_invalid_wav_formats(self):
        invalid_cases = {
            "wrong_sample_rate": wav_bytes(sample_rate=8000),
            "stereo": wav_bytes(channels=2),
            "wrong_sample_width": wav_bytes(sample_width=1),
            "too_short": wav_bytes(duration_seconds=0.9),
            "too_long": wav_bytes(duration_seconds=5.1),
        }
        for case_name, payload in invalid_cases.items():
            with self.subTest(case_name=case_name):
                with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
                    module, previous = self.load_module(temp_dir)
                    try:
                        with self.assertRaises(module.HTTPException) as raised:
                            asyncio.run(
                                module.upload_training_record(
                                    file=FakeUploadFile("recording.wav", payload),
                                    keyword="help",
                                    speaker_id="sp01",
                                    age_group="adult",
                                    gender="female",
                                    distance_m=1.0,
                                    noise_condition="quiet",
                                )
                            )
                        self.assertEqual(raised.exception.status_code, 400)
                        self.assertEqual(
                            list(module.KEYWORD_DATASET_DIR.rglob("*.wav")), []
                        )
                        self.assertEqual(module.read_training_metadata_rows(), [])
                        self.assertEqual(
                            list((module.KEYWORD_DATASET_DIR / ".tmp").glob("*")),
                            [],
                        )
                    finally:
                        self.cleanup(module, previous)

    def test_statistics_and_recording_list_read_metadata(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                first = asyncio.run(
                    module.upload_training_record(
                        file=FakeUploadFile("help.wav", wav_bytes()),
                        keyword="help",
                        speaker_id="sp01",
                        age_group="adult",
                        gender="female",
                        distance_m=1.0,
                        noise_condition="quiet",
                    )
                )
                asyncio.run(
                    module.upload_training_record(
                        file=FakeUploadFile("tulong.wav", wav_bytes()),
                        keyword="tulong",
                        speaker_id="sp02",
                        age_group="teen",
                        gender="male",
                        distance_m=2.0,
                        noise_condition="normal",
                    )
                )

                stats = asyncio.run(module.training_statistics())
                recordings = asyncio.run(module.training_recordings())

                self.assertEqual(stats["total_recordings"], 2)
                self.assertEqual(stats["original_recordings"], 2)
                self.assertEqual(stats["augmented_recordings"], 0)
                self.assertEqual(stats["unique_real_speakers"], 2)
                self.assertEqual(stats["by_keyword"], {"help": 1, "tulong": 1})
                self.assertEqual(len(recordings["recordings"]), 2)
                self.assertEqual(recordings["recordings"][0]["id"], first["id"])
            finally:
                self.cleanup(module, previous)

    def test_delete_recording_removes_original_and_derived_augmentations(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                original = asyncio.run(
                    module.upload_training_record(
                        file=FakeUploadFile("help.wav", wav_bytes()),
                        keyword="help",
                        speaker_id="sp01",
                        age_group="adult",
                        gender="female",
                        distance_m=1.0,
                        noise_condition="quiet",
                    )
                )
                other = asyncio.run(
                    module.upload_training_record(
                        file=FakeUploadFile("help-other.wav", wav_bytes()),
                        keyword="help",
                        speaker_id="sp02",
                        age_group="adult",
                        gender="male",
                        distance_m=2.0,
                        noise_condition="normal",
                    )
                )
                augmented_relative = "positive/help/augmented/help_sp01_aug_deadbeef.wav"
                augmented_path = module.safe_dataset_path(augmented_relative)
                augmented_path.parent.mkdir(parents=True, exist_ok=True)
                augmented_path.write_bytes(wav_bytes())
                with module.TRAINING_METADATA_LOCK:
                    module.append_training_metadata(
                        module.KEYWORD_METADATA_PATH,
                        {
                            "path": augmented_relative,
                            "keyword": "help",
                            "label": "help",
                            "speaker_id": "sp01",
                            "source": "augmentation",
                            "sample_rate": "16000",
                            "duration_s": "1.20",
                            "notes": f"source={original['path']};copy=1",
                        },
                    )

                result = asyncio.run(module.delete_training_recording(original["id"]))

                self.assertEqual(result["deleted_originals"], 1)
                self.assertEqual(result["deleted_augmented"], 1)
                self.assertFalse(module.safe_dataset_path(original["path"]).exists())
                self.assertFalse(augmented_path.exists())
                self.assertTrue(module.safe_dataset_path(other["path"]).exists())
                rows = module.read_training_metadata_rows()
                self.assertEqual([row["path"] for row in rows], [other["path"]])
            finally:
                self.cleanup(module, previous)

    def test_delete_unknown_recording_returns_not_found(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                with self.assertRaises(module.HTTPException) as raised:
                    asyncio.run(module.delete_training_recording("deadbeef"))
                self.assertEqual(raised.exception.status_code, 404)
            finally:
                self.cleanup(module, previous)

    def test_job_status_returns_record_and_unknown_job_is_not_found(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                module.TRAINING_JOBS["job-test"] = {
                    "job_id": "job-test",
                    "job_type": "validation",
                    "status": "queued",
                    "progress": 0,
                    "result": None,
                    "error": None,
                }
                result = asyncio.run(module.training_job_status("job-test"))
                self.assertEqual(result["status"], "queued")

                with self.assertRaises(module.HTTPException) as raised:
                    asyncio.run(module.training_job_status("missing"))
                self.assertEqual(raised.exception.status_code, 404)
            finally:
                self.cleanup(module, previous)

    def test_heavy_jobs_run_one_at_a_time_and_capture_readable_failures(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                active = 0
                maximum_active = 0
                state_lock = threading.Lock()

                def successful_operation():
                    nonlocal active, maximum_active
                    with state_lock:
                        active += 1
                        maximum_active = max(maximum_active, active)
                    time.sleep(0.03)
                    with state_lock:
                        active -= 1
                    return {"processed": 1}

                def failing_operation():
                    raise RuntimeError("augmentation dependency unavailable")

                async def exercise_jobs():
                    first = await module.queue_training_job(
                        "validation", successful_operation
                    )
                    second = await module.queue_training_job(
                        "export", successful_operation
                    )
                    failed = await module.queue_training_job(
                        "augmentation", failing_operation
                    )
                    await asyncio.gather(*module.TRAINING_JOB_TASKS.values())
                    return first, second, failed

                first, second, failed = asyncio.run(exercise_jobs())

                self.assertEqual(maximum_active, 1)
                self.assertEqual(module.TRAINING_JOBS[first["job_id"]]["status"], "succeeded")
                self.assertEqual(module.TRAINING_JOBS[second["job_id"]]["result"], {"processed": 1})
                failure = module.TRAINING_JOBS[failed["job_id"]]
                self.assertEqual(failure["status"], "failed")
                self.assertEqual(failure["error"], "augmentation dependency unavailable")
                self.assertNotIn("Traceback", failure["error"])
            finally:
                self.cleanup(module, previous)

    def test_keywords_returns_canonical_list_with_language_tags(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                result = asyncio.run(module.training_keywords())
                self.assertEqual(result["total"], 17)
                keywords = result["keywords"]
                self.assertEqual(len(keywords), 17)
                slugs = {kw["slug"] for kw in keywords}
                self.assertIn("help", slugs)
                self.assertIn("tulong", slugs)
                self.assertIn("kailangan_ko_ng_tulong", slugs)
                languages = {kw["language"] for kw in keywords}
                self.assertEqual(languages, {"en", "fil"})
            finally:
                self.cleanup(module, previous)

    def test_validate_endpoint_starts_job(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                module.ensure_training_dataset_layout(module.KEYWORD_DATASET_DIR)

                async def _run():
                    result = await module.training_validate()
                    self.assertIn("job_id", result)
                    self.assertEqual(result["status"], "queued")
                    await asyncio.gather(*module.TRAINING_JOB_TASKS.values())
                    job = module.TRAINING_JOBS[result["job_id"]]
                    self.assertEqual(job["status"], "succeeded")
                    self.assertIn("total_files", job["result"])

                asyncio.run(_run())
            finally:
                self.cleanup(module, previous)

    def test_augment_rejects_invalid_copies_count(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                with self.assertRaises(module.HTTPException) as raised:
                    asyncio.run(module.training_augment(copies_per_file=10))
                self.assertEqual(raised.exception.status_code, 400)
            finally:
                self.cleanup(module, previous)

    def test_train_endpoint_creates_manifest(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                module.ensure_training_dataset_layout(module.KEYWORD_DATASET_DIR)
                # Need at least one WAV for the manifest
                keyword_dir = module.KEYWORD_DATASET_DIR / "positive" / "help"
                keyword_dir.mkdir(parents=True, exist_ok=True)
                for i in range(3):
                    wav_path = keyword_dir / f"help_sp{i:02d}_real_001.wav"
                    wav_path.write_bytes(wav_bytes())

                async def _run():
                    result = await module.training_train(seed=42)
                    self.assertIn("job_id", result)
                    await asyncio.gather(*module.TRAINING_JOB_TASKS.values())
                    job = module.TRAINING_JOBS[result["job_id"]]
                    self.assertEqual(job["status"], "succeeded")
                    self.assertIn("manifest_path", job["result"])

                asyncio.run(_run())
            finally:
                self.cleanup(module, previous)

    def test_deploy_rejects_empty_onnx_file(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                with self.assertRaises(module.HTTPException) as raised:
                    asyncio.run(
                        module.training_deploy(
                            onnx_file=FakeUploadFile("help.onnx", b""),
                            onnx_data_file=FakeUploadFile("help.onnx.data", b"data"),
                            keyword="help",
                        )
                    )
                self.assertEqual(raised.exception.status_code, 400)
            finally:
                self.cleanup(module, previous)

    def test_deploy_rejects_invalid_keyword(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                with self.assertRaises(module.HTTPException) as raised:
                    asyncio.run(
                        module.training_deploy(
                            onnx_file=FakeUploadFile("bad.onnx", b"model"),
                            onnx_data_file=FakeUploadFile("bad.onnx.data", b"data"),
                            keyword="not-a-keyword",
                        )
                    )
                self.assertEqual(raised.exception.status_code, 400)
            finally:
                self.cleanup(module, previous)

    def test_deploy_writes_paired_files_atomically(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                onnx_content = b"ONNX_MODEL_BINARY_DATA"
                data_content = b"ONNX_WEIGHTS_DATA"
                result = asyncio.run(
                    module.training_deploy(
                        onnx_file=FakeUploadFile("help.onnx", onnx_content),
                        onnx_data_file=FakeUploadFile("help.onnx.data", data_content),
                        keyword="help",
                    )
                )
                self.assertTrue(result["deployed"])
                self.assertEqual(result["keyword"], "help")
                self.assertEqual(result["onnx_size"], len(onnx_content))
                self.assertEqual(result["data_size"], len(data_content))

                target_onnx = module.OPENWAKEWORD_MODEL_DIR / "help.onnx"
                target_data = module.OPENWAKEWORD_MODEL_DIR / "help.onnx.data"
                self.assertTrue(target_onnx.exists())
                self.assertTrue(target_data.exists())
                self.assertEqual(target_onnx.read_bytes(), onnx_content)
                self.assertEqual(target_data.read_bytes(), data_content)
            finally:
                self.cleanup(module, previous)

    def test_deploy_creates_backup_of_existing_model(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                # Deploy initial model
                asyncio.run(
                    module.training_deploy(
                        onnx_file=FakeUploadFile("help.onnx", b"old_model"),
                        onnx_data_file=FakeUploadFile("help.onnx.data", b"old_data"),
                        keyword="help",
                    )
                )
                # Deploy replacement
                result = asyncio.run(
                    module.training_deploy(
                        onnx_file=FakeUploadFile("help.onnx", b"new_model"),
                        onnx_data_file=FakeUploadFile("help.onnx.data", b"new_data"),
                        keyword="help",
                    )
                )
                self.assertTrue(result["backed_up"])
                backup_dir = module.OPENWAKEWORD_MODEL_DIR / "backup"
                backups = list(backup_dir.glob("help_*.onnx"))
                self.assertGreaterEqual(len(backups), 1)
                # Verify the live model is the new one
                self.assertEqual(
                    (module.OPENWAKEWORD_MODEL_DIR / "help.onnx").read_bytes(),
                    b"new_model",
                )
            finally:
                self.cleanup(module, previous)

    def test_evaluate_returns_409_when_no_predictions(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                with self.assertRaises(module.HTTPException) as raised:
                    asyncio.run(module.training_evaluate())
                self.assertEqual(raised.exception.status_code, 409)
            finally:
                self.cleanup(module, previous)

    def test_evaluate_returns_metrics_from_prediction_files(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                predictions_dir = module.KEYWORD_DATASET_DIR / "predictions"
                predictions_dir.mkdir(parents=True, exist_ok=True)
                import json
                predictions = [
                    {"label": 1, "score": 0.9},
                    {"label": 0, "score": 0.1},
                ]
                (predictions_dir / "help.json").write_text(
                    json.dumps(predictions), encoding="utf-8"
                )
                result = asyncio.run(module.training_evaluate(threshold=0.5))
                self.assertIn("keywords", result)
                self.assertIn("help", result["keywords"])
                self.assertEqual(result["keywords"]["help"]["true_positives"], 1)
                self.assertEqual(result["keywords"]["help"]["true_negatives"], 1)
            finally:
                self.cleanup(module, previous)

    def test_export_rejects_fewer_than_3_speakers(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            module, previous = self.load_module(temp_dir)
            try:
                module.ensure_training_dataset_layout(module.KEYWORD_DATASET_DIR)

                async def _run():
                    # Upload with only 1 speaker
                    await module.upload_training_record(
                        file=FakeUploadFile("help.wav", wav_bytes()),
                        keyword="help",
                        speaker_id="sp01",
                        age_group="adult",
                        gender="female",
                        distance_m=1.0,
                        noise_condition="quiet",
                    )
                    result = await module.training_export()
                    self.assertIn("job_id", result)
                    await asyncio.gather(*module.TRAINING_JOB_TASKS.values())
                    job = module.TRAINING_JOBS[result["job_id"]]
                    self.assertEqual(job["status"], "failed")
                    self.assertIn("3 real speakers", job["error"])

                asyncio.run(_run())
            finally:
                self.cleanup(module, previous)


if __name__ == "__main__":
    unittest.main()
