#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import wave

import numpy as np
import psutil
import pyaudio
from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

CURRENT_DIR = Path(__file__).resolve().parent
RASPBERRY_PI_ROOT = CURRENT_DIR.parent
PROJECT_ROOT = RASPBERRY_PI_ROOT.parent
for extra_path in (
    RASPBERRY_PI_ROOT,
    RASPBERRY_PI_ROOT / "kws",
    RASPBERRY_PI_ROOT / "thermal",
):
    extra_as_str = str(extra_path)
    if extra_as_str not in sys.path:
        sys.path.insert(0, extra_as_str)

from alert_decision import AlertDecisionEngine
from noise_suppressor import (
    DEFAULT_CONFIG_PATH,
    NoiseSuppressionConfig,
    NoiseSuppressionConfigStore,
    NoiseSuppressor,
)
from thermal_confidence import ThermalConfidenceScorer
from keyword_dataset_common import (
    KEYWORDS as TRAINING_KEYWORDS,
    METADATA_COLUMNS as TRAINING_METADATA_COLUMNS,
    append_metadata as append_training_metadata,
    ensure_dataset_layout as ensure_training_dataset_layout,
    slugify_keyword,
)

try:
    import adafruit_mlx90640
    import board
    import busio
except Exception:  # pragma: no cover - hardware import
    adafruit_mlx90640 = None
    board = None
    busio = None

try:
    import spidev
except Exception:  # pragma: no cover - hardware import
    spidev = None

try:
    from gpiozero import DigitalInputDevice
except Exception:  # pragma: no cover - hardware import
    DigitalInputDevice = None


APP_START = time.time()
MLX_ADDRS = [0x10, 0x33]
DEFAULT_AUDIO_SAMPLE_RATE = 16000
VOICE_SAMPLES_DIR = Path.home() / "voice_samples"
AUDIO_STATUS_PATH = Path(os.getenv("PROJECT_PI_AUDIO_STATUS_PATH", "/tmp/project_pi_audio_status.json"))
ALERT_DB_PATH = Path(os.getenv("ALERT_DB_PATH", str(CURRENT_DIR / "alerts.db")))
DATASET_DIR = Path(os.getenv("DATASET_DIR", str(PROJECT_ROOT / "dataset"))).expanduser()
KEYWORD_DATASET_DIR = DATASET_DIR / "audio" / "keyword_dataset"
KEYWORD_METADATA_PATH = KEYWORD_DATASET_DIR / "metadata.csv"
OPENWAKEWORD_MODEL_DIR = DATASET_DIR / "audio" / "openwakeword_models"
DATASET_ARCHIVES_DIR = DATASET_DIR / "archives"
API_TOKEN = os.getenv("PROJECT_PI_API_TOKEN", "project-pi-local-token")
MAX_TRAINING_WAV_UPLOAD_BYTES = int(os.getenv("TRAINING_WAV_MAX_BYTES", str(8 * 1024 * 1024)))
MAX_ONNX_UPLOAD_BYTES = int(os.getenv("TRAINING_ONNX_MAX_BYTES", str(128 * 1024 * 1024)))
MAX_ONNX_DATA_UPLOAD_BYTES = int(
    os.getenv("TRAINING_ONNX_DATA_MAX_BYTES", str(256 * 1024 * 1024))
)
TRAINING_METADATA_LOCK = threading.Lock()
TRAINING_JOBS: dict[str, dict[str, Any]] = {}
TRAINING_JOB_TASKS: dict[str, asyncio.Task[Any]] = {}
TRAINING_JOBS_LOCK = asyncio.Lock()
TRAINING_HEAVY_JOB_LOCK = asyncio.Lock()
TRAINING_AGE_GROUPS = {"child", "teen", "adult", "elder"}
TRAINING_GENDERS = {"male", "female", "other"}
TRAINING_NOISE_CONDITIONS = {"quiet", "normal", "noisy"}
SPEAKER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

app = FastAPI(title="Project Pi Thermal Backend", version="1.0.0")
cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "PROJECT_PI_CORS_ORIGINS",
        "http://localhost,http://127.0.0.1",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LedRequest(BaseModel):
    led: int = Field(ge=0, le=2)
    r: int = Field(ge=0, le=255)
    g: int = Field(ge=0, le=255)
    b: int = Field(ge=0, le=255)
    brightness: float = Field(default=1.0, ge=0.0, le=1.0)


class AlertIn(BaseModel):
    event_id: str | None = None
    event: str = "keyword_detected"
    keyword: str
    confidence: float = 0.0
    direction: str = "center"
    direction_angle: float | None = None
    direction_confidence: float | None = None
    distance_estimate_m: float | None = None
    distance_m: float | None = None
    phase: str | None = None
    source: str | None = None
    timestamp: str | None = None
    noise_level_db: float | None = None
    signal_level_db: float | None = None
    snr_db: float | None = None
    noise_reduction_db: float | None = None
    noise_suppression_active: bool | None = None
    snowboy_sensitivity: float | None = None
    final_confidence: float | None = None
    alert_level: str | None = None
    human_detected: bool | None = None
    body_coverage: float | None = None
    detected_part: str | None = None
    thermal_confidence_boost: float | None = None
    decision_factors: dict[str, Any] | None = None


class RefreshRequest(BaseModel):
    git_pull: bool = False
    restart_backend: bool = False


class NoiseSuppressionRequest(BaseModel):
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    active: bool = True
    snowboy_sensitivity: float | None = Field(default=None, ge=0.0, le=1.0)


class VoiceSampleResponse(BaseModel):
    sample_id: str
    filename: str
    duration_seconds: float
    sample_rate: int
    channels: int
    keyword: str
    timestamp: str
    message: str


class AlertStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self.lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    keyword TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    direction TEXT,
                    human_detected INTEGER DEFAULT 0,
                    source TEXT DEFAULT 'openwakeword'
                )
                """
            )

    def insert(self, event: dict[str, Any]) -> dict[str, Any]:
        stored = dict(event)
        stored["timestamp"] = (
            str(stored.get("timestamp") or datetime.now(timezone.utc).isoformat())
        )
        stored["keyword"] = str(stored.get("keyword") or "unknown")
        stored["confidence"] = _as_float(stored.get("confidence"), 0.0)
        stored["direction"] = str(stored.get("direction") or "front")
        stored["human_detected"] = bool(stored.get("human_detected", False))
        stored["source"] = str(stored.get("source") or "openwakeword")

        with self.lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO alerts (
                    timestamp,
                    keyword,
                    confidence,
                    direction,
                    human_detected,
                    source
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    stored["timestamp"],
                    stored["keyword"],
                    stored["confidence"],
                    stored["direction"],
                    1 if stored["human_detected"] else 0,
                    stored["source"],
                ),
            )
            stored["id"] = cursor.lastrowid
        return stored

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        with self.lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, timestamp, keyword, confidence, direction, human_detected, source
                FROM alerts
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

        return [
            {
                "id": row["id"],
                "event": "keyword_detected",
                "timestamp": row["timestamp"],
                "keyword": row["keyword"],
                "confidence": row["confidence"],
                "direction": row["direction"] or "front",
                "human_detected": bool(row["human_detected"]),
                "source": row["source"] or "openwakeword",
            }
            for row in rows
        ]

    def clear(self) -> int:
        with self.lock:
            with self._connect() as connection:
                row = connection.execute("SELECT COUNT(*) AS count FROM alerts").fetchone()
                deleted = int(row["count"] if row else 0)
                connection.execute("DELETE FROM alerts")
                connection.commit()

            with self._connect() as connection:
                connection.execute("VACUUM")
            return deleted


class AlertHub:
    def __init__(self):
        self.clients: set[asyncio.Queue[dict[str, Any]]] = set()

    async def publish(self, event: dict[str, Any]):
        if not event.get("timestamp"):
            event["timestamp"] = datetime.now(timezone.utc).isoformat()
        for client_queue in list(self.clients):
            await client_queue.put(event)

    async def connect(self):
        client_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self.clients.add(client_queue)
        return client_queue

    def disconnect(self, client_queue):
        self.clients.discard(client_queue)


class AlertIdempotencyRegistry:
    """
    Bounded in-memory idempotency cache for KWS alert submissions.

    This prevents HTTP retries from being treated as new distress events while
    the backend process remains alive. Persistence across backend restarts is
    intentionally deferred until the future database-migration phase.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float,
        max_entries: int,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.ttl_seconds = float(ttl_seconds)
        self.max_entries = max(1, int(max_entries))
        self.clock = clock or time.monotonic
        self._in_flight: dict[str, dict[str, Any]] = {}
        self._completed: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = asyncio.Lock()
        self._in_flight_warning_threshold = max(128, self.max_entries * 2)

    async def claim(self, event_id: str, fingerprint: str) -> dict[str, Any]:
        async with self._lock:
            self._prune_completed_locked()

            in_flight = self._in_flight.get(event_id)
            if in_flight is not None:
                if in_flight["fingerprint"] != fingerprint:
                    return {"status": "conflict"}
                return {"status": "in_flight", "future": in_flight["future"]}

            completed = self._completed.get(event_id)
            if completed is not None:
                self._completed.move_to_end(event_id)
                if completed["fingerprint"] != fingerprint:
                    return {"status": "conflict"}
                return {
                    "status": "duplicate",
                    "response": dict(completed["response"]),
                }

            loop = asyncio.get_running_loop()
            future: asyncio.Future[dict[str, Any]] = loop.create_future()
            self._in_flight[event_id] = {
                "fingerprint": fingerprint,
                "started_at": self.clock(),
                "future": future,
            }
            if len(self._in_flight) > self._in_flight_warning_threshold:
                print(
                    "Alert idempotency warning: unusually many in-flight "
                    f"events ({len(self._in_flight)})",
                    file=sys.stderr,
                    flush=True,
                )
            return {"status": "claimed", "future": future}

    async def complete(self, event_id: str, response: dict[str, Any]) -> None:
        async with self._lock:
            in_flight = self._in_flight.pop(event_id, None)
            if in_flight is None:
                return
            cached_response = dict(response)
            cached_response["duplicate_event"] = False
            self._completed[event_id] = {
                "fingerprint": in_flight["fingerprint"],
                "created_at": self.clock(),
                "response": cached_response,
            }
            future = in_flight["future"]
            if not future.done():
                future.set_result(cached_response)
            self._completed.move_to_end(event_id)
            self._trim_completed_capacity_locked()

    async def fail(self, event_id: str, exc: BaseException) -> None:
        async with self._lock:
            in_flight = self._in_flight.pop(event_id, None)
            if in_flight is None:
                return
            future = in_flight["future"]
            if not future.done():
                future.set_exception(exc)

    def snapshot_size(self) -> int:
        return len(self._completed)

    def in_flight_size(self) -> int:
        return len(self._in_flight)

    def _prune_completed_locked(self) -> None:
        now = self.clock()
        expired = [
            event_id
            for event_id, entry in self._completed.items()
            if now - float(entry["created_at"]) > self.ttl_seconds
        ]
        for event_id in expired:
            self._completed.pop(event_id)

    def _trim_completed_capacity_locked(self) -> None:
        while len(self._completed) > self.max_entries:
            self._completed.popitem(last=False)


alert_store = AlertStore(ALERT_DB_PATH)
alerts = AlertHub()
decision_engine = AlertDecisionEngine()
alert_idempotency = AlertIdempotencyRegistry(
    ttl_seconds=decision_engine.policy.idempotency_ttl_seconds,
    max_entries=decision_engine.policy.idempotency_max_entries,
)
noise_config_store = NoiseSuppressionConfigStore(
    Path(os.getenv("NOISE_SUPPRESSION_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))
)


def estimate_direction(left_chunk, right_chunk, sample_rate=DEFAULT_AUDIO_SAMPLE_RATE):
    left = np.asarray(left_chunk, dtype=np.float32)
    right = np.asarray(right_chunk, dtype=np.float32)
    if left.size < 2 or right.size < 2:
        return "center"

    left -= float(np.mean(left))
    right -= float(np.mean(right))
    if float(np.max(np.abs(left))) < 1 or float(np.max(np.abs(right))) < 1:
        return "center"

    correlation = np.correlate(left, right, mode="full")
    lag = int(np.argmax(correlation) - (len(left) - 1))
    time_diff = lag / sample_rate
    threshold = float(os.getenv("DIRECTION_THRESHOLD_SECONDS", "0.00003"))

    if time_diff > threshold:
        return "right"
    if time_diff < -threshold:
        return "left"
    return "center"


def calculate_direction(left_rms: float, right_rms: float):
    if left_rms <= 0 and right_rms <= 0:
        return "unknown", 0, 0.0, None

    diff = right_rms - left_rms
    total = left_rms + right_rms
    if total <= 0:
        return "front", 0, 0.0, None

    ratio = diff / total
    if -0.1 <= ratio <= 0.1:
        direction = "front"
        angle = 0
    elif 0.1 < ratio <= 0.3:
        direction = "front-right"
        angle = 45
    elif 0.3 < ratio <= 0.6:
        direction = "right"
        angle = 90
    elif ratio > 0.6:
        direction = "back-right"
        angle = 135
    elif -0.3 <= ratio < -0.1:
        direction = "front-left"
        angle = -45
    elif -0.6 <= ratio < -0.3:
        direction = "left"
        angle = -90
    else:
        direction = "back-left"
        angle = -135

    avg_level = (left_rms + right_rms) / 2
    distance_m = max(0.5, min(10.0, 1.0 / (avg_level + 0.01) * 0.05))
    confidence = min(1.0, abs(ratio) * 2)
    return direction, angle, confidence, distance_m


def estimate_pitch_hz(samples, sample_rate=DEFAULT_AUDIO_SAMPLE_RATE):
    signal = np.asarray(samples, dtype=np.float32)
    if signal.size < 128:
        return None
    signal = signal - float(np.mean(signal))
    if float(np.max(np.abs(signal))) < 150:
        return None

    windowed = signal * np.hanning(signal.size)
    spectrum = np.abs(np.fft.rfft(windowed))
    frequencies = np.fft.rfftfreq(signal.size, d=1.0 / sample_rate)
    mask = (frequencies >= 85.0) & (frequencies <= 400.0)
    if not np.any(mask):
        return None
    band = spectrum[mask]
    if band.size == 0 or float(np.max(band)) <= 1e-6:
        return None
    index = int(np.argmax(band))
    return float(frequencies[mask][index])


class ThermalCamera:
    def __init__(self):
        self.mlx = None
        self.address = None
        self.frame = [0.0] * 768
        self.error = None
        self._lock = threading.Lock()
        self._last_payload: dict[str, Any] | None = None
        self._last_read_at = 0.0
        self._confidence_scorer = ThermalConfidenceScorer(
            width=32,
            height=24,
            temporal_required=True,
        )

    def init(self):
        if self.mlx is not None:
            return
        if board is None or busio is None or adafruit_mlx90640 is None:
            self.error = "Adafruit Blinka/MLX90640 libraries are unavailable"
            return

        i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
        last_error = None
        for address in MLX_ADDRS:
            try:
                self.mlx = adafruit_mlx90640.MLX90640(i2c, address=address)
                self.mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_4_HZ
                self.address = address
                self.error = None
                return
            except Exception as exc:  # pragma: no cover - hardware path
                last_error = exc

        self.error = f"MLX90640 not found at {[hex(a) for a in MLX_ADDRS]}: {last_error}"

    def read(self) -> dict[str, Any]:
        self.init()
        if self.mlx is None:
            raise RuntimeError(self.error or "MLX90640 unavailable")

        with self._lock:
            while True:
                try:
                    self.mlx.getFrame(self.frame)
                    break
                except ValueError:
                    time.sleep(0.02)

            payload: dict[str, Any] = {
                "width": 32,
                "height": 24,
                "temperatures": [round(float(value), 2) for value in self.frame],
                "address": f"0x{self.address:02x}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            payload.update(self._confidence_payload(payload["temperatures"]))
            self._last_payload = payload
            self._last_read_at = time.monotonic()
            return payload

    def latest(self, max_age_seconds: float = 1.0) -> dict[str, Any]:
        if self._last_payload is not None and (time.monotonic() - self._last_read_at) <= max_age_seconds:
            return self._last_payload
        return self.read()

    def model_status(self) -> dict[str, object]:
        if hasattr(self._confidence_scorer, "status"):
            return self._confidence_scorer.status()
        return {
            "thermal_model_available": False,
            "thermal_model_error": "status unavailable",
            "thermal_model_path": None,
            "thermal_model_threshold": None,
        }

    def _confidence_payload(self, temperatures: list[float]) -> dict[str, Any]:
        try:
            return self._confidence_scorer.analyze(temperatures)
        except Exception as exc:
            return {
                "human_detected": False,
                "body_coverage": 0.0,
                "detected_part": "analysis_error",
                "confidence_boost": 0.0,
                "human_temp_avg": None,
                "human_temp_min": None,
                "human_temp_max": None,
                "human_clusters": [],
                "dominant_cluster": None,
                "analysis_error": str(exc),
            }


thermal = ThermalCamera()


class AudioMonitor:
    def __init__(self):
        self.pa = None
        self.stream = None
        self.latest = {
            "rms": [0.0, 0.0],
            "direction": "center",
            "noise_level_db": -90.0,
            "signal_level_db": -90.0,
            "snr_db": 0.0,
            "noise_reduction_db": 0.0,
            "noise_suppression_active": False,
            "suppression_strength": 0.5,
            "suppression_sensitivity": 0.5,
            "estimated_pitch_hz": None,
            "timestamp": None,
        }
        self.device_index = None
        self.config_store = noise_config_store
        self._config = self.config_store.load()
        self.noise_suppressor = NoiseSuppressor(
            sample_rate=DEFAULT_AUDIO_SAMPLE_RATE,
            noise_reduction_strength=float(os.getenv("NOISE_SUPPRESSOR_STRENGTH", "0.70")),
            sensitivity=float(os.getenv("NOISE_SUPPRESSOR_SENSITIVITY", "0.50")),
            active=True,
            noise_profile_seconds=float(os.getenv("NOISE_PROFILE_SECONDS", "2.0")),
            profile_update_rate=float(os.getenv("NOISE_PROFILE_ADAPT_RATE", "0.05")),
        )
        self.apply_noise_settings(self._config)

    def _find_device(self):
        fallback = None
        for index in range(self.pa.get_device_count()):
            info = self.pa.get_device_info_by_index(index)
            if int(info.get("maxInputChannels", 0)) <= 0:
                continue
            name = str(info.get("name", "")).lower()
            if "seeed" in name or "respeaker" in name:
                return index
            if fallback is None:
                fallback = index
        if fallback is None:
            raise RuntimeError("No audio input device found")
        return fallback

    def start(self):
        if self.stream is not None:
            return
        self.pa = pyaudio.PyAudio()
        self.device_index = self._find_device()
        self.stream = self.pa.open(
            rate=DEFAULT_AUDIO_SAMPLE_RATE,
            channels=2,
            format=pyaudio.paInt16,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=800,
        )

    def apply_noise_settings(self, config: NoiseSuppressionConfig) -> None:
        self._config = config
        self.noise_suppressor.apply_config(config)

    def get_noise_settings(self) -> dict[str, Any]:
        payload = self.noise_suppressor.export_settings()
        payload["snowboy_sensitivity"] = self._config.snowboy_sensitivity
        return payload

    def read(self) -> dict[str, Any]:
        try:
            self.start()
            data = self.stream.read(800, exception_on_overflow=False)
        except Exception:
            shared = read_shared_audio_status()
            if shared is not None:
                self.latest = shared
                return shared
            raise

        samples = np.frombuffer(data, dtype=np.int16)
        left = samples[0::2].astype(np.float32)
        right = samples[1::2].astype(np.float32)
        mono = np.mean(np.column_stack((left, right)), axis=1).astype(np.int16)

        if not self.noise_suppressor.profile_ready:
            self.noise_suppressor.capture_noise_profile(mono)
        else:
            latest_config = self.config_store.load()
            if latest_config != self._config:
                self.apply_noise_settings(latest_config)

        cleaned, metrics = self.noise_suppressor.process(mono)
        speech_active = bool(np.sqrt(np.mean(np.square(cleaned.astype(np.float32)))) / 32768.0 > 0.02)
        self.noise_suppressor.update_noise_profile(mono, is_speech=speech_active)

        rms_left = float(np.sqrt(np.mean(left * left)) / 32768.0)
        rms_right = float(np.sqrt(np.mean(right * right)) / 32768.0)
        correlation_direction = estimate_direction(left, right)
        direction, direction_angle, direction_confidence, distance_m = calculate_direction(
            rms_left,
            rms_right,
        )
        if direction == "front" and correlation_direction in {"left", "right"}:
            direction = f"front-{correlation_direction}"
            direction_angle = -45 if correlation_direction == "left" else 45
            direction_confidence = max(direction_confidence, 0.35)
        pitch_hz = estimate_pitch_hz(cleaned, DEFAULT_AUDIO_SAMPLE_RATE)

        self.latest = normalize_audio_payload({
            "left": round(rms_left, 4),
            "right": round(rms_right, 4),
            "rms": [round(rms_left, 4), round(rms_right, 4)],
            "direction": direction,
            "direction_angle": direction_angle,
            "direction_confidence": round(direction_confidence, 3),
            "distance_estimate_m": round(distance_m, 2) if distance_m else None,
            "noise_level_db": metrics["noise_level_db"],
            "signal_level_db": metrics["signal_level_db"],
            "snr_db": metrics["snr_db"],
            "noise_reduction_db": metrics["noise_reduction_db"],
            "noise_suppression_active": metrics["noise_suppression_active"],
            "suppression_strength": metrics["strength"],
            "suppression_sensitivity": metrics["sensitivity"],
            "estimated_pitch_hz": round(pitch_hz, 1) if pitch_hz is not None else None,
            "device_index": self.device_index,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return self.latest

    def close(self):
        if self.stream is not None:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        if self.pa is not None:
            self.pa.terminate()
            self.pa = None


audio = AudioMonitor()


class Apa102Leds:
    def __init__(self):
        self.colors = [(0, 0, 0)] * 3
        self.spi = None

    def init(self):
        if self.spi is not None or spidev is None:
            return
        self.spi = spidev.SpiDev()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 8000000
        self.spi.mode = 0

    def set_led(self, led, r, g, b, brightness=1.0):
        self.colors[led] = (
            int(r * brightness),
            int(g * brightness),
            int(b * brightness),
        )
        self.show()

    def show(self):
        self.init()
        if self.spi is None:
            return
        frame = [0, 0, 0, 0]
        for r, g, b in self.colors:
            frame.extend([0b11100000 | 31, b & 255, g & 255, r & 255])
        frame.extend([255, 255, 255, 255])
        self.spi.xfer2(frame)


leds = Apa102Leds()


class ButtonState:
    def __init__(self):
        self.device = None
        self.last_pressed = None
        self.press_count = 0
        self.pressed = False

    def init(self):
        if self.device is not None or DigitalInputDevice is None:
            return
        self.device = DigitalInputDevice(17, pull_up=True)
        self.device.when_activated = self._pressed
        self.device.when_deactivated = self._released

    def _pressed(self):
        self.pressed = True
        self.press_count += 1
        self.last_pressed = datetime.now(timezone.utc).isoformat()

    def _released(self):
        self.pressed = False

    def get(self):
        self.init()
        if self.device is not None:
            self.pressed = bool(self.device.value)
        return {
            "pressed": self.pressed,
            "last_pressed": self.last_pressed,
            "press_count": self.press_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


button = ButtonState()


def cpu_temp_c():
    path = Path("/sys/class/thermal/thermal_zone0/temp")
    if path.exists():
        return round(int(path.read_text().strip()) / 1000.0, 2)
    return None


def uptime_string():
    seconds = int(float(Path("/proc/uptime").read_text().split()[0]))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    return f"{days}d {hours}h {minutes}m"


def i2c_devices():
    try:
        out = subprocess.check_output(["i2cdetect", "-y", "1"], text=True, timeout=2)
    except Exception as exc:
        return {"error": str(exc), "devices": []}

    devices = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        for part in parts[1:]:
            if part != "--":
                devices.append(f"0x{part}")
    return {"devices": sorted(set(devices))}


def sanitize_token(value: str, fallback: str = "unknown") -> str:
    cleaned = "".join(
        char.lower() if char.isalnum() else "_" for char in value.strip()
    ).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned or fallback


def _as_float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def alert_with_type(event: dict[str, Any], event_type: str) -> dict[str, Any]:
    payload = dict(event)
    payload["type"] = event_type
    return payload


def normalize_audio_payload(data: dict[str, Any], *, working: bool = True) -> dict[str, Any]:
    left = round(float(data.get("left", 0.0) or 0.0), 4)
    right = round(float(data.get("right", 0.0) or 0.0), 4)
    derived_direction, derived_angle, derived_confidence, derived_distance = calculate_direction(
        left,
        right,
    )
    direction = data.get("direction") or derived_direction
    if direction == "center":
        direction = "front"
    return {
        "working": working,
        "left": left,
        "right": right,
        "left_rms": left,
        "right_rms": right,
        "rms": [left, right],
        "direction": direction,
        "direction_angle": data.get("direction_angle", derived_angle),
        "direction_confidence": data.get("direction_confidence", derived_confidence),
        "distance_estimate_m": data.get(
            "distance_estimate_m",
            data.get("distance_m", derived_distance),
        ),
        "noise_floor_db": data.get("noise_floor_db", data.get("noise_level_db", -90.0)),
        "noise_level_db": data.get("noise_level_db", data.get("noise_floor_db", -90.0)),
        "signal_level_db": data.get("signal_level_db", -90.0),
        "snr_estimate": data.get("snr_estimate", data.get("snr_db", 0.0)),
        "snr_db": data.get("snr_db", data.get("snr_estimate", 0.0)),
        "noise_reduction_db": data.get("noise_reduction_db", 0.0),
        "noise_suppression_active": data.get("noise_suppression_active", False),
        "estimated_pitch_hz": data.get("estimated_pitch_hz"),
        "device_index": data.get("device_index"),
        "source": data.get("source", "backend_audio"),
        "timestamp": data.get("timestamp", datetime.now(timezone.utc).isoformat()),
        **({"error": data["error"]} if data.get("error") else {}),
    }


def read_shared_audio_status(max_age_seconds: float = 1.5) -> dict[str, Any] | None:
    if not AUDIO_STATUS_PATH.exists():
        return None
    try:
        payload = json.loads(AUDIO_STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        timestamp = datetime.fromisoformat(str(payload.get("timestamp")))
        age = datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)
        if age.total_seconds() > max_age_seconds:
            return None
    except (TypeError, ValueError):
        return None
    payload["source"] = "kws_shared_audio"
    return normalize_audio_payload(payload)


def validate_training_metadata(
    *,
    keyword: str,
    speaker_id: str,
    age_group: str,
    gender: str,
    distance_m: float,
    noise_condition: str,
) -> dict[str, Any]:
    keyword = keyword.strip().lower()
    speaker_id = speaker_id.strip()
    age_group = age_group.strip().lower()
    gender = gender.strip().lower()
    noise_condition = noise_condition.strip().lower()
    if keyword not in TRAINING_KEYWORDS:
        raise HTTPException(status_code=400, detail="Invalid training keyword")
    if not SPEAKER_ID_PATTERN.fullmatch(speaker_id):
        raise HTTPException(status_code=400, detail="Invalid speaker_id")
    if age_group not in TRAINING_AGE_GROUPS:
        raise HTTPException(status_code=400, detail="Invalid age_group")
    if gender not in TRAINING_GENDERS:
        raise HTTPException(status_code=400, detail="Invalid gender")
    if noise_condition not in TRAINING_NOISE_CONDITIONS:
        raise HTTPException(status_code=400, detail="Invalid noise_condition")
    distance = float(distance_m)
    if not math.isfinite(distance) or distance < 0.5 or distance > 5.0:
        raise HTTPException(status_code=400, detail="distance_m must be between 0.5 and 5.0")
    return {
        "keyword": keyword,
        "speaker_id": speaker_id,
        "age_group": age_group,
        "gender": gender,
        "distance_m": distance,
        "noise_condition": noise_condition,
    }


def inspect_training_wav(path: Path) -> dict[str, Any]:
    try:
        with wave.open(str(path), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            compression = wav_file.getcomptype()
    except (wave.Error, EOFError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid WAV file: {exc}") from exc
    duration = frame_count / float(sample_rate or 1)
    if compression != "NONE":
        raise HTTPException(status_code=400, detail="WAV must use PCM encoding")
    if channels != 1:
        raise HTTPException(status_code=400, detail="WAV must be mono")
    if sample_width != 2:
        raise HTTPException(status_code=400, detail="WAV must be 16-bit PCM")
    if sample_rate != 16000:
        raise HTTPException(status_code=400, detail="WAV sample rate must be 16000 Hz")
    if duration < 1.0 or duration > 5.0:
        raise HTTPException(status_code=400, detail="WAV duration must be 1.0 through 5.0 seconds")
    return {
        "sample_rate": sample_rate,
        "channels": channels,
        "duration_s": round(duration, 2),
    }


def distance_slug(distance_m: float) -> str:
    text = f"{distance_m:.1f}".rstrip("0").rstrip(".")
    return text.replace(".", "p")


def safe_dataset_path(relative_path: str) -> Path:
    candidate = (KEYWORD_DATASET_DIR / relative_path).resolve()
    root = KEYWORD_DATASET_DIR.resolve()
    if root != candidate and root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Unsafe dataset path")
    return candidate


def require_api_token(request: Request | None) -> None:
    if request is None:
        return
    expected = API_TOKEN.strip()
    if not expected:
        return
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token.strip() != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid API token")


async def write_upload_to_path(
    upload: UploadFile,
    target_path: Path,
    *,
    max_bytes: int,
) -> int:
    total = 0
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target_path.open("wb") as handle:
            while True:
                try:
                    chunk = await upload.read(1024 * 1024)
                except TypeError:
                    chunk = await upload.read()
                    if chunk:
                        total += len(chunk)
                        if total > max_bytes:
                            raise HTTPException(
                                status_code=413,
                                detail=f"Uploaded file exceeds {max_bytes} bytes",
                            )
                        handle.write(chunk)
                    break
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Uploaded file exceeds {max_bytes} bytes",
                    )
                handle.write(chunk)
    except Exception:
        target_path.unlink(missing_ok=True)
        raise
    return total


def read_training_metadata_rows() -> list[dict[str, str]]:
    if not KEYWORD_METADATA_PATH.exists():
        return []
    with KEYWORD_METADATA_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def rewrite_training_metadata_rows(rows: list[dict[str, str]]) -> None:
    KEYWORD_METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = KEYWORD_METADATA_PATH.with_name(
        f".{KEYWORD_METADATA_PATH.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        with temp_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=TRAINING_METADATA_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {column: row.get(column, "") for column in TRAINING_METADATA_COLUMNS}
                )
        os.replace(temp_path, KEYWORD_METADATA_PATH)
    finally:
        temp_path.unlink(missing_ok=True)


def training_source_path_from_notes(notes: str) -> str | None:
    for token in notes.split(";"):
        key, separator, value = token.strip().partition("=")
        if separator and key == "source" and value:
            return value
    return None


def training_record_id(row: dict[str, str]) -> str:
    stem = Path(row.get("path", "")).stem
    return stem.rsplit("_", 1)[-1] if "_" in stem else stem


def training_record_from_row(row: dict[str, str]) -> dict[str, Any]:
    payload = {column: row.get(column, "") for column in TRAINING_METADATA_COLUMNS}
    payload["id"] = training_record_id(row)
    payload["distance_m"] = _as_float(payload.get("distance_m"), 0.0)
    payload["duration_s"] = _as_float(payload.get("duration_s"), 0.0)
    payload["sample_rate"] = int(_as_float(payload.get("sample_rate"), 0.0))
    return payload


def calculate_training_statistics() -> dict[str, Any]:
    rows = read_training_metadata_rows()
    by_keyword: dict[str, int] = {}
    by_speaker: dict[str, int] = {}
    by_age_group: dict[str, int] = {}
    by_noise_condition: dict[str, int] = {}
    unique_real_speakers = set()
    original = 0
    augmented = 0
    for row in rows:
        source = row.get("source", "")
        keyword_slug = slugify_keyword(row.get("keyword", "unknown"))
        speaker = row.get("speaker_id", "unknown")
        by_keyword[keyword_slug] = by_keyword.get(keyword_slug, 0) + 1
        by_speaker[speaker] = by_speaker.get(speaker, 0) + 1
        age_group = row.get("age_group", "unknown")
        noise = row.get("noise_condition", "unknown")
        by_age_group[age_group] = by_age_group.get(age_group, 0) + 1
        by_noise_condition[noise] = by_noise_condition.get(noise, 0) + 1
        if source == "augmentation":
            augmented += 1
        else:
            original += 1
        if source == "real" and speaker:
            unique_real_speakers.add(speaker)
    return {
        "total_recordings": len(rows),
        "original_recordings": original,
        "augmented_recordings": augmented,
        "unique_real_speakers": len(unique_real_speakers),
        "by_keyword": dict(sorted(by_keyword.items())),
        "by_speaker": dict(sorted(by_speaker.items())),
        "by_age_group": dict(sorted(by_age_group.items())),
        "by_noise_condition": dict(sorted(by_noise_condition.items())),
    }


def training_job_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


async def run_training_job(
    job_id: str,
    operation: Callable[..., Any],
) -> None:
    async with TRAINING_HEAVY_JOB_LOCK:
        async with TRAINING_JOBS_LOCK:
            job = TRAINING_JOBS[job_id]
            job["status"] = "running"
            job["started_at"] = training_job_timestamp()
            job["progress"] = 0
            job["message"] = "Starting..."
        try:
            import inspect
            sig = inspect.signature(operation)
            if len(sig.parameters) > 0:
                result = await asyncio.to_thread(operation, job_id)
            else:
                result = await asyncio.to_thread(operation)
        except Exception as exc:
            async with TRAINING_JOBS_LOCK:
                job = TRAINING_JOBS[job_id]
                job["status"] = "failed"
                job["error"] = str(exc) or exc.__class__.__name__
                job["finished_at"] = training_job_timestamp()
            return
        async with TRAINING_JOBS_LOCK:
            job = TRAINING_JOBS[job_id]
            job["status"] = "succeeded"
            job["progress"] = 100
            job["message"] = "Completed"
            job["result"] = result
            job["finished_at"] = training_job_timestamp()


async def queue_training_job(
    job_type: str,
    operation: Callable[..., Any],
) -> dict[str, str]:
    job_id = f"job-{uuid.uuid4().hex[:12]}"
    async with TRAINING_JOBS_LOCK:
        TRAINING_JOBS[job_id] = {
            "job_id": job_id,
            "job_type": job_type,
            "status": "queued",
            "progress": 0,
            "message": "Queued in background",
            "result": None,
            "error": None,
            "created_at": training_job_timestamp(),
            "started_at": None,
            "finished_at": None,
        }
    TRAINING_JOB_TASKS[job_id] = asyncio.create_task(
        run_training_job(job_id, operation)
    )
    return {"job_id": job_id, "status": "queued"}


def voice_sample_metadata_files(keyword: str | None = None):
    search_dir = VOICE_SAMPLES_DIR / sanitize_token(keyword) if keyword else VOICE_SAMPLES_DIR
    if not search_dir.exists():
        return []
    return sorted(search_dir.rglob("*.json"))


def load_voice_samples(keyword: str | None = None) -> list[dict[str, Any]]:
    samples = []
    for json_file in voice_sample_metadata_files(keyword):
        try:
            payload = json.loads(json_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            samples.append(payload)
    samples.sort(key=lambda item: str(item.get("timestamp", "")))
    return samples


def count_samples(keyword: str | None = None) -> int:
    return len(load_voice_samples(keyword))


def count_by_keyword() -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in load_voice_samples():
        keyword = str(sample.get("keyword", "unknown"))
        counts[keyword] = counts.get(keyword, 0) + 1
    return counts


def count_by_speaker() -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in load_voice_samples():
        speaker = str(sample.get("speaker_name", "unknown"))
        counts[speaker] = counts.get(speaker, 0) + 1
    return counts


def count_unique_speakers() -> int:
    return len(count_by_speaker())


def read_wav_samples(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        raw = wav_file.readframes(wav_file.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16)
    if channels > 1 and samples.size >= channels:
        samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)
    return samples.astype(np.float32), sample_rate


def calculate_average_volume(samples: list[dict[str, Any]]) -> float:
    rms_values = []
    for sample in samples:
        try:
            audio_samples, _ = read_wav_samples(Path(str(sample["filepath"])))
        except Exception:
            continue
        if audio_samples.size:
            rms_values.append(float(np.sqrt(np.mean(np.square(audio_samples))) / 32768.0))
    return float(np.mean(rms_values)) if rms_values else 0.0


def estimate_pitch_range_from_samples(samples: list[dict[str, Any]]) -> list[float | None]:
    pitches = []
    for sample in samples:
        try:
            audio_samples, sample_rate = read_wav_samples(Path(str(sample["filepath"])))
            pitch = estimate_pitch_hz(audio_samples, sample_rate)
        except Exception:
            pitch = None
        if pitch is not None:
            pitches.append(pitch)
    if not pitches:
        return [None, None]
    return [round(float(min(pitches)), 1), round(float(max(pitches)), 1)]


def estimate_clarity(samples: list[dict[str, Any]]) -> float:
    scores = []
    for sample in samples:
        try:
            audio_samples, _ = read_wav_samples(Path(str(sample["filepath"])))
        except Exception:
            continue
        if audio_samples.size == 0:
            continue
        rms = float(np.sqrt(np.mean(np.square(audio_samples))) / 32768.0)
        peak = float(np.max(np.abs(audio_samples)) / 32768.0)
        crest = peak / max(rms, 1e-6)
        scores.append(float(np.clip((rms * 8.0) + (1.0 / max(crest, 1.0)), 0.0, 1.0)))
    return float(np.mean(scores)) if scores else 0.0


def alert_to_dict(event: AlertIn) -> dict[str, Any]:
    if hasattr(event, "model_dump"):
        return event.model_dump()
    return event.dict()


def normalize_event_id(value: object) -> tuple[str, bool]:
    if value is None:
        return str(uuid.uuid4()), True
    event_id = str(value).strip()
    if not event_id:
        raise HTTPException(status_code=400, detail="event_id must be non-empty")
    if len(event_id) > 128:
        raise HTTPException(
            status_code=400,
            detail="event_id must be 128 characters or fewer",
        )
    if any(ord(character) < 32 for character in event_id):
        raise HTTPException(
            status_code=400,
            detail="event_id must not contain control characters",
        )
    return event_id, False


def alert_event_fingerprint(payload: dict[str, Any]) -> str:
    stable = {
        "keyword": str(payload.get("keyword") or "").strip().lower(),
        "source": str(payload.get("source") or "").strip().lower(),
        "timestamp": str(payload.get("timestamp") or "").strip(),
        "confidence": round(_as_float(payload.get("confidence"), 0.0), 6),
    }
    return json.dumps(stable, sort_keys=True, separators=(",", ":"))


def duplicate_response(event: dict[str, Any]) -> dict[str, Any]:
    duplicate = dict(event)
    duplicate["duplicate_event"] = True
    return {"ok": True, "duplicate_event": True, "event": duplicate}


def first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def thermal_frame_values_valid(temperatures: object) -> bool:
    try:
        values = list(temperatures)  # type: ignore[arg-type]
    except TypeError:
        return False
    if len(values) != 768:
        return False
    for value in values:
        try:
            if not math.isfinite(float(value)):
                return False
        except (TypeError, ValueError):
            return False
    return True


def thermal_evidence_for_decision(
    thermal_payload: dict[str, Any] | None,
    *,
    read_error: Exception | None = None,
) -> dict[str, Any]:
    if thermal_payload is None:
        evidence: dict[str, Any] = {
            "thermal_state": "unavailable",
            "frame_valid": False,
        }
        if read_error is not None:
            evidence["thermal_error"] = str(read_error)
        elif getattr(thermal, "error", None):
            evidence["thermal_error"] = str(thermal.error)
        return evidence

    evidence = dict(thermal_payload or {})
    if read_error is not None:
        evidence["thermal_error"] = str(read_error)

    last_read_at = getattr(thermal, "_last_read_at", None)
    if last_read_at is not None:
        evidence["frame_age_seconds"] = max(0.0, time.monotonic() - float(last_read_at))

    temperatures = evidence.get("temperatures")
    if temperatures is not None:
        evidence["frame_valid"] = thermal_frame_values_valid(temperatures)

    if not evidence.get("frame_valid", True):
        evidence["thermal_state"] = "invalid"
    elif evidence.get("error") or evidence.get("analysis_error") or evidence.get("thermal_error"):
        evidence["thermal_state"] = "unavailable"
    elif (
        evidence.get("frame_age_seconds", 0.0)
        > decision_engine.policy.thermal_freshness_seconds
    ):
        evidence["thermal_state"] = "stale"
    elif "thermal_state" not in evidence:
        if evidence.get("human_detected", False):
            evidence["thermal_state"] = "positive"
        else:
            evidence["thermal_state"] = "negative"

    return evidence


def enrich_alert_payload(payload: dict[str, Any], thermal_payload: dict[str, Any] | None) -> dict[str, Any]:
    thermal_payload = thermal_payload or {}
    latest_audio = read_shared_audio_status() or (
        audio.latest if isinstance(audio.latest, dict) else {}
    )
    direction = payload.get("direction") or latest_audio.get("direction") or "front"
    if direction == "center":
        direction = "front"
    payload["direction"] = direction
    payload["direction_angle"] = first_not_none(
        payload.get("direction_angle"),
        latest_audio.get("direction_angle"),
        0,
    )
    payload["direction_confidence"] = first_not_none(
        payload.get("direction_confidence"),
        latest_audio.get("direction_confidence"),
        0.0,
    )
    payload["distance_estimate_m"] = first_not_none(
        payload.get("distance_estimate_m"),
        payload.get("distance_m"),
        latest_audio.get("distance_estimate_m"),
    )
    payload["phase"] = payload.get("phase") or "direction_guidance"
    decision = decision_engine.evaluate(payload, thermal_payload)
    decision_factors = decision["decision_factors"]
    payload["raw_thermal_human_detected"] = thermal_payload.get("human_detected", False)
    payload["human_detected"] = decision["thermal_state"] == "positive"
    payload["body_coverage"] = thermal_payload.get("body_coverage", 0.0)
    payload["detected_part"] = thermal_payload.get("detected_part", "no_human")
    payload["thermal_confidence_boost"] = decision_factors["thermal_boost"]
    payload["raw_thermal_confidence_boost"] = decision_factors["raw_thermal_boost"]
    payload["thermal_confidence"] = decision_factors["thermal_confidence"]
    payload["thermal_state"] = decision["thermal_state"]
    payload["thermal_frame_age_seconds"] = decision_factors[
        "thermal_frame_age_seconds"
    ]
    payload["thermal_frame_valid"] = decision_factors["thermal_frame_valid"]
    payload["keyword_confidence"] = decision["keyword_confidence"]
    payload["final_confidence"] = decision["final_confidence"]
    payload["decision_factors"] = decision_factors
    # Legacy aliases for current Flutter builds. Do not change these outside
    # the decision engine; `decision_state` is the authoritative state.
    payload["alert_level"] = decision["alert_level"]
    payload["should_alert"] = decision["should_alert"]
    payload["decision_state"] = decision["decision_state"]
    payload["decision_reason"] = decision["decision_reason"]
    payload["alert_modality"] = decision["alert_modality"]
    payload["policy_version"] = decision["policy_version"]
    payload["policy_source"] = decision["policy_source"]
    return payload


def current_noise_settings() -> dict[str, Any]:
    payload = audio.get_noise_settings()
    latest = audio.latest
    return {
        "active": payload["active"],
        "strength": payload["strength"],
        "sensitivity": payload["sensitivity"],
        "snowboy_sensitivity": payload.get("snowboy_sensitivity"),
        "noise_floor_db": latest.get("noise_level_db", payload.get("noise_floor_db", -90.0)),
        "snr_estimate": latest.get("snr_db", payload.get("snr_estimate", 0.0)),
        "reduction_db": latest.get(
            "noise_reduction_db",
            payload.get("reduction_db", 0.0),
        ),
    }


@app.on_event("startup")
async def startup():
    try:
        button.init()
    except Exception as exc:
        print(f"Button init skipped: {exc}")
    try:
        thermal.init()
    except Exception as exc:
        print(f"Thermal init skipped: {exc}")
    VOICE_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    noise_config_store.save(noise_config_store.load())


@app.on_event("shutdown")
async def shutdown_event():
    audio.close()
    if hasattr(thermal, "close"):
        thermal.close()


@app.websocket("/ws/thermal")
async def ws_thermal(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            try:
                payload = await asyncio.to_thread(thermal.read)
            except Exception as exc:
                payload = {
                    "error": str(exc),
                    "human_detected": False,
                    "body_coverage": 0.0,
                    "detected_part": "error",
                    "confidence_boost": 0.0,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            await websocket.send_json(payload)
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        return


@app.websocket("/ws/audio")
async def ws_audio(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            try:
                payload = normalize_audio_payload(await asyncio.to_thread(audio.read))
            except Exception as exc:
                payload = normalize_audio_payload({
                    "error": str(exc),
                    "working": False,
                    "left": 0.0,
                    "right": 0.0,
                    "rms": [0.0, 0.0],
                    "direction": "center",
                    "noise_level_db": -90.0,
                    "signal_level_db": -90.0,
                    "snr_db": 0.0,
                    "noise_reduction_db": 0.0,
                    "noise_suppression_active": False,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, working=False)
            await websocket.send_json(payload)
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        return


@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    await websocket.accept()
    client_queue = await alerts.connect()
    try:
        for event in alert_store.list_recent(10):
            await websocket.send_json(alert_with_type(event, "historical"))
        await websocket.send_json(
            {
                "type": "connected",
                "message": "Alert stream active",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        while True:
            event = await client_queue.get()
            await websocket.send_json(alert_with_type(event, "live"))
    except WebSocketDisconnect:
        alerts.disconnect(client_queue)


@app.get("/api/status")
async def api_status():
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    i2c = i2c_devices()
    latest_thermal = thermal._last_payload or {}
    thermal_model_status = thermal.model_status()
    return {
        "cpu_temp_c": cpu_temp_c(),
        "ram_usage_percent": round(mem.percent, 2),
        "ram": {"total": mem.total, "available": mem.available, "percent": mem.percent},
        "disk": {"total": disk.total, "free": disk.free, "percent": disk.percent},
        "uptime": uptime_string(),
        "uptime_seconds": int(time.time() - APP_START),
        "i2c_devices": i2c.get("devices", []),
        "i2c": i2c,
        "thermal": {
            "address": f"0x{thermal.address:02x}" if thermal.address else None,
            "error": thermal.error,
            "human_detected": latest_thermal.get("human_detected", False),
            "body_coverage": latest_thermal.get("body_coverage", 0.0),
            "detected_part": latest_thermal.get("detected_part", "unknown"),
            "confidence_boost": latest_thermal.get("confidence_boost", 0.0),
            **thermal_model_status,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/api/leds")
async def api_leds(request: LedRequest):
    leds.set_led(request.led, request.r, request.g, request.b, request.brightness)
    return {"ok": True, "led": request.led, "colors": leds.colors}


@app.get("/api/button")
async def api_button():
    return button.get()


@app.get("/api/audio/noise-suppression")
async def get_noise_suppression():
    return current_noise_settings()


@app.post("/api/audio/noise-suppression")
async def set_noise_suppression(request: NoiseSuppressionRequest):
    config = NoiseSuppressionConfig(
        active=request.active,
        strength=request.strength,
        sensitivity=request.sensitivity,
        snowboy_sensitivity=request.snowboy_sensitivity,
    )
    noise_config_store.save(config)
    audio.apply_noise_settings(config)
    return {"ok": True, "settings": current_noise_settings()}


@app.get("/api/audio/status")
async def audio_status():
    try:
        data = normalize_audio_payload(await asyncio.to_thread(audio.read))
        return {
            **data,
            "working": True,
            "sample_rate": DEFAULT_AUDIO_SAMPLE_RATE,
            "channels": 2,
        }
    except Exception as exc:
        shared = read_shared_audio_status()
        if shared is not None:
            return {
                **shared,
                "working": True,
                "sample_rate": DEFAULT_AUDIO_SAMPLE_RATE,
                "channels": 2,
            }
        return {
            "working": False,
            "error": str(exc),
            "device_index": audio.device_index,
            "sample_rate": DEFAULT_AUDIO_SAMPLE_RATE,
            "channels": 2,
        }


@app.get("/api/alerts")
async def api_alert_history(limit: int = 100):
    return {"history": alert_store.list_recent(limit)}


@app.delete("/api/alerts")
async def api_clear_alert_history():
    deleted = await asyncio.to_thread(alert_store.clear)
    return {"ok": True, "deleted_count": deleted}


@app.post("/api/training/record", status_code=status.HTTP_201_CREATED)
async def upload_training_record(
    file: UploadFile = File(...),
    keyword: str = Form(...),
    speaker_id: str = Form(...),
    age_group: str = Form(...),
    gender: str = Form(...),
    distance_m: float = Form(...),
    noise_condition: str = Form(...),
):
    metadata = validate_training_metadata(
        keyword=keyword,
        speaker_id=speaker_id,
        age_group=age_group,
        gender=gender,
        distance_m=distance_m,
        noise_condition=noise_condition,
    )

    ensure_training_dataset_layout(KEYWORD_DATASET_DIR)
    temp_dir = KEYWORD_DATASET_DIR / ".tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"upload_{uuid.uuid4().hex}.wav"
    try:
        upload_size = await write_upload_to_path(
            file,
            temp_path,
            max_bytes=MAX_TRAINING_WAV_UPLOAD_BYTES,
        )
        if upload_size == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        wav_info = inspect_training_wav(temp_path)
        recording_id = uuid.uuid4().hex[:8]
        keyword_slug = slugify_keyword(metadata["keyword"])
        distance_text = distance_slug(metadata["distance_m"])
        filename = (
            f"{keyword_slug}_{metadata['speaker_id']}_{metadata['age_group']}_"
            f"{metadata['gender']}_{distance_text}m_"
            f"{metadata['noise_condition']}_{recording_id}.wav"
        )
        relative_path = f"positive/{keyword_slug}/{filename}"
        final_path = safe_dataset_path(relative_path)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_path, final_path)
        created_at = datetime.now(timezone.utc).isoformat()
        with TRAINING_METADATA_LOCK:
            append_training_metadata(
                KEYWORD_METADATA_PATH,
                {
                    "path": relative_path,
                    "keyword": metadata["keyword"],
                    "label": metadata["keyword"],
                    "speaker_id": metadata["speaker_id"],
                    "age_group": metadata["age_group"],
                    "gender": metadata["gender"],
                    "distance_m": str(metadata["distance_m"]),
                    "noise_condition": metadata["noise_condition"],
                    "source": "real",
                    "sample_rate": str(wav_info["sample_rate"]),
                    "duration_s": f"{wav_info['duration_s']:.2f}",
                    "notes": "",
                },
            )
        return {
            "id": recording_id,
            "path": relative_path,
            "keyword": metadata["keyword"],
            "speaker_id": metadata["speaker_id"],
            "sample_rate": wav_info["sample_rate"],
            "channels": wav_info["channels"],
            "duration_s": wav_info["duration_s"],
            "created_at": created_at,
        }
    except HTTPException as exc:
        print(
            "Training upload rejected: "
            f"keyword={keyword!r} speaker_id={speaker_id!r} detail={exc.detail}"
        )
        temp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        print(
            "Training upload failed unexpectedly: "
            f"keyword={keyword!r} speaker_id={speaker_id!r} error={exc}"
        )
        temp_path.unlink(missing_ok=True)
        raise


@app.get("/api/training/statistics")
async def training_statistics():
    with TRAINING_METADATA_LOCK:
        return calculate_training_statistics()


@app.get("/api/training/recordings")
async def training_recordings():
    with TRAINING_METADATA_LOCK:
        rows = read_training_metadata_rows()
        recordings = []
        for row in rows:
            relative_path = row.get("path", "")
            if relative_path:
                safe_dataset_path(relative_path)
            recordings.append(training_record_from_row(row))
        return {"total": len(recordings), "recordings": recordings}


@app.delete("/api/training/recordings/{recording_id}")
async def delete_training_recording(recording_id: str):
    if not re.fullmatch(r"[A-Fa-f0-9]{8,32}", recording_id):
        raise HTTPException(status_code=404, detail="Training recording not found")

    with TRAINING_METADATA_LOCK:
        rows = read_training_metadata_rows()
        original = next(
            (
                row
                for row in rows
                if row.get("source") != "augmentation"
                and training_record_id(row) == recording_id
            ),
            None,
        )
        if original is None:
            raise HTTPException(status_code=404, detail="Training recording not found")

        original_path = original.get("path", "")
        augmented = [
            row
            for row in rows
            if row.get("source") == "augmentation"
            and training_source_path_from_notes(row.get("notes", "")) == original_path
        ]
        removed_paths = {
            row.get("path", "")
            for row in [original, *augmented]
            if row.get("path", "")
        }
        remaining = [row for row in rows if row.get("path", "") not in removed_paths]
        rewrite_training_metadata_rows(remaining)

        for relative_path in removed_paths:
            safe_dataset_path(relative_path).unlink(missing_ok=True)

    return {
        "deleted": True,
        "recording_id": recording_id,
        "deleted_originals": 1,
        "deleted_augmented": len(augmented),
    }


@app.get("/api/training/jobs/{job_id}")
async def training_job_status(job_id: str):
    async with TRAINING_JOBS_LOCK:
        job = TRAINING_JOBS.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Training job not found")
        return dict(job)




# ---------------------------------------------------------------------------
#  Training Pipeline Endpoints (Phase 2: validate, augment, export, train,
#  deploy, evaluate, keywords)
# ---------------------------------------------------------------------------

TRAINING_KEYWORD_LANG = {
    "help": "en", "help me": "en", "save me": "en", "please help": "en",
    "emergency": "en", "rescue": "en", "over here": "en", "ouch": "en",
    "tulong": "fil", "saklolo": "fil", "tulungan niyo ako": "fil",
    "tulungan mo ako": "fil", "kailangan ko ng tulong": "fil",
    "ang sakit": "fil", "aray": "fil", "sunog": "fil", "agai": "fil",
}


@app.get("/api/training/keywords")
async def training_keywords():
    """Return the canonical 17-keyword inventory with language tags."""
    return {
        "keywords": [
            {
                "keyword": kw,
                "slug": slugify_keyword(kw),
                "language": TRAINING_KEYWORD_LANG.get(kw, "unknown"),
            }
            for kw in TRAINING_KEYWORDS
        ],
        "total": len(TRAINING_KEYWORDS),
    }


@app.post("/api/training/validate", status_code=status.HTTP_202_ACCEPTED)
async def training_validate():
    """Launch an async dataset validation job."""
    def _run_validation():
        from validate_keyword_dataset import validate_dataset
        return validate_dataset(KEYWORD_DATASET_DIR)

    return await queue_training_job("validation", _run_validation)


@app.post("/api/training/augment", status_code=status.HTTP_202_ACCEPTED)
async def training_augment(copies_per_file: int = 2, seed: int = 1337):
    """Launch an async augmentation job."""
    if not 1 <= copies_per_file <= 5:
        raise HTTPException(
            status_code=400,
            detail="copies_per_file must be between 1 and 5",
        )

    # Check available system memory before queueing
    try:
        vm = psutil.virtual_memory()
        min_memory_bytes = 500 * 1024 * 1024  # 500 MB
        if vm.available < min_memory_bytes:
            avail_mb = vm.available / (1024 * 1024)
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Insufficient system memory for augmentation. "
                    f"At least 500 MB free RAM required, only {avail_mb:.1f} MB available."
                ),
            )
    except HTTPException:
        raise
    except Exception:
        pass

    def _run_augment(job_id: str):
        def _on_progress(current: int, total: int, msg: str):
            pct = int((current / max(1, total)) * 100)
            job = TRAINING_JOBS.get(job_id)
            if job:
                job["progress"] = min(99, max(1, pct))
                job["message"] = msg

        from augment_keyword_dataset import augment_dataset
        output_dir = KEYWORD_DATASET_DIR / "augmented"
        return augment_dataset(
            KEYWORD_DATASET_DIR,
            output_dir,
            copies_per_file=copies_per_file,
            seed=seed,
            progress_callback=_on_progress,
        )

    return await queue_training_job("augmentation", _run_augment)


@app.post("/api/training/export", status_code=status.HTTP_202_ACCEPTED)
async def training_export():
    """Package the dataset as a dated ZIP archive."""
    import shutil
    import zipfile

    def _run_export():
        with TRAINING_METADATA_LOCK:
            rows = read_training_metadata_rows()
        real_speakers = {
            row.get("speaker_id", "").strip()
            for row in rows
            if row.get("source", "").strip().lower() == "real"
            and row.get("speaker_id", "").strip()
        }
        if len(real_speakers) < 3:
            raise ValueError(
                f"Export requires at least 3 real speakers, found {len(real_speakers)}: "
                + ", ".join(sorted(real_speakers))
            )

        from train_openwakeword_models import build_split_manifest, write_manifest
        manifest = build_split_manifest(KEYWORD_DATASET_DIR)
        manifest_path = KEYWORD_DATASET_DIR / "splits" / "openwakeword_split.json"
        write_manifest(manifest, manifest_path)

        DATASET_ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive_path = DATASET_ARCHIVES_DIR / f"keyword_dataset_{timestamp}.zip"

        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if KEYWORD_METADATA_PATH.exists():
                zf.write(KEYWORD_METADATA_PATH, "metadata.csv")
            zf.write(manifest_path, "splits/openwakeword_split.json")
            for wav in KEYWORD_DATASET_DIR.rglob("*.wav"):
                rel = wav.relative_to(KEYWORD_DATASET_DIR)
                zf.write(wav, str(rel))

        return {
            "archive": str(archive_path.relative_to(PROJECT_ROOT)),
            "size_bytes": archive_path.stat().st_size,
            "recordings": len(rows),
            "speakers": len(real_speakers),
        }

    return await queue_training_job("export", _run_export)


@app.post("/api/training/train", status_code=status.HTTP_202_ACCEPTED)
async def training_train(seed: int = 1337):
    """Generate a training manifest and launch the training pipeline."""
    def _run_train():
        from train_openwakeword_models import build_split_manifest, write_manifest

        manifest = build_split_manifest(KEYWORD_DATASET_DIR, seed=seed)
        manifest_path = KEYWORD_DATASET_DIR / "splits" / "openwakeword_split.json"
        write_manifest(manifest, manifest_path)

        keyword_count = len(manifest.get("keywords", {}))
        speaker_info = manifest.get("speakers", {})
        return {
            "manifest_path": str(manifest_path.relative_to(PROJECT_ROOT)),
            "keywords_with_samples": keyword_count,
            "speakers": {
                split: len(ids) for split, ids in speaker_info.items()
            },
            "note": "Manifest created. Run openWakeWord training in Colab with this manifest.",
        }

    return await queue_training_job("training", _run_train)


def validate_upload_filename(filename: str | None, suffix: str, label: str) -> None:
    name = (filename or "").strip().lower()
    if not name.endswith(suffix):
        raise HTTPException(status_code=400, detail=f"{label} must end with {suffix}")


def restart_kws_alert_service() -> dict[str, Any]:
    command = ["sudo", "-n", "systemctl", "restart", "kws-alert.service"]
    if os.name != "posix":
        return {"skipped": True, "reason": "not running on Linux", "command": command}
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=20,
        check=False,
    )
    if completed.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=(
                "KWS service restart failed: "
                + ((completed.stderr or completed.stdout or "").strip() or "unknown error")
            ),
        )
    return {"skipped": False, "command": command}


@app.post("/api/training/deploy")
async def training_deploy(
    onnx_file: UploadFile = File(...),
    onnx_data_file: UploadFile = File(...),
    keyword: str = Form(...),
    request: Request = None,
):
    """Deploy a trained .onnx + .onnx.data model pair to the live models directory."""
    require_api_token(request)
    keyword_slug = slugify_keyword(keyword.strip().lower())
    if keyword.strip().lower() not in TRAINING_KEYWORDS:
        raise HTTPException(status_code=400, detail="Invalid keyword for deployment")

    validate_upload_filename(onnx_file.filename, ".onnx", "ONNX model file")
    validate_upload_filename(onnx_data_file.filename, ".onnx.data", "ONNX data file")

    OPENWAKEWORD_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    temp_onnx = OPENWAKEWORD_MODEL_DIR / f".{keyword_slug}.onnx.{uuid.uuid4().hex}.tmp"
    temp_data = OPENWAKEWORD_MODEL_DIR / f".{keyword_slug}.onnx.data.{uuid.uuid4().hex}.tmp"
    onnx_size = await write_upload_to_path(
        onnx_file,
        temp_onnx,
        max_bytes=MAX_ONNX_UPLOAD_BYTES,
    )
    data_size = await write_upload_to_path(
        onnx_data_file,
        temp_data,
        max_bytes=MAX_ONNX_DATA_UPLOAD_BYTES,
    )

    if not onnx_size:
        temp_onnx.unlink(missing_ok=True)
        temp_data.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="ONNX model file is empty")
    if not data_size:
        temp_onnx.unlink(missing_ok=True)
        temp_data.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="ONNX data file is empty")

    target_onnx = OPENWAKEWORD_MODEL_DIR / f"{keyword_slug}.onnx"
    target_data = OPENWAKEWORD_MODEL_DIR / f"{keyword_slug}.onnx.data"
    old_onnx_bytes = target_onnx.read_bytes() if target_onnx.exists() else None
    old_data_bytes = target_data.read_bytes() if target_data.exists() else None

    # Create timestamped backups of existing models
    backup_dir = OPENWAKEWORD_MODEL_DIR / "backup"
    if target_onnx.exists() or target_data.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if target_onnx.exists():
            backup_onnx = backup_dir / f"{keyword_slug}_{timestamp}.onnx"
            backup_onnx.write_bytes(target_onnx.read_bytes())
        if target_data.exists():
            backup_data = backup_dir / f"{keyword_slug}_{timestamp}.onnx.data"
            backup_data.write_bytes(target_data.read_bytes())

    # Atomic write via temp files
    try:
        os.replace(temp_onnx, target_onnx)
        os.replace(temp_data, target_data)
        restart_result = restart_kws_alert_service()
    except Exception:
        temp_onnx.unlink(missing_ok=True)
        temp_data.unlink(missing_ok=True)
        if old_onnx_bytes is not None:
            target_onnx.write_bytes(old_onnx_bytes)
        if old_data_bytes is not None:
            target_data.write_bytes(old_data_bytes)
        raise

    return {
        "deployed": True,
        "keyword": keyword.strip().lower(),
        "slug": keyword_slug,
        "onnx_size": onnx_size,
        "data_size": data_size,
        "backed_up": backup_dir.exists(),
        "restart": restart_result,
    }


@app.get("/api/training/evaluate")
async def training_evaluate(threshold: float = 0.5):
    """Return evaluation metrics from prediction files, if available."""
    predictions_dir = KEYWORD_DATASET_DIR / "predictions"
    if not predictions_dir.exists() or not any(predictions_dir.iterdir()):
        raise HTTPException(
            status_code=409,
            detail="No prediction files found. Run model evaluation first.",
        )

    from evaluate_keyword_models import evaluate_prediction_dir
    results = evaluate_prediction_dir(
        predictions_dir,
        threshold=threshold,
        negative_hours=None,
    )
    return results


@app.post("/api/voice/sample", response_model=VoiceSampleResponse)
async def upload_voice_sample(
    request: Request,
    keyword: str = "tulong",
    speaker_name: str = "mobile_user",
):
    keyword = sanitize_token(keyword, "tulong")
    speaker_name = sanitize_token(speaker_name, "mobile_user")
    if keyword not in {"tulong", "help"}:
        raise HTTPException(status_code=400, detail="keyword must be 'tulong' or 'help'")

    audio_data = await request.body()
    if len(audio_data) < 44 or not audio_data.startswith(b"RIFF"):
        raise HTTPException(status_code=400, detail="Only WAV audio is accepted")

    sample_hash = hashlib.md5(audio_data).hexdigest()[:12]
    timestamp_slug = datetime.now().strftime("%Y%m%d_%H%M%S")
    sample_id = f"{keyword}_{speaker_name}_{timestamp_slug}_{sample_hash}"
    keyword_dir = VOICE_SAMPLES_DIR / keyword / speaker_name
    keyword_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{sample_id}.wav"
    filepath = keyword_dir / filename
    filepath.write_bytes(audio_data)

    try:
        with wave.open(str(filepath), "rb") as wav_file:
            duration = wav_file.getnframes() / float(wav_file.getframerate())
            sample_rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
    except wave.Error as exc:
        filepath.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Invalid WAV file: {exc}") from exc

    timestamp = datetime.now(timezone.utc).isoformat()
    metadata = {
        "sample_id": sample_id,
        "filename": filename,
        "keyword": keyword,
        "speaker_name": speaker_name,
        "duration_seconds": round(duration, 2),
        "sample_rate": sample_rate,
        "channels": channels,
        "filepath": str(filepath),
        "timestamp": timestamp,
        "file_size_bytes": len(audio_data),
    }
    (keyword_dir / f"{sample_id}.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )

    return VoiceSampleResponse(
        sample_id=sample_id,
        filename=filename,
        duration_seconds=round(duration, 2),
        sample_rate=sample_rate,
        channels=channels,
        keyword=keyword,
        timestamp=timestamp,
        message=(
            f"Voice sample saved for '{keyword}'. "
            f"Total samples for this keyword: {count_samples(keyword)}"
        ),
    )


@app.get("/api/voice/samples")
async def list_voice_samples(keyword: str | None = None):
    samples = load_voice_samples(keyword)
    return {
        "total": len(samples),
        "by_keyword": count_by_keyword(),
        "by_speaker": count_by_speaker(),
        "samples": samples[-20:],
    }


@app.get("/api/voice/stats")
async def voice_sample_stats():
    tulong_samples = count_samples("tulong")
    help_samples = count_samples("help")
    return {
        "tulong_samples": tulong_samples,
        "help_samples": help_samples,
        "unique_speakers": count_unique_speakers(),
        "total_samples": count_samples(),
        "ready_for_training": tulong_samples >= 3 and help_samples >= 3,
        "message": "Minimum 3 samples per keyword recommended for training",
    }


@app.post("/api/voice/calibrate")
async def calibrate_from_samples():
    samples = load_voice_samples()
    if len(samples) < 3:
        raise HTTPException(status_code=400, detail="Need at least 3 samples for calibration")

    avg_volume = calculate_average_volume(samples)
    pitch_range = estimate_pitch_range_from_samples(samples)
    clarity_score = estimate_clarity(samples)
    if avg_volume < 0.1:
        gain_boost = 1.5
        snowboy_sensitivity = 0.35
    elif avg_volume < 0.3:
        gain_boost = 1.0
        snowboy_sensitivity = 0.40
    else:
        gain_boost = 0.8
        snowboy_sensitivity = 0.45

    return {
        "voice_profile": {
            "avg_volume": round(avg_volume, 3),
            "pitch_range_hz": pitch_range,
            "clarity_score": round(clarity_score, 2),
        },
        "recommended_settings": {
            "noise_suppression_strength": 0.3 if clarity_score > 0.7 else 0.5,
            "noise_suppression_sensitivity": 0.6 if avg_volume < 0.2 else 0.5,
            "snowboy_sensitivity": snowboy_sensitivity,
            "gain_boost": gain_boost,
        },
        "samples_analyzed": len(samples),
        "ready_for_production": len(samples) >= 5,
    }


@app.post("/api/alerts")
async def api_alerts(event: AlertIn):
    payload = alert_to_dict(event)
    payload["type"] = "live"
    event_id, generated_event_id = normalize_event_id(payload.get("event_id"))
    payload["event_id"] = event_id
    payload["server_generated_event_id"] = generated_event_id
    fingerprint = alert_event_fingerprint(payload)
    claim = await alert_idempotency.claim(event_id, fingerprint)
    if claim["status"] == "conflict":
        raise HTTPException(
            status_code=409,
            detail="event_id was reused for a different alert event",
        )
    if claim["status"] == "duplicate":
        return duplicate_response(claim["response"])
    if claim["status"] == "in_flight":
        cached_event = await claim["future"]
        return duplicate_response(cached_event)

    try:
        thermal_payload = None
        thermal_error = None
        try:
            thermal_payload = await asyncio.to_thread(
                thermal.latest,
                decision_engine.policy.thermal_freshness_seconds,
            )
        except Exception as exc:
            thermal_error = exc
            thermal_payload = getattr(thermal, "_last_payload", None)

        thermal_payload = thermal_evidence_for_decision(
            thermal_payload,
            read_error=thermal_error,
        )
        payload = enrich_alert_payload(payload, thermal_payload)
        payload["duplicate_event"] = False
        stored_payload = await asyncio.to_thread(alert_store.insert, payload)
        stored_payload["duplicate_event"] = False
        broadcast_payload = dict(stored_payload)
        await alerts.publish(broadcast_payload)
        await alert_idempotency.complete(event_id, stored_payload)
        return {"ok": True, "duplicate_event": False, "event": stored_payload}
    except Exception as exc:
        await alert_idempotency.fail(event_id, exc)
        raise


REFRESH_SCRIPT = RASPBERRY_PI_ROOT / "scripts" / "pi_refresh.sh"
POWER_COMMAND_DELAY_SECONDS = 0.75


def verify_passwordless_sudo() -> None:
    try:
        completed = subprocess.run(
            ["sudo", "-n", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=500, detail="sudo power check timed out.") from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise HTTPException(
            status_code=500,
            detail=(
                "Passwordless sudo is not configured for power commands. "
                "Run sudo bash raspberry_pi/scripts/install_headless.sh. "
                f"{detail}"
            ).strip(),
        )


async def run_delayed_power_command(action: str, command: list[str]) -> None:
    await asyncio.sleep(POWER_COMMAND_DELAY_SECONDS)
    completed = await asyncio.to_thread(
        subprocess.run,
        ["sudo", "-n", *command],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
        check=False,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        print(
            f"Power command failed action={action} returncode={completed.returncode} "
            f"stdout={stdout!r} stderr={stderr!r}",
            flush=True,
        )


@app.post("/api/refresh")
async def api_refresh(request: RefreshRequest, http_request: Request):
    require_api_token(http_request)
    if not REFRESH_SCRIPT.is_file():
        raise HTTPException(status_code=500, detail="Refresh script is missing on the Pi.")

    args = ["sudo", str(REFRESH_SCRIPT)]
    if request.git_pull:
        args.append("--git-pull")
    if request.restart_backend:
        args.append("--restart-backend")

    try:
        completed = await asyncio.to_thread(
            subprocess.run,
            args,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="Refresh timed out.") from exc

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    return {
        "ok": completed.returncode == 0,
        "git_pull": request.git_pull,
        "restart_backend": request.restart_backend,
        "returncode": completed.returncode,
        "stdout": stdout[-4000:] if stdout else "",
        "stderr": stderr[-2000:] if stderr else "",
    }


@app.post("/api/shutdown")
async def api_shutdown(request: Request):
    require_api_token(request)
    verify_passwordless_sudo()
    asyncio.create_task(
        run_delayed_power_command(
            "shutdown",
            ["/usr/sbin/shutdown", "-h", "now"],
        )
    )
    return {"ok": True, "action": "shutdown", "scheduled": True}


@app.post("/api/reboot")
async def api_reboot(request: Request):
    require_api_token(request)
    verify_passwordless_sudo()
    asyncio.create_task(
        run_delayed_power_command("reboot", ["/usr/sbin/reboot"])
    )
    return {"ok": True, "action": "reboot", "scheduled": True}
