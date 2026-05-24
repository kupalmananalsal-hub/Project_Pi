# Project Pi Keyword Spotting

This folder contains the Raspberry Pi keyword spotting services for the
emergency alert system.

## Current Engines

- openWakeWord runs first as an optional preprocessor:
  - Speex noise suppression is enabled inside openWakeWord's inference path.
  - VAD gates whether Vosk/Snowboy should receive each audio chunk.
  - Custom `tulong` and `help` models can post alerts too.
- Vosk detects `tulong` using the Tagalog model:
  `/home/thesis/vosk-models/vosk-model-tl-ph-generic-0.6`
- Snowboy detects `help` using a personal model:
  `/home/thesis/snowboy/examples/Python3/resources/models/help.pmdl`

Both engines send alerts to:

```text
http://127.0.0.1:8765/api/alerts
```

The FastAPI backend then broadcasts the alert to the Flutter app over:

```text
ws://<pi-ip>:8765/ws/alerts
```

## Install Updated Service

From the Pi:

```bash
cd ~/Project_Pi
git pull
chmod +x raspberry_pi/kws/kws_alert_dual.py
chmod +x raspberry_pi/kws/snowboy_training/train_help_model.sh
sudo cp raspberry_pi/systemd/kws-alert-vosk.service /etc/systemd/system/kws-alert.service
sudo systemctl daemon-reload
sudo systemctl enable thermal-backend.service kws-alert.service
sudo systemctl restart thermal-backend.service
sudo systemctl restart kws-alert.service
```

Watch logs:

```bash
sudo journalctl -u kws-alert.service -f
```

Expected startup:

```text
openWakeWord ready
Vosk ready for tulong
Snowboy ready for help
Listening for: tulong via Vosk, help via Snowboy
```

If openWakeWord is not installed yet, the service logs a warning and continues
with the existing Vosk/Snowboy path. This keeps the current emergency alert
pipeline running while dependencies are installed.

## Install openWakeWord

Install the optional third engine inside the same KWS virtual environment:

```bash
source ~/kws-env/bin/activate
pip install openwakeword
sudo apt-get update
sudo apt-get install -y libspeexdsp-dev
python3 -c "import openwakeword; openwakeword.utils.download_models()"
```

Smoke test VAD and Speex noise suppression:

```bash
source ~/kws-env/bin/activate
python3 - <<'PY'
from openwakeword.model import Model

model = Model(
    wakeword_models=[],
    enable_speex_noise_suppression=True,
    vad_threshold=0.5,
)
print("openWakeWord noise suppression + VAD ready")
PY
```

Run the full triple-engine script manually:

```bash
source ~/kws-env/bin/activate
python3 ~/Project_Pi/raspberry_pi/kws/kws_alert_dual.py
```

## Triple-Engine Audio Flow

```text
ReSpeaker 2-Mics audio
  -> Project Pi spectral NoiseSuppressor
  -> openWakeWord VAD + additional wake words
  -> Vosk checks "tulong" only when speech is active
  -> Snowboy checks "help" only when speech is active
  -> FastAPI /api/alerts
  -> Flutter app /ws/alerts
```

openWakeWord is configured through systemd environment variables:

```ini
Environment=OPENWAKEWORD_ENABLED=1
Environment=OPENWAKEWORD_VAD_THRESHOLD=0.50
Environment=OPENWAKEWORD_WAKE_THRESHOLD=0.65
Environment="OPENWAKEWORD_MODEL_THRESHOLDS=tulong=0.55,help=0.65,save_me=0.65,help_me=0.65,please_help=0.65"
Environment=OPENWAKEWORD_SPEEX_NOISE_SUPPRESSION=1
```

The service automatically loads every `.onnx` model in:

```text
/home/thesis/Project_Pi/raspberry_pi/kws/openwakeword_models/
```

Keep each model's `.onnx.data` file in the same directory. To use VAD gating
without posting openWakeWord wake-word alerts, leave the model list blank:

```ini
Environment=OPENWAKEWORD_MODELS=
```

To disable openWakeWord without changing code:

```ini
Environment=OPENWAKEWORD_ENABLED=0
```

Apply overrides:

```bash
sudo systemctl daemon-reload
sudo systemctl restart kws-alert.service
```

## Train Custom openWakeWord Models

Use the official automated openWakeWord Colab notebook to train one synthetic
model per phrase:

```text
https://github.com/dscripka/openWakeWord/blob/main/notebooks/automatic_model_training.ipynb
```

Train one model per distress phrase. Download each generated `.onnx` file and
its `.onnx.data` companion, then copy both files to the Pi:

```bash
mkdir -p ~/Project_Pi/raspberry_pi/kws/openwakeword_models
scp tulong.onnx tulong.onnx.data thesis@<PI_IP>:/home/thesis/Project_Pi/raspberry_pi/kws/openwakeword_models/
scp help.onnx help.onnx.data thesis@<PI_IP>:/home/thesis/Project_Pi/raspberry_pi/kws/openwakeword_models/
```

If the files were downloaded on the Pi itself, move them into the same folder
instead. Restart the keyword service after the model files exist:

```bash
sudo systemctl daemon-reload
sudo systemctl restart kws-alert.service
sudo journalctl -u kws-alert.service -f
```

The keyword service keeps Vosk and Snowboy active. A shared per-keyword
cooldown prevents `tulong` or `help` from posting duplicate alerts when more
than one engine hears the same utterance.

## Train `help.pmdl`

Snowboy's original hosted trainer is no longer available. The helper script
uses the Docker-based `rhasspy/snowboy-seasalt` trainer.

Install Docker if needed:

```bash
sudo apt update
sudo apt install -y docker.io curl
sudo usermod -aG docker thesis
newgrp docker
```

Train a `help.pmdl` model:

```bash
cd ~/Project_Pi
bash raspberry_pi/kws/snowboy_training/train_help_model.sh all
```

For a phrase model:

```bash
HOTWORD_TEXT="please help" MODEL_NAME=please_help \
  bash raspberry_pi/kws/snowboy_training/train_help_model.sh all
```

If the Docker image does not run on the Pi architecture, run the same helper
from a Linux/x86_64 computer with Docker, then copy the generated `.pmdl` file
to:

```text
/home/thesis/snowboy/examples/Python3/resources/models/help.pmdl
```

## Temporary Stand-In Model

Before `help.pmdl` exists, use a bundled model for wiring tests:

```bash
sudo systemctl edit kws-alert.service
```

Add:

```ini
[Service]
Environment=SNOWBOY_MODEL_PATHS=/home/thesis/snowboy/examples/Python3/resources/models/jarvis.umdl
Environment=SNOWBOY_KEYWORDS=jarvis
Environment=SNOWBOY_ALERT_KEYWORD=help
```

Restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart kws-alert.service
```

Saying `Jarvis` should post an app alert with keyword `help`.

## Alert Proof

When Snowboy works:

```text
Alert: help detected by snowboy!
Backend alert posted: help
```

When Vosk works:

```text
Alert: tulong detected by vosk!
Backend alert posted: tulong
```

## Tuning False Help Alerts

If saying `tulong` sometimes posts `help`, Snowboy is too sensitive for the
custom `help.pmdl`. The service defaults to:

```ini
Environment=SNOWBOY_SENSITIVITY=0.40
Environment=SNOWBOY_HELP_CONFIRM_SECONDS=0.8
Environment=SNOWBOY_SUPPRESS_AFTER_TULONG_SECONDS=1.5
```

That means Snowboy waits briefly before posting `help`; if Vosk hears `tulong`
in that window, the pending `help` alert is cancelled.

To make Snowboy less sensitive:

```bash
sudo systemctl edit kws-alert.service
```

Add:

```ini
[Service]
Environment=SNOWBOY_SENSITIVITY=0.30
```

Then restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart kws-alert.service
```

## Noise Gate And Direction Tuning

The dual keyword service captures two channels from the ReSpeaker, estimates
voice direction with cross-correlation, and skips quiet chunks before they reach
Vosk/Snowboy.

Defaults:

```ini
Environment=KWS_CHANNELS=2
Environment=KWS_CHUNK_FRAMES=1280
Environment=NOISE_GATE_THRESHOLD=0.015
Environment=NOISE_GATE_HOLD_MS=220
Environment=NOISE_SUPPRESSOR_STRENGTH=0.60
Environment=NOISE_PROFILE_SECONDS=2.0
Environment=NOISE_PROFILE_ADAPT_RATE=0.05
Environment=NOISE_LOG_INTERVAL_SECONDS=5.0
Environment=DIRECTION_THRESHOLD_SECONDS=0.00003
Environment=SNOWBOY_SENSITIVITY_QUIET=0.58
Environment=SNOWBOY_SENSITIVITY_MODERATE=0.48
Environment=SNOWBOY_SENSITIVITY_NOISY=0.38
```

If fans or air conditioning trigger detections, raise the noise gate:

```ini
[Service]
Environment=NOISE_GATE_THRESHOLD=0.03
```

If quiet voices are missed, lower it:

```ini
[Service]
Environment=NOISE_GATE_THRESHOLD=0.012
Environment=NOISE_GATE_HOLD_MS=280
```

If speech is still buried under fans or room echo, increase the suppressor:

```ini
[Service]
Environment=NOISE_SUPPRESSOR_STRENGTH=0.80
```

If the suppressor is eating too much speech detail, relax it:

```ini
[Service]
Environment=NOISE_SUPPRESSOR_STRENGTH=0.55
```

If `help` is still not triggering often enough, push Snowboy higher in steps:

```ini
[Service]
Environment=SNOWBOY_SENSITIVITY_QUIET=0.62
Environment=SNOWBOY_SENSITIVITY_MODERATE=0.52
Environment=SNOWBOY_SENSITIVITY_NOISY=0.42
```

That will make the ReSpeaker more eager to react to quiet speech, but it can
also increase false `help` triggers, especially near `tulong`.

If left/right detection is too sensitive, raise the direction threshold:

```ini
[Service]
Environment=DIRECTION_THRESHOLD_SECONDS=0.00005
```

Apply overrides:

```bash
sudo systemctl daemon-reload
sudo systemctl restart kws-alert.service
```

The backend alert decision uses these thresholds:

- final confidence `< 0.70` -> suppress alert
- `0.70` to `< 0.85` -> visual-only alert
- `>= 0.85` -> full alert with vibration
