#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import psutil
import pyaudio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

CURRENT_DIR = Path(__file__).resolve().parent
RASPBERRY_PI_ROOT = CURRENT_DIR.parent
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

app = FastAPI(title="Project Pi Thermal Backend", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    event: str = "keyword_detected"
    keyword: str
    confidence: float = 0.0
    direction: str = "center"
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


class NoiseSuppressionRequest(BaseModel):
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    active: bool = True
    snowboy_sensitivity: float | None = Field(default=None, ge=0.0, le=1.0)


class AlertHub:
    def __init__(self):
        self.clients: set[asyncio.Queue[dict[str, Any]]] = set()
        self.history: deque[dict[str, Any]] = deque(maxlen=100)

    async def publish(self, event: dict[str, Any]):
        if not event.get("timestamp"):
            event["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.history.appendleft(event)
        for client_queue in list(self.clients):
            await client_queue.put(event)

    async def connect(self):
        client_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self.clients.add(client_queue)
        return client_queue

    def disconnect(self, client_queue):
        self.clients.discard(client_queue)


alerts = AlertHub()
decision_engine = AlertDecisionEngine()
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

    def _confidence_payload(self, temperatures: list[float]) -> dict[str, Any]:
        try:
            scorer = ThermalConfidenceScorer(temperatures, width=32, height=24)
            return scorer.analyze()
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
        self.start()
        data = self.stream.read(800, exception_on_overflow=False)
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
        direction = estimate_direction(left, right)
        pitch_hz = estimate_pitch_hz(cleaned, DEFAULT_AUDIO_SAMPLE_RATE)

        self.latest = {
            "left": round(rms_left, 4),
            "right": round(rms_right, 4),
            "rms": [round(rms_left, 4), round(rms_right, 4)],
            "direction": direction,
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
        }
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


def alert_to_dict(event: AlertIn) -> dict[str, Any]:
    if hasattr(event, "model_dump"):
        return event.model_dump()
    return event.dict()


def enrich_alert_payload(payload: dict[str, Any], thermal_payload: dict[str, Any] | None) -> dict[str, Any]:
    thermal_payload = thermal_payload or {}
    decision = decision_engine.evaluate(payload, thermal_payload)
    payload["human_detected"] = thermal_payload.get("human_detected", False)
    payload["body_coverage"] = thermal_payload.get("body_coverage", 0.0)
    payload["detected_part"] = thermal_payload.get("detected_part", "no_human")
    payload["thermal_confidence_boost"] = thermal_payload.get("confidence_boost", 0.0)
    payload["final_confidence"] = decision["final_confidence"]
    payload["decision_factors"] = decision["decision_factors"]
    payload["alert_level"] = decision["alert_level"]
    payload["should_alert"] = decision["should_alert"]
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
    button.init()
    thermal.init()
    noise_config_store.save(noise_config_store.load())


@app.on_event("shutdown")
async def shutdown_event():
    audio.close()


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
                payload = await asyncio.to_thread(audio.read)
            except Exception as exc:
                payload = {
                    "error": str(exc),
                    "rms": [0.0, 0.0],
                    "direction": "center",
                    "noise_level_db": -90.0,
                    "signal_level_db": -90.0,
                    "snr_db": 0.0,
                    "noise_reduction_db": 0.0,
                    "noise_suppression_active": False,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            await websocket.send_json(payload)
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        return


@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    await websocket.accept()
    client_queue = await alerts.connect()
    try:
        for event in list(alerts.history)[:10]:
            await websocket.send_json(event)
        while True:
            event = await client_queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        alerts.disconnect(client_queue)


@app.get("/api/status")
async def api_status():
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    i2c = i2c_devices()
    latest_thermal = thermal._last_payload or {}
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


@app.post("/api/alerts")
async def api_alerts(event: AlertIn):
    payload = alert_to_dict(event)
    thermal_payload = None
    try:
        thermal_payload = await asyncio.to_thread(thermal.latest, 1.25)
    except Exception:
        thermal_payload = None

    payload = enrich_alert_payload(payload, thermal_payload)
    if payload["should_alert"]:
        await alerts.publish(payload)
        return {"ok": True, "event": payload}
    return {"ok": True, "suppressed": True, "event": payload}


@app.get("/api/alerts")
async def api_alert_history():
    return {"history": list(alerts.history)}


@app.post("/api/shutdown")
async def api_shutdown():
    subprocess.Popen(["sudo", "/usr/sbin/shutdown", "-h", "now"])
    return {"ok": True, "action": "shutdown"}


@app.post("/api/reboot")
async def api_reboot():
    subprocess.Popen(["sudo", "/usr/sbin/reboot"])
    return {"ok": True, "action": "reboot"}
