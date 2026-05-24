# Raspberry Pi 5 Emergency Alert System: From-Scratch Setup

- Target host: `THESIS`
- Target user: `thesis`
- Current hotspot IP: `172.20.10.8`
- Backend port: `8765`
- OS target: Raspberry Pi OS Bookworm 64-bit

Important driver note: for ReSpeaker 2-Mics Pi HAT v2.0 with TLV320AIC3104 on current Raspberry Pi OS, Seeed's current documented path uses the `respeaker-2mic-v2_0` device-tree overlay from `seeed-linux-dtoverlays`. The older `seeed-voicecard` repo provides the legacy `seeed-2mic-voicecard` overlay for older ReSpeaker hardware and older kernels. Do not install the legacy driver on Pi 5 Bookworm unless the current v2 overlay fails and you have confirmed your board is not the TLV320AIC3104 v2.0 board.

References:

- Raspberry Pi configuration, `raspi-config`, I2C/SPI, and device-tree parameters: https://www.raspberrypi.com/documentation/computers/configuration.html
- Seeed ReSpeaker 2-Mics Pi HAT v2.0 current Raspberry Pi OS setup: https://wiki.seeedstudio.com/respeaker_2_mics_pi_hat_raspberry_v2/
- Legacy Seeed voicecard repo: https://github.com/respeaker/seeed-voicecard
- Adafruit MLX90640 Raspberry Pi/CircuitPython guide: https://learn.adafruit.com/adafruit-mlx90640-ir-thermal-camera/python-circuitpython
- Vosk offline speech recognition and model list: https://alphacephei.com/vosk/models

## Phase 1: First Boot and System Update

1. Flash Raspberry Pi OS Bookworm 64-bit with Raspberry Pi Imager.
2. In Imager advanced settings, set:
   - Hostname: `THESIS`
   - Username: `thesis`
   - Password: your chosen password
   - Locale, timezone, keyboard: your local values
   - Enable SSH
3. Boot the Pi, log in as `thesis`, then run the commands below.

```bash
sudo raspi-config
```

In `raspi-config`:

- `1 System Options > S4 Hostname`: set `THESIS`
- `3 Interface Options > I2 SSH`: enable
- `3 Interface Options > I4 SPI`: enable
- `3 Interface Options > I5 I2C`: enable
- `5 Localisation Options`: set keyboard, locale, timezone, WLAN country
- Finish and reboot if prompted

Non-interactive equivalents for SSH/I2C/SPI:

```bash
sudo raspi-config nonint do_ssh 0
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0
sudo hostnamectl set-hostname THESIS
```

Connect the Pi to the phone hotspot as a DHCP client. Keep the hotspot-client
architecture; do not force a static IP on the Pi. After connecting, check the
current address:

```bash
ip route
nmcli device status
nmcli connection show --active
hostname -I
ip -4 addr show wlan0
```

The current hotspot IP used by the app defaults is `172.20.10.8`. If the
phone hotspot assigns a different IP later, update the Flutter app Settings.

Update the OS:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt autoremove -y
sudo reboot
```

After reboot:

```bash
ssh thesis@172.20.10.8
python3 --version
uname -a
```

## Phase 2: ReSpeaker Hardware Integration

Power off before attaching the HAT:

```bash
sudo poweroff
```

Attach the ReSpeaker 2-Mics Pi HAT v2.0 to the 40-pin GPIO header. Make sure pins are aligned. If audio is unstable, connect auxiliary Micro USB power to the ReSpeaker HAT.

Boot the Pi and install base tools:

```bash
sudo apt update
sudo apt install -y \
  git make gcc g++ build-essential device-tree-compiler \
  raspberrypi-kernel-headers i2c-tools alsa-utils \ 
  libasound2-dev portaudio19-dev python3-venv python3-pip \
  python3-gpiozero python3-spidev python3-pyaudio \
  libatlas-base-dev

sudo usermod -aG audio,gpio,i2c,spi thesis
```

Install the current v2.0 overlay:

```bash
cd ~
git clone https://github.com/Seeed-Studio/seeed-linux-dtoverlays.git
cd ~/seeed-linux-dtoverlays
make overlays/rpi/respeaker-2mic-v2_0-overlay.dtbo
sudo cp overlays/rpi/respeaker-2mic-v2_0-overlay.dtbo /boot/firmware/overlays/respeaker-2mic-v2_0.dtbo
```

Configure `/boot/firmware/config.txt`:

```bash
sudo cp /boot/firmware/config.txt /boot/firmware/config.txt.bak.$(date +%Y%m%d-%H%M%S)
sudo sed -i -E '/^(dtoverlay=(respeaker-2mic-v2_0|seeed-2mic-voicecard)|dtparam=i2s=on|dtparam=i2c_arm=on|dtparam=i2c_arm_baudrate=|dtparam=spi=on)/d' /boot/firmware/config.txt

sudo tee -a /boot/firmware/config.txt >/dev/null <<'EOF'

# Project Pi hardware
dtparam=i2c_arm=on
dtparam=i2c_arm_baudrate=400000
dtparam=spi=on
dtparam=i2s=on
dtoverlay=respeaker-2mic-v2_0

# Legacy ReSpeaker v1/older-kernel overlay only. Do not enable for v2.0 TLV320AIC3104 on Pi 5 Bookworm.
# dtoverlay=seeed-2mic-voicecard
EOF
```

Create an ALSA config that allows shared capture through `dsnoop`:

```bash
tee ~/.asoundrc >/dev/null <<'EOF'
pcm.respeaker_raw {
    type hw
    card seeed2micvoicec
    device 0
}

pcm.respeaker {
    type plug
    slave.pcm "respeaker_dsnoop"
}

pcm.respeaker_dsnoop {
    type dsnoop
    ipc_key 1024
    slave {
        pcm "respeaker_raw"
        channels 2
        rate 16000
        format S16_LE
        period_size 1024
        buffer_size 4096
    }
}

pcm.!default {
    type asym
    capture.pcm "respeaker"
    playback.pcm "plughw:CARD=seeed2micvoicec,DEV=0"
}

ctl.!default {
    type hw
    card seeed2micvoicec
}
EOF
```

Reboot and verify:

```bash
sudo reboot
```

```bash
aplay -l
arecord -l
i2cdetect -y 1
lsmod | grep -E 'tlv320|snd_soc'
dmesg | grep -Ei 'tlv320|respeaker|seeed|i2s' | tail -80
```

Expected:

- `aplay -l` and `arecord -l` show `seeed2micvoicec`
- `i2cdetect -y 1` shows `1a`

Quick audio test:

```bash
arecord -D respeaker -f S16_LE -r 16000 -c 2 -d 5 ~/respeaker_test.wav
aplay ~/respeaker_test.wav
```

Legacy fallback only if you confirm older hardware or the current v2 overlay is wrong for your board:

```bash
cd ~
git clone https://github.com/respeaker/seeed-voicecard.git
cd ~/seeed-voicecard
sudo ./install_arm64.sh
sudo reboot
```

## Phase 3: MLX90640 Thermal Camera Integration

Power off, then connect the MLX90640 to the ReSpeaker Grove I2C port:

- VCC/VIN to 3.3 V
- GND to GND
- SDA to SDA
- SCL to SCL

Boot and install packages:

```bash
sudo apt update
sudo apt install -y \
  python3-pip python3-dev python3-venv swig build-essential \
  liblgpio-dev python3-lgpio i2c-tools \
  libopenblas-dev libjpeg-dev libpng-dev libtiff-dev \
  libavcodec-dev libavformat-dev libswscale-dev python3-opencv
```

Create the system-site-packages virtual environment:

```bash
python3 -m venv --system-site-packages ~/thermal-env-sys
source ~/thermal-env-sys/bin/activate
python -m pip install --upgrade pip wheel setuptools
python -m pip install adafruit-blinka adafruit-circuitpython-mlx90640 numpy opencv-python
deactivate
```

Verify I2C:

```bash
i2cdetect -y 1
```

Expected:

- ReSpeaker codec: `1a`
- MLX90640: usually `10`, sometimes `33`

Create `~/mlx90640_test.py`:

```bash
cat > ~/mlx90640_test.py <<'PY'
import os
import time

import board
import busio
import adafruit_mlx90640

address = int(os.getenv("MLX90640_ADDR", "0x10"), 16)
i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
mlx = adafruit_mlx90640.MLX90640(i2c, address=address)
mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_2_HZ

frame = [0.0] * 768
while True:
    try:
        mlx.getFrame(frame)
        break
    except ValueError:
        time.sleep(0.05)

center_index = (24 // 2) * 32 + (32 // 2)
print(f"MLX90640 address: 0x{address:02x}")
print(f"Center pixel: {frame[center_index]:.2f} C")
print(f"Min: {min(frame):.2f} C")
print(f"Max: {max(frame):.2f} C")
PY

~/thermal-env-sys/bin/python ~/mlx90640_test.py
```

If your camera is at `0x33`:

```bash
MLX90640_ADDR=0x33 ~/thermal-env-sys/bin/python ~/mlx90640_test.py
```

Create `~/thermal_cam_display.py`:

```bash
cat > ~/thermal_cam_display.py <<'PY'
import os
import time

import cv2
import numpy as np
import board
import busio
import adafruit_mlx90640

address = int(os.getenv("MLX90640_ADDR", "0x10"), 16)
i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
mlx = adafruit_mlx90640.MLX90640(i2c, address=address)
mlx.refresh_rate = adafruit_mlx90640.RefreshRate.REFRESH_4_HZ
frame = [0.0] * 768

while True:
    try:
        mlx.getFrame(frame)
    except ValueError:
        continue

    arr = np.array(frame, dtype=np.float32).reshape((24, 32))
    lo = float(np.percentile(arr, 2))
    hi = float(np.percentile(arr, 98))
    norm = np.clip((arr - lo) / max(hi - lo, 0.01), 0, 1)
    img = (norm * 255).astype(np.uint8)
    img = cv2.resize(img, (640, 480), interpolation=cv2.INTER_CUBIC)
    color = cv2.applyColorMap(img, cv2.COLORMAP_INFERNO)
    center = arr[12, 16]
    cv2.putText(color, f"Center {center:.1f} C", (14, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.imshow("MLX90640 Thermal", color)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break
    time.sleep(0.01)

cv2.destroyAllWindows()
PY

~/thermal-env-sys/bin/python ~/thermal_cam_display.py
```

## Phase 4: Keyword Spotting with Vosk

Picovoice is not required. This project can use Vosk offline speech recognition instead, which does not require a company email, API key, or cloud account.

Create the Vosk keyword-spotting environment:

```bash
sudo apt update
sudo apt install -y portaudio19-dev libasound2-dev python3-pyaudio ffmpeg curl

python3 -m venv --system-site-packages ~/kws-env
source ~/kws-env/bin/activate
python -m pip install --upgrade pip wheel setuptools
python -m pip install vosk pyaudio numpy requests
deactivate
```

If you already downloaded and unzipped the models, confirm the paths:

```bash
ls -lh ~/vosk-models
ls -lh ~/vosk-models/vosk-model-tl-ph-generic-0.6
```

If the model folder name is different, use that exact path in the service file later.

Quick microphone sanity check:

```bash
arecord -l
arecord -D respeaker -f S16_LE -r 16000 -c 1 -d 5 ~/kws_test.wav
aplay ~/kws_test.wav
```

Create `~/Project_Pi/raspberry_pi/kws/kws_alert_vosk.py` from the repository, or create the same script manually on the Pi:

```bash
mkdir -p ~/Project_Pi/raspberry_pi/kws

cat > ~/Project_Pi/raspberry_pi/kws/kws_alert_vosk.py <<'PY'
#!/usr/bin/env python3
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pyaudio
import requests
from vosk import KaldiRecognizer, Model

RUNNING = True


def handle_signal(signum, frame):
    global RUNNING
    RUNNING = False


def find_input_device(pa, hint):
    hint = hint.lower()
    fallback = None
    for index in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(index)
        if int(info.get("maxInputChannels", 0)) <= 0:
            continue
        name = str(info.get("name", ""))
        print(f"Input device {index}: {name}", flush=True)
        lowered = name.lower()
        if hint in lowered or "seeed" in lowered or "respeaker" in lowered:
            return index
        if fallback is None:
            fallback = index
    if fallback is None:
        raise RuntimeError("No input device found")
    return fallback


def post_alert(keyword, confidence, backend_url):
    event = {
        "event": "keyword_detected",
        "keyword": keyword,
        "confidence": confidence,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    print(f"Alert: {keyword} detected! {json.dumps(event)}", flush=True)
    try:
        requests.post(backend_url, json=event, timeout=1.0)
    except Exception as exc:
        print(f"Backend alert post failed: {exc}", file=sys.stderr, flush=True)
        with open("/tmp/project_pi_alerts.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")


def main():
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    model_path = Path(os.getenv("VOSK_MODEL_PATH", "/home/thesis/vosk-models/vosk-model-tl-ph-generic-0.6"))
    backend_url = os.getenv("BACKEND_ALERT_URL", "http://127.0.0.1:8765/api/alerts")
    mic_hint = os.getenv("MIC_NAME_HINT", "seeed")
    confidence = float(os.getenv("VOSK_KEYWORD_CONFIDENCE", "0.60"))
    cooldown_seconds = float(os.getenv("KWS_COOLDOWN_SECONDS", "1.5"))

    if not model_path.exists():
        raise RuntimeError(f"Vosk model path does not exist: {model_path}")

    model = Model(str(model_path))
    recognizer = KaldiRecognizer(model, 16000, json.dumps(["tulong", "help", "[unk]"]))
    recognizer.SetWords(True)

    pa = pyaudio.PyAudio()
    stream = None
    last_alert_at = 0.0

    try:
        device_index = find_input_device(pa, mic_hint)
        print(f"Using input device index {device_index}", flush=True)
        stream = pa.open(
            rate=16000,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=4000,
        )

        print("Listening for: tulong / help", flush=True)
        while RUNNING:
            data = stream.read(4000, exception_on_overflow=False)
            accepted = recognizer.AcceptWaveform(data)
            result = json.loads(recognizer.Result() if accepted else recognizer.PartialResult())
            text = (result.get("text") or result.get("partial") or "").lower().strip()
            now = time.monotonic()
            if now - last_alert_at < cooldown_seconds:
                continue
            if "tulong" in text:
                post_alert("tulong", confidence, backend_url)
                last_alert_at = now
                recognizer.Reset()
            elif "help" in text:
                post_alert("help", confidence, backend_url)
                last_alert_at = now
                recognizer.Reset()
    finally:
        if stream is not None:
            stream.stop_stream()
            stream.close()
        pa.terminate()


if __name__ == "__main__":
    main()
PY

chmod +x ~/Project_Pi/raspberry_pi/kws/kws_alert_vosk.py
```

Test Vosk manually. Start the backend first if it is not running:

```bash
sudo systemctl start thermal-backend.service
curl http://127.0.0.1:8765/api/status

source ~/kws-env/bin/activate
VOSK_MODEL_PATH=/home/thesis/vosk-models/vosk-model-tl-ph-generic-0.6 \
BACKEND_ALERT_URL=http://127.0.0.1:8765/api/alerts \
python ~/Project_Pi/raspberry_pi/kws/kws_alert_vosk.py
```

Say `tulong` near the ReSpeaker. You should see an `Alert: tulong detected!` line.

Create the systemd service:

```bash
sudo tee /etc/systemd/system/kws-alert.service >/dev/null <<'EOF'
[Unit]
Description=Project Pi Vosk keyword spotting alert service
After=sound.target network-online.target thermal-backend.service
Wants=network-online.target

[Service]
Type=simple
User=thesis
Group=audio
SupplementaryGroups=gpio i2c spi
WorkingDirectory=/home/thesis/Project_Pi
Environment=PYTHONUNBUFFERED=1
Environment=VOSK_MODEL_PATH=/home/thesis/vosk-models/vosk-model-tl-ph-generic-0.6
Environment=BACKEND_ALERT_URL=http://127.0.0.1:8765/api/alerts
Environment=MIC_NAME_HINT=seeed
Environment=VOSK_KEYWORD_CONFIDENCE=0.60
Environment=KWS_COOLDOWN_SECONDS=1.5
ExecStart=/home/thesis/kws-env/bin/python /home/thesis/Project_Pi/raspberry_pi/kws/kws_alert_vosk.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable kws-alert.service
sudo systemctl start kws-alert.service
sudo journalctl -u kws-alert.service -f
```

## Phase 5: Backend Server

Install backend packages into `~/thermal-env-sys`:

```bash
source ~/thermal-env-sys/bin/activate
python -m pip install fastapi uvicorn websockets psutil pyaudio spidev gpiozero
deactivate
```

Create project directories:

```bash
mkdir -p ~/thermal_cam_project/backend
cd ~/thermal_cam_project/backend
```

Create `~/thermal_cam_project/backend/main.py`:

```bash
cat > ~/thermal_cam_project/backend/main.py <<'PY'
#!/usr/bin/env python3
import asyncio
import json
import os
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
    import board
    import busio
    import adafruit_mlx90640
except Exception:
    board = busio = adafruit_mlx90640 = None

try:
    import spidev
except Exception:
    spidev = None

try:
    from gpiozero import DigitalInputDevice
except Exception:
    DigitalInputDevice = None


APP_START = time.time()
MLX_ADDRS = [int(x, 16) for x in os.getenv("MLX_ADDRS", "0x10,0x33").split(",")]

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
        if board is None:
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
        hint = os.getenv("MIC_NAME_HINT", "seeed").lower()
        fallback = None
        for index in range(self.pa.get_device_count()):
            info = self.pa.get_device_info_by_index(index)
            if int(info.get("maxInputChannels", 0)) <= 0:
                continue
            name = str(info.get("name", ""))
            if hint in name.lower() or "respeaker" in name.lower() or "seeed" in name.lower():
                return index
            fallback = fallback if fallback is not None else index
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
                payload = {"error": str(exc), "timestamp": datetime.now(timezone.utc).isoformat()}
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
                payload = {"error": str(exc), "rms": [0.0, 0.0], "timestamp": datetime.now(timezone.utc).isoformat()}
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
        "thermal": {"address": f"0x{thermal.address:02x}" if thermal.address else None, "error": thermal.error},
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
    payload = event.model_dump()
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
PY
```

Create `requirements.txt`:

```bash
cat > ~/thermal_cam_project/backend/requirements.txt <<'EOF'
fastapi
uvicorn
websockets
psutil
numpy
pyaudio
spidev
gpiozero
adafruit-blinka
adafruit-circuitpython-mlx90640
EOF
```

Create backend README:

```bash
cat > ~/thermal_cam_project/backend/README.md <<'EOF'
# Project Pi Backend

FastAPI backend for MLX90640 thermal streaming, ReSpeaker audio level streaming, keyword alerts, LEDs, GPIO 17 button status, and safe reboot/shutdown.

## Run manually

```bash
source ~/thermal-env-sys/bin/activate
cd ~/thermal_cam_project/backend
uvicorn main:app --host 0.0.0.0 --port 8765
```

## Endpoints

- `GET /api/status`
- `POST /api/leds`
- `GET /api/button`
- `POST /api/shutdown`
- `POST /api/reboot`
- `POST /api/alerts`
- `GET /api/alerts`
- `WS /ws/thermal`
- `WS /ws/audio`
- `WS /ws/alerts`
EOF
```

Allow only safe power commands without a sudo password:

```bash
sudo tee /etc/sudoers.d/project-pi-power >/dev/null <<'EOF'
thesis ALL=NOPASSWD: /usr/sbin/shutdown, /usr/sbin/reboot, /sbin/shutdown, /sbin/reboot
EOF
sudo chmod 440 /etc/sudoers.d/project-pi-power
sudo visudo -cf /etc/sudoers.d/project-pi-power
```

Create systemd service:

```bash
sudo tee /etc/systemd/system/thermal-backend.service >/dev/null <<'EOF'
[Unit]
Description=Project Pi thermal/audio FastAPI backend
After=network-online.target sound.target
Wants=network-online.target

[Service]
Type=simple
User=thesis
Group=audio
SupplementaryGroups=gpio i2c spi
WorkingDirectory=/home/thesis/thermal_cam_project/backend
Environment=PYTHONUNBUFFERED=1
Environment=MLX_ADDRS=0x10,0x33
Environment=MIC_NAME_HINT=seeed
ExecStart=/home/thesis/thermal-env-sys/bin/uvicorn main:app --host 0.0.0.0 --port 8765
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable thermal-backend.service
sudo systemctl start thermal-backend.service
sudo systemctl status thermal-backend.service --no-pager
```

If KWS was already enabled, restart it after backend starts:

```bash
sudo systemctl restart kws-alert.service
```

## Phase 6: GitHub Repository Setup

Initialize the project repository:

```bash
cd ~/thermal_cam_project
git init
```

Create `.gitignore`:

```bash
cat > ~/thermal_cam_project/.gitignore <<'EOF'
# Python
__pycache__/
*.py[cod]
*.pyo
*.pyd
*.so
.Python
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/

# Virtual environments
.venv/
venv/
env/
thermal-env-sys/
picovoice-env/

# Secrets and local config
.env
*.env
kws.env
*.ppn
*.pv
*.pmdl
*.wav
*.mp3
*.log

# Runtime files
*.pid
*.sock
*.sqlite
*.db
tmp/
runtime/

# OS/editor
.DS_Store
Thumbs.db
.idea/
.vscode/

# Build/package
dist/
build/
*.egg-info/
EOF
```

Commit:

```bash
git add .
git commit -m "Initial Raspberry Pi thermal audio backend"
```

Create a GitHub repository:

1. Go to https://github.com/new
2. Repository name: `thermal-cam-project`
3. Visibility: private or public
4. Do not initialize with README, license, or `.gitignore`
5. Copy the remote URL

Push:

```bash
git branch -M main
git remote add origin git@github.com:YOUR_GITHUB_USERNAME/thermal-cam-project.git
git push -u origin main
```

If you use HTTPS instead of SSH:

```bash
git remote set-url origin https://github.com/YOUR_GITHUB_USERNAME/thermal-cam-project.git
git push -u origin main
```

## Phase 7: Verification Checklist

I2C:

```bash
i2cdetect -y 1
```

Expected: `10` or `33` for MLX90640 and `1a` for ReSpeaker codec.

Audio:

```bash
arecord -l
aplay -l
arecord -D respeaker -f S16_LE -r 16000 -c 2 -d 5 ~/verify_audio.wav
aplay ~/verify_audio.wav
```

Thermal camera:

```bash
~/thermal-env-sys/bin/python ~/mlx90640_test.py
```

Backend service:

```bash
systemctl status thermal-backend.service --no-pager
journalctl -u thermal-backend.service -n 80 --no-pager
curl http://172.20.10.8:8765/api/status
```

Thermal WebSocket:

```bash
~/thermal-env-sys/bin/python - <<'PY'
import asyncio
import json
import websockets

async def main():
    async with websockets.connect("ws://172.20.10.8:8765/ws/thermal") as ws:
        msg = json.loads(await ws.recv())
        print(msg.keys())
        print(len(msg.get("temperatures", [])))
        print(msg.get("temperatures", [])[:5])

asyncio.run(main())
PY
```

Audio WebSocket:

```bash
~/thermal-env-sys/bin/python - <<'PY'
import asyncio
import json
import websockets

async def main():
    async with websockets.connect("ws://172.20.10.8:8765/ws/audio") as ws:
        for _ in range(5):
            print(json.loads(await ws.recv()))

asyncio.run(main())
PY
```

Alert WebSocket and manual alert injection:

```bash
~/thermal-env-sys/bin/python - <<'PY'
import asyncio
import json
import websockets

async def main():
    async with websockets.connect("ws://172.20.10.8:8765/ws/alerts") as ws:
        print(json.loads(await ws.recv()))

asyncio.run(main())
PY
```

In another terminal:

```bash
curl -X POST http://172.20.10.8:8765/api/alerts \
  -H 'Content-Type: application/json' \
  -d '{"event":"keyword_detected","keyword":"tulong","confidence":0.95}'
```

Keyword spotting:

```bash
systemctl status kws-alert.service --no-pager
journalctl -u kws-alert.service -f
```

Say "Help" or "Tulong" near the ReSpeaker. Expected log line:

```text
Alert: Help/Tulong detected!
```

LED test:

```bash
curl -X POST http://172.20.10.8:8765/api/leds \
  -H 'Content-Type: application/json' \
  -d '{"led":0,"r":255,"g":0,"b":0}'
curl -X POST http://172.20.10.8:8765/api/leds \
  -H 'Content-Type: application/json' \
  -d '{"led":1,"r":0,"g":255,"b":0}'
curl -X POST http://172.20.10.8:8765/api/leds \
  -H 'Content-Type: application/json' \
  -d '{"led":2,"r":0,"g":0,"b":255}'
```

Button test:

```bash
watch -n 0.5 curl -s http://172.20.10.8:8765/api/button
```

Flutter app endpoints:

```text
REST:    http://172.20.10.8:8765/api/
Thermal: ws://172.20.10.8:8765/ws/thermal
Audio:   ws://172.20.10.8:8765/ws/audio
Alerts:  ws://172.20.10.8:8765/ws/alerts
```
