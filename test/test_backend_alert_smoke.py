import asyncio
import gc
import importlib.util
import os
import sys
import tempfile
import types
import unittest
import warnings
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_MAIN = PROJECT_ROOT / "raspberry_pi" / "backend" / "main.py"


class FakeFastAPI:
    def __init__(self, *args, **kwargs):
        pass

    def add_middleware(self, *args, **kwargs):
        pass

    def on_event(self, *args, **kwargs):
        return lambda function: function

    def websocket(self, *args, **kwargs):
        return lambda function: function

    def get(self, *args, **kwargs):
        return lambda function: function

    def post(self, *args, **kwargs):
        return lambda function: function

    def delete(self, *args, **kwargs):
        return lambda function: function


class FakeBaseModel:
    def __init__(self, **kwargs):
        annotations = getattr(self.__class__, "__annotations__", {})
        for key in annotations:
            if hasattr(self.__class__, key):
                setattr(self, key, getattr(self.__class__, key))
        for key, value in kwargs.items():
            setattr(self, key, value)

    def dict(self):
        annotations = getattr(self.__class__, "__annotations__", {})
        return {
            key: getattr(self, key)
            for key in annotations
            if hasattr(self, key)
        }


class FakeNoiseSuppressionConfig:
    active = True
    strength = 0.5
    sensitivity = 0.5
    snowboy_sensitivity = None

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class FakeNoiseSuppressionConfigStore:
    def __init__(self, path):
        self.path = path
        self.config = FakeNoiseSuppressionConfig()

    def load(self):
        return self.config

    def save(self, config):
        self.config = config


class FakeNoiseSuppressor:
    def __init__(self, *args, **kwargs):
        pass

    def apply_config(self, config):
        pass

    def export_settings(self):
        return {
            "active": True,
            "strength": 0.5,
            "sensitivity": 0.5,
            "noise_floor_db": -90.0,
            "snr_estimate": 0.0,
            "reduction_db": 0.0,
        }


class FakeThermalConfidenceScorer:
    def __init__(self, *args, **kwargs):
        pass

    def status(self):
        return {"thermal_model_available": False}

    def analyze(self, temperatures):
        return {
            "human_detected": False,
            "confidence_boost": 0.0,
            "body_coverage": 0.0,
            "detected_part": "none",
        }


class FakeThermal:
    def __init__(self, module, payload):
        self.error = None
        self._last_payload = payload
        self._last_read_at = module.time.monotonic()

    def latest(self, max_age_seconds):
        return self._last_payload


class FakeFailingThermal:
    error = "MLX90640 unavailable"
    _last_payload = None
    _last_read_at = 0.0

    def latest(self, max_age_seconds):
        raise RuntimeError(self.error)


class FakeAlertHub:
    def __init__(self):
        self.published = []

    async def publish(self, event):
        self.published.append(dict(event))


class FakeAlertStore:
    def __init__(self):
        self.inserted = []

    def insert(self, event):
        stored = dict(event)
        stored.setdefault("id", len(self.inserted) + 1)
        self.inserted.append(stored)
        return stored


def field(default=None, **kwargs):
    return default


def install_backend_stubs():
    stubs = {
        "fastapi": types.ModuleType("fastapi"),
        "fastapi.middleware": types.ModuleType("fastapi.middleware"),
        "fastapi.middleware.cors": types.ModuleType("fastapi.middleware.cors"),
        "pydantic": types.ModuleType("pydantic"),
        "numpy": types.ModuleType("numpy"),
        "psutil": types.ModuleType("psutil"),
        "pyaudio": types.ModuleType("pyaudio"),
        "noise_suppressor": types.ModuleType("noise_suppressor"),
        "thermal_confidence": types.ModuleType("thermal_confidence"),
    }
    stubs["fastapi"].FastAPI = FakeFastAPI
    stubs["fastapi"].HTTPException = type("HTTPException", (Exception,), {})
    stubs["fastapi"].Request = type("Request", (), {})
    stubs["fastapi"].WebSocket = type("WebSocket", (), {})
    stubs["fastapi"].WebSocketDisconnect = type("WebSocketDisconnect", (Exception,), {})
    stubs["fastapi.middleware.cors"].CORSMiddleware = type("CORSMiddleware", (), {})
    stubs["pydantic"].BaseModel = FakeBaseModel
    stubs["pydantic"].Field = field
    stubs["psutil"].virtual_memory = lambda: types.SimpleNamespace(
        total=0,
        available=0,
        percent=0.0,
    )
    stubs["psutil"].disk_usage = lambda path: types.SimpleNamespace(
        total=0,
        free=0,
        percent=0.0,
    )
    stubs["noise_suppressor"].DEFAULT_CONFIG_PATH = Path("noise.json")
    stubs["noise_suppressor"].NoiseSuppressionConfig = FakeNoiseSuppressionConfig
    stubs["noise_suppressor"].NoiseSuppressionConfigStore = (
        FakeNoiseSuppressionConfigStore
    )
    stubs["noise_suppressor"].NoiseSuppressor = FakeNoiseSuppressor
    stubs["thermal_confidence"].ThermalConfidenceScorer = FakeThermalConfidenceScorer

    previous = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    return previous


def restore_modules(previous):
    for name, module in previous.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def load_backend_module(temp_dir):
    os.environ["ALERT_DB_PATH"] = str(Path(temp_dir) / "alerts.db")
    os.environ["NOISE_SUPPRESSION_CONFIG_PATH"] = str(Path(temp_dir) / "noise.json")
    previous = install_backend_stubs()
    try:
        spec = importlib.util.spec_from_file_location(
            "project_pi_backend_smoke",
            BACKEND_MAIN,
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module, previous
    except Exception:
        restore_modules(previous)
        raise


class BackendAlertSmokeTest(unittest.TestCase):
    def run_alert(self, module, payload):
        return asyncio.run(module.api_alerts(module.AlertIn(**payload)))

    def cleanup_backend(self, module, previous):
        module.alert_store = None
        restore_modules(previous)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            gc.collect()

    def prepare_backend(self, module):
        module.alert_store = FakeAlertStore()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            gc.collect()

    def test_post_alert_uses_authoritative_decision_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_backend_module(temp_dir)
            try:
                self.prepare_backend(module)
                module.alerts = FakeAlertHub()
                module.audio.latest = {"direction": "front", "snr_db": 25.0}
                module.thermal = FakeThermal(
                    module,
                    {
                        "thermal_state": "positive",
                        "human_detected": True,
                        "body_coverage": 0.20,
                        "detected_part": "torso_or_full_face",
                        "confidence_boost": 0.15,
                        "thermal_model_confidence": 0.9,
                        "temperatures": [34.0] * 768,
                    },
                )

                response = self.run_alert(
                    module,
                    {
                        "keyword": "help",
                        "confidence": 0.95,
                        "snr_db": 25.0,
                    },
                )
                event = response["event"]

                self.assertEqual(event["decision_state"], "critical")
                self.assertEqual(event["decision_reason"], "voice_confirmed_by_thermal")
                self.assertEqual(event["alert_modality"], "voice_thermal")
                self.assertEqual(event["thermal_state"], "positive")
                self.assertEqual(event["alert_level"], "full_alert")
                self.assertTrue(event["should_alert"])
                self.assertEqual(event["keyword"], "help")
                self.assertEqual(event["confidence"], 0.95)
                self.assertEqual(module.alerts.published[-1]["decision_state"], "critical")
            finally:
                self.cleanup_backend(module, previous)

    def test_suppressed_alert_is_not_rewritten_to_visual_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_backend_module(temp_dir)
            try:
                self.prepare_backend(module)
                module.alerts = FakeAlertHub()
                module.audio.latest = {"direction": "front", "snr_db": 25.0}
                module.thermal = FakeThermal(
                    module,
                    {
                        "thermal_state": "negative",
                        "human_detected": False,
                        "body_coverage": 0.0,
                        "detected_part": "none",
                        "confidence_boost": 0.0,
                        "temperatures": [24.0] * 768,
                    },
                )

                response = self.run_alert(
                    module,
                    {
                        "keyword": "help",
                        "confidence": 0.20,
                        "snr_db": 25.0,
                    },
                )
                event = response["event"]

                self.assertEqual(event["decision_state"], "suppressed")
                self.assertEqual(event["decision_reason"], "voice_below_threshold")
                self.assertEqual(event["thermal_state"], "negative")
                self.assertEqual(event["alert_level"], "none")
                self.assertFalse(event["should_alert"])
                self.assertEqual(module.alerts.published[-1]["alert_level"], "none")
            finally:
                self.cleanup_backend(module, previous)

    def test_thermal_read_failure_without_payload_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_backend_module(temp_dir)
            try:
                self.prepare_backend(module)
                module.alerts = FakeAlertHub()
                module.audio.latest = {"direction": "front", "snr_db": 25.0}
                module.thermal = FakeFailingThermal()

                response = self.run_alert(
                    module,
                    {
                        "keyword": "help",
                        "confidence": 0.75,
                        "snr_db": 25.0,
                    },
                )
                event = response["event"]

                self.assertEqual(event["decision_state"], "advisory")
                self.assertEqual(event["decision_reason"], "thermal_unavailable")
                self.assertEqual(event["thermal_state"], "unavailable")
                self.assertEqual(event["alert_level"], "visual_only")
                self.assertTrue(event["should_alert"])
            finally:
                self.cleanup_backend(module, previous)


if __name__ == "__main__":
    unittest.main()
