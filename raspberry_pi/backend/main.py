#!/usr/bin/env python3
import asyncio
import subprocess
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

try:
    import adafruit_mlx90640
    import board
    import busio
except Exception:
    adafruit_mlx90640 = None
    board = None
    busio = None

try:
    import spidev
except Exception:
    spidev = None

try:
    from gpiozero import DigitalInputDevice
except Exception:
    DigitalInputDevice = None


APP_START = time.time()
MLX_ADDRS = [0x10, 0x33]

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
    timestamp: str | None = None


class AlertHub:
    def __init__(self):
        self.clients: set[asyncio.Queue[dict[str, Any]]] = set()
        self.history: deque[dict[str, Any]] = deque(maxlen=100)

    async def publish(self, event: dict[str, Any]):
        if not event.get("timestamp"):
            event["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.history.appendleft(event)
        for queue in list(self.clients):
            await queue.put(event)

    async def connect(self):
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self.clients.add(queue)
        return queue

    def disconnect(self, queue):
        self.clients.discard(queue)


alerts = AlertHub()


class ThermalCamera:
    def __init__(self):
        self.mlx = None
        self.address = None
        self.frame = [0.0] * 768
        self.error = None

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
            except Exception as exc:
                last_error = exc

        self.error = f"MLX90640 not found at {[hex(a) for a in MLX_ADDRS]}: {last_error}"

    def read(self):
        self.init()
        if self.mlx is None:
            raise RuntimeError(self.error or "MLX90640 unavailable")

        while True:
            try:
                self.mlx.getFrame(self.frame)
                break
            except ValueError:
                time.sleep(0.02)

        return {
            "width": 32,
            "height": 24,
            "temperatures": [round(float(x), 2) for x in self.frame],
            "address": f"0x{self.address:02x}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


thermal = ThermalCamera()


class AudioMonitor:
    def __init__(self):
        self.pa = None
        self.stream = None
        self.latest = {"rms": [0.0, 0.0], "timestamp": None}
        self.device_index = None

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
            rate=16000,
            channels=2,
            format=pyaudio.paInt16,
            input=True,
            input_device_index=self.device_index,
            frames_per_buffer=800,
        )

    def read(self):
        self.start()
        data = self.stream.read(800, exception_on_overflow=False)
        samples = np.frombuffer(data, dtype=np.int16)
        left = samples[0::2].astype(np.float32)
        right = samples[1::2].astype(np.float32)
        rms_left = float(np.sqrt(np.mean(left * left)) / 32768.0)
        rms_right = float(np.sqrt(np.mean(right * right)) / 32768.0)
        self.latest = {
            "left": round(rms_left, 4),
            "right": round(rms_right, 4),
            "rms": [round(rms_left, 4), round(rms_right, 4)],
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


def alert_to_dict(event: AlertIn):
    if hasattr(event, "model_dump"):
        return event.model_dump()
    return event.dict()


@app.on_event("startup")
async def startup():
    button.init()
    thermal.init()


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
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            await websocket.send_json(payload)
            await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        return


@app.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    await websocket.accept()
    queue = await alerts.connect()
    try:
        for event in list(alerts.history)[:10]:
            await websocket.send_json(event)
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        alerts.disconnect(queue)


@app.get("/api/status")
async def api_status():
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    i2c = i2c_devices()
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


@app.post("/api/alerts")
async def api_alerts(event: AlertIn):
    payload = alert_to_dict(event)
    await alerts.publish(payload)
    return {"ok": True, "event": payload}


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
