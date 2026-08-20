import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KWS_MODULE = PROJECT_ROOT / "raspberry_pi" / "kws" / "kws_alert_dual.py"
KWS_ROOT = PROJECT_ROOT / "raspberry_pi" / "kws"


class FakeSession:
    def __init__(self):
        self.posts = []
        self.fail = True

    def post(self, url, json, timeout):
        del url, timeout
        self.posts.append(dict(json))
        if self.fail:
            raise RuntimeError("backend offline")
        return types.SimpleNamespace(raise_for_status=lambda: None)


def install_kws_stubs():
    stubs = {
        "numpy": types.ModuleType("numpy"),
        "pyaudio": types.ModuleType("pyaudio"),
        "requests": types.ModuleType("requests"),
        "vosk": types.ModuleType("vosk"),
        "audio_preprocessor": types.ModuleType("audio_preprocessor"),
        "noise_suppressor": types.ModuleType("noise_suppressor"),
        "wav2vec2_verifier": types.ModuleType("wav2vec2_verifier"),
    }
    stubs["numpy"].float32 = float
    stubs["numpy"].int16 = int
    stubs["numpy"].clip = lambda value, lower, upper: max(lower, min(upper, value))
    stubs["requests"].Session = FakeSession
    stubs["vosk"].KaldiRecognizer = object
    stubs["vosk"].Model = object
    stubs["audio_preprocessor"].AudioPreprocessor = object
    stubs["noise_suppressor"].DEFAULT_CONFIG_PATH = Path("noise.json")
    stubs["noise_suppressor"].NoiseSuppressionConfigStore = object
    stubs["noise_suppressor"].NoiseSuppressor = object
    stubs["wav2vec2_verifier"].Wav2Vec2Verifier = object

    previous = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    if str(KWS_ROOT) not in sys.path:
        sys.path.insert(0, str(KWS_ROOT))
    return previous


def restore_modules(previous):
    for name, module in previous.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def load_kws_module():
    previous = install_kws_stubs()
    try:
        spec = importlib.util.spec_from_file_location(
            "project_pi_kws_event_id_test",
            KWS_MODULE,
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module, previous
    except Exception:
        restore_modules(previous)
        raise


class KwsEventIdTest(unittest.TestCase):
    def make_poster(self, module, queue_path):
        poster = module.AlertPoster("http://backend/api/alerts", queue_path)
        poster.session = FakeSession()
        return poster

    def test_new_event_receives_event_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                poster = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                poster.publish("help", 0.9, "openwakeword")

                self.assertEqual(len(poster.pending), 1)
                self.assertIsInstance(poster.pending[0]["event_id"], str)
                self.assertTrue(poster.pending[0]["event_id"])
            finally:
                restore_modules(previous)

    def test_event_id_remains_unchanged_across_retries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                poster = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                poster.publish("help", 0.9, "openwakeword")
                event_id = poster.pending[0]["event_id"]
                poster.flush()

                posted_ids = [post["event_id"] for post in poster.session.posts]
                self.assertGreaterEqual(len(posted_ids), 2)
                self.assertEqual(set(posted_ids), {event_id})
                self.assertEqual(poster.pending[0]["event_id"], event_id)
            finally:
                restore_modules(previous)

    def test_serialization_and_deserialization_preserve_event_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                queue_path = Path(temp_dir) / "alerts.jsonl"
                poster = self.make_poster(module, queue_path)
                poster.publish("help", 0.9, "openwakeword")
                event_id = poster.pending[0]["event_id"]

                reloaded = self.make_poster(module, queue_path)
                self.assertEqual(reloaded.pending[0]["event_id"], event_id)
            finally:
                restore_modules(previous)

    def test_legacy_queued_event_gets_one_persistent_event_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                queue_path = Path(temp_dir) / "alerts.jsonl"
                queue_path.write_text(
                    json.dumps(
                        {
                            "event": "keyword_detected",
                            "keyword": "help",
                            "confidence": 0.9,
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )

                first_load = self.make_poster(module, queue_path)
                event_id = first_load.pending[0]["event_id"]
                second_load = self.make_poster(module, queue_path)

                self.assertTrue(event_id)
                self.assertEqual(second_load.pending[0]["event_id"], event_id)
            finally:
                restore_modules(previous)

    def test_two_independent_detections_receive_different_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                poster = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                poster.publish("help", 0.9, "openwakeword")
                poster.publish("tulong", 0.91, "openwakeword")

                ids = {event["event_id"] for event in poster.pending}
                self.assertEqual(len(ids), 2)
            finally:
                restore_modules(previous)

    def test_failed_posting_does_not_regenerate_event_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                poster = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                poster.publish("help", 0.9, "openwakeword")
                event_id = poster.pending[0]["event_id"]

                for _ in range(3):
                    poster.flush()

                self.assertEqual(poster.pending[0]["event_id"], event_id)
                self.assertEqual(
                    {post["event_id"] for post in poster.session.posts},
                    {event_id},
                )
            finally:
                restore_modules(previous)


if __name__ == "__main__":
    unittest.main()
