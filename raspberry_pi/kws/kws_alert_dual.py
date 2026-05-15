#!/usr/bin/env python3
import json
import os
import queue
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pyaudio
import requests
from vosk import KaldiRecognizer, Model

RUNNING = True
SAMPLE_RATE = 16000
CHUNK_FRAMES = 1024
ALERT_FLUSH_INTERVAL_SECONDS = 2.0


def _split_env(value):
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def handle_signal(signum, frame):
    global RUNNING
    RUNNING = False


class AlertPoster:
    def __init__(self, backend_url, queue_path):
        self.backend_url = backend_url
        self.queue_path = queue_path
        self.session = requests.Session()
        self.lock = threading.Lock()
        self.pending = self._load_pending()

    def publish(self, keyword, confidence, source):
        event = {
            "event": "keyword_detected",
            "keyword": keyword,
            "confidence": confidence,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        print(f"Alert: {keyword} detected by {source}! {json.dumps(event)}", flush=True)
        with self.lock:
            self.pending.append(event)
            self._persist_pending_locked()
        self.flush()

    def flush(self):
        with self.lock:
            if not self.pending:
                return

            while self.pending:
                event = self.pending[0]
                try:
                    response = self.session.post(self.backend_url, json=event, timeout=1.0)
                    response.raise_for_status()
                except Exception as exc:
                    print(
                        f"Backend alert post failed; queued {len(self.pending)} alert(s): {exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                    return

                sent = self.pending.pop(0)
                self._persist_pending_locked()
                print(f"Backend alert posted: {sent['keyword']}", flush=True)

    def _load_pending(self):
        if not self.queue_path.exists():
            return []

        pending = []
        with self.queue_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    decoded = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(decoded, dict):
                    pending.append(decoded)
        return pending

    def _persist_pending_locked(self):
        if not self.pending:
            try:
                self.queue_path.unlink()
            except FileNotFoundError:
                pass
            return

        with self.queue_path.open("w", encoding="utf-8") as handle:
            for event in self.pending:
                handle.write(json.dumps(event) + "\n")


class CooldownGate:
    def __init__(self, seconds):
        self.seconds = seconds
        self.lock = threading.Lock()
        self.last_seen = {}

    def allow(self, keyword):
        now = time.monotonic()
        with self.lock:
            last = self.last_seen.get(keyword, 0.0)
            if now - last < self.seconds:
                return False
            self.last_seen[keyword] = now
            return True


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


def create_vosk_recognizer(model_path, sample_rate):
    model = Model(str(model_path))
    recognizer = KaldiRecognizer(model, sample_rate, json.dumps(["tulong", "[unk]"]))
    recognizer.SetWords(True)
    return recognizer


def read_vosk_text(recognizer, data):
    accepted = recognizer.AcceptWaveform(data)
    result = json.loads(recognizer.Result() if accepted else recognizer.PartialResult())
    return (result.get("text") or result.get("partial") or "").lower().strip()


def import_snowboydetect(swig_path, examples_path):
    for path in (swig_path, examples_path):
        if path and path not in sys.path:
            sys.path.insert(0, path)
    import snowboydetect  # pylint: disable=import-error,import-outside-toplevel

    return snowboydetect


def put_latest(target_queue, data):
    try:
        target_queue.put_nowait(data)
    except queue.Full:
        try:
            target_queue.get_nowait()
        except queue.Empty:
            pass
        target_queue.put_nowait(data)


def vosk_worker(audio_queue, poster, cooldown, config):
    recognizer = create_vosk_recognizer(config["model_path"], config["sample_rate"])
    debug = config["debug"]
    last_debug_text = ""
    print(f"Vosk ready for tulong: {config['model_path']}", flush=True)

    while RUNNING:
        try:
            data = audio_queue.get(timeout=0.2)
        except queue.Empty:
            continue

        text = read_vosk_text(recognizer, data)
        if debug and text and text != last_debug_text:
            print(f"vosk heard: {text}", flush=True)
            last_debug_text = text

        if "tulong" in text and cooldown.allow("tulong"):
            poster.publish("tulong", config["confidence"], "vosk")
            recognizer.Reset()


def snowboy_worker(audio_queue, poster, cooldown, config):
    snowboydetect = import_snowboydetect(config["swig_path"], config["examples_path"])
    detector = snowboydetect.SnowboyDetect(
        str(config["resource_path"]).encode(),
        ",".join(str(path) for path in config["model_paths"]).encode(),
    )
    detector.SetAudioGain(config["audio_gain"])
    detector.SetSensitivity(",".join(config["sensitivities"]).encode())

    detected_sample_rate = int(detector.SampleRate())
    if detected_sample_rate != config["sample_rate"]:
        print(
            f"Snowboy sample rate is {detected_sample_rate}; capture uses {config['sample_rate']}.",
            flush=True,
        )

    print(
        "Snowboy ready for "
        + ", ".join(config["keywords"])
        + " using "
        + ", ".join(str(path) for path in config["model_paths"]),
        flush=True,
    )

    while RUNNING:
        try:
            data = audio_queue.get(timeout=0.2)
        except queue.Empty:
            continue

        result = detector.RunDetection(data)
        if result > 0:
            index = result - 1
            if index < len(config["keywords"]):
                spoken_keyword = config["keywords"][index]
            else:
                spoken_keyword = config["alert_keyword"]

            if cooldown.allow(spoken_keyword):
                poster.publish(config["alert_keyword"], config["confidence"], "snowboy")
        elif result == -1:
            print("Snowboy detection error", file=sys.stderr, flush=True)


def main():
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    vosk_model_path = Path(
        os.getenv("VOSK_MODEL_PATH", "/home/thesis/vosk-models/vosk-model-tl-ph-generic-0.6")
    )
    backend_url = os.getenv("BACKEND_ALERT_URL", "http://127.0.0.1:8765/api/alerts")
    queue_path = Path(os.getenv("ALERT_QUEUE_PATH", "/tmp/project_pi_alerts.jsonl"))
    mic_hint = os.getenv("MIC_NAME_HINT", "seeed")
    sample_rate = int(os.getenv("KWS_SAMPLE_RATE", str(SAMPLE_RATE)))
    chunk_frames = int(os.getenv("KWS_CHUNK_FRAMES", str(CHUNK_FRAMES)))
    cooldown_seconds = float(os.getenv("KWS_COOLDOWN_SECONDS", "1.5"))
    debug = _env_bool("KWS_DEBUG", False)

    snowboy_model_paths = [
        Path(path)
        for path in _split_env(
            os.getenv(
                "SNOWBOY_MODEL_PATHS",
                os.getenv(
                    "SNOWBOY_MODEL_PATH",
                    "/home/thesis/snowboy/examples/Python3/resources/models/help.pmdl",
                ),
            )
        )
    ]
    snowboy_resource_path = Path(
        os.getenv(
            "SNOWBOY_RESOURCE_PATH",
            "/home/thesis/snowboy/examples/Python3/resources/common.res",
        )
    )
    snowboy_keywords = _split_env(os.getenv("SNOWBOY_KEYWORDS", "help"))
    snowboy_sensitivities = _split_env(os.getenv("SNOWBOY_SENSITIVITY", "0.55"))

    if len(snowboy_sensitivities) == 1 and len(snowboy_model_paths) > 1:
        snowboy_sensitivities = snowboy_sensitivities * len(snowboy_model_paths)
    if len(snowboy_keywords) == 1 and len(snowboy_model_paths) > 1:
        snowboy_keywords = snowboy_keywords * len(snowboy_model_paths)

    if len(snowboy_keywords) != len(snowboy_model_paths):
        raise RuntimeError("SNOWBOY_KEYWORDS must match SNOWBOY_MODEL_PATHS")
    if len(snowboy_sensitivities) != len(snowboy_model_paths):
        raise RuntimeError("SNOWBOY_SENSITIVITY must match SNOWBOY_MODEL_PATHS")

    missing = [
        str(path)
        for path in [vosk_model_path, snowboy_resource_path, *snowboy_model_paths]
        if not path.exists()
    ]
    if missing:
        raise RuntimeError(f"Missing keyword model path(s): {', '.join(missing)}")

    poster = AlertPoster(backend_url, queue_path)
    cooldown = CooldownGate(cooldown_seconds)
    vosk_queue = queue.Queue(maxsize=32)
    snowboy_queue = queue.Queue(maxsize=32)

    vosk_thread = threading.Thread(
        target=vosk_worker,
        args=(
            vosk_queue,
            poster,
            cooldown,
            {
                "model_path": vosk_model_path,
                "sample_rate": sample_rate,
                "confidence": float(os.getenv("VOSK_KEYWORD_CONFIDENCE", "0.95")),
                "debug": debug,
            },
        ),
        daemon=True,
    )
    snowboy_thread = threading.Thread(
        target=snowboy_worker,
        args=(
            snowboy_queue,
            poster,
            cooldown,
            {
                "swig_path": os.getenv("SNOWBOY_SWIG_PATH", "/home/thesis/snowboy/swig/Python3"),
                "examples_path": os.getenv(
                    "SNOWBOY_EXAMPLES_PATH", "/home/thesis/snowboy/examples/Python3"
                ),
                "resource_path": snowboy_resource_path,
                "model_paths": snowboy_model_paths,
                "keywords": snowboy_keywords,
                "alert_keyword": os.getenv("SNOWBOY_ALERT_KEYWORD", "help"),
                "sensitivities": snowboy_sensitivities,
                "audio_gain": float(os.getenv("SNOWBOY_AUDIO_GAIN", "1.0")),
                "confidence": float(os.getenv("SNOWBOY_CONFIDENCE", "0.95")),
                "sample_rate": sample_rate,
            },
        ),
        daemon=True,
    )

    pa = pyaudio.PyAudio()
    stream = None
    try:
        device_index = find_input_device(pa, mic_hint)
        print(f"Using shared input device index {device_index}", flush=True)
        stream = pa.open(
            rate=sample_rate,
            channels=1,
            format=pyaudio.paInt16,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=chunk_frames,
        )

        vosk_thread.start()
        snowboy_thread.start()
        print("Listening for: tulong via Vosk, help via Snowboy", flush=True)

        next_flush_at = 0.0
        while RUNNING:
            data = stream.read(chunk_frames, exception_on_overflow=False)
            put_latest(vosk_queue, data)
            put_latest(snowboy_queue, data)

            now = time.monotonic()
            if now >= next_flush_at:
                poster.flush()
                next_flush_at = now + ALERT_FLUSH_INTERVAL_SECONDS
    finally:
        if stream is not None:
            stream.stop_stream()
            stream.close()
        pa.terminate()


if __name__ == "__main__":
    main()
