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

    model_path = Path(
        os.getenv("VOSK_MODEL_PATH", "/home/thesis/vosk-models/vosk-model-tl-ph-generic-0.6")
    )
    backend_url = os.getenv("BACKEND_ALERT_URL", "http://127.0.0.1:8765/api/alerts")
    mic_hint = os.getenv("MIC_NAME_HINT", "seeed")
    threshold_confidence = float(os.getenv("VOSK_KEYWORD_CONFIDENCE", "0.40"))
    cooldown_seconds = float(os.getenv("KWS_COOLDOWN_SECONDS", "1.5"))

    if not model_path.exists():
        raise RuntimeError(f"Vosk model path does not exist: {model_path}")

    model = Model(str(model_path))
    recognizer = KaldiRecognizer(model, 16000)
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
            text = result.get("text") or result.get("partial") or ""
            text = text.lower().strip()

            now = time.monotonic()
            if now - last_alert_at < cooldown_seconds:
                continue

            if "tulong" in text:
                post_alert("tulong", threshold_confidence, backend_url)
                last_alert_at = now
                recognizer.Reset()
            elif "help" in text:
                post_alert("help", threshold_confidence, backend_url)
                last_alert_at = now
                recognizer.Reset()
    finally:
        if stream is not None:
            stream.stop_stream()
            stream.close()
        pa.terminate()


if __name__ == "__main__":
    main()
