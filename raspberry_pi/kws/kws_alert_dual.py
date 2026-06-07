#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import queue
import signal
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pyaudio
import requests
from vosk import KaldiRecognizer, Model

from audio_preprocessor import AudioPreprocessor
from noise_suppressor import (
    DEFAULT_CONFIG_PATH,
    NoiseSuppressionConfigStore,
    NoiseSuppressor,
)
from wav2vec2_verifier import Wav2Vec2Verifier


RUNNING = True
SAMPLE_RATE = 16000
CHUNK_FRAMES = 1024
ALERT_FLUSH_INTERVAL_SECONDS = 2.0
DEFAULT_AUDIO_STATUS_PATH = Path("/tmp/project_pi_audio_status.json")
TAGALOG_KEYWORD_ALIASES: dict[str, set[str]] = {
    "tulong": {"tulong", "tolong", "tulon", "tulom", "tulungan"},
    "saklolo": {"saklolo", "sakolo", "saglolo"},
    "ang sakit": {"ang sakit", "sakit", "masakit"},
    "aray": {"aray", "aray ko"},
    "agai": {"agai", "agay"},
    "sunog": {"sunog"},
}
TAGALOG_KEYWORDS: tuple[str, ...] = tuple(TAGALOG_KEYWORD_ALIASES)


def _split_env(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _friendly_keyword(value: str) -> str:
    keyword = Path(value).stem if any(sep in value for sep in ("/", "\\")) else value
    keyword = keyword.replace("_", " ").replace("-", " ").strip().lower()
    return " ".join(keyword.split())


def _split_threshold_env(value: str) -> dict[str, float]:
    thresholds: dict[str, float] = {}
    for item in _split_env(value):
        if "=" in item:
            name, raw_threshold = item.split("=", 1)
        elif ":" in item:
            name, raw_threshold = item.rsplit(":", 1)
        else:
            continue
        keyword = _friendly_keyword(name)
        try:
            thresholds[keyword] = float(raw_threshold)
        except ValueError:
            print(
                f"Ignoring invalid openWakeWord threshold '{item}'",
                file=sys.stderr,
                flush=True,
            )
    return thresholds


def handle_signal(signum, frame):
    del signum, frame
    global RUNNING
    RUNNING = False


class AlertPoster:
    def __init__(self, backend_url: str, queue_path: Path):
        self.backend_url = backend_url
        self.queue_path = queue_path
        self.session = requests.Session()
        self.lock = threading.Lock()
        self.pending = self._load_pending()

    def publish(
        self,
        keyword: str,
        confidence: float,
        source: str,
        *,
        direction: str = "center",
        extra: dict[str, object] | None = None,
    ) -> None:
        event: dict[str, object] = {
            "event": "keyword_detected",
            "keyword": keyword,
            "confidence": confidence,
            "source": source,
            "direction": direction,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            event.update(extra)
        print(f"Alert: {keyword} detected by {source}! {json.dumps(event)}", flush=True)
        with self.lock:
            self.pending.append(event)
            self._persist_pending_locked()
        self.flush()

    def flush(self) -> None:
        with self.lock:
            if not self.pending:
                return

            while self.pending:
                event = self.pending[0]
                try:
                    response = self.session.post(self.backend_url, json=event, timeout=1.0)
                    response.raise_for_status()
                except Exception as exc:  # pragma: no cover - network side effect
                    print(
                        f"Backend alert post failed; queued {len(self.pending)} alert(s): {exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                    return

                sent = self.pending.pop(0)
                self._persist_pending_locked()
                print(f"Backend alert posted: {sent['keyword']}", flush=True)

    def _load_pending(self) -> list[dict[str, object]]:
        if not self.queue_path.exists():
            return []

        pending: list[dict[str, object]] = []
        with self.queue_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    decoded = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(decoded, dict):
                    pending.append(decoded)
        return pending

    def _persist_pending_locked(self) -> None:
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
    def __init__(self, seconds: float):
        self.seconds = seconds
        self.lock = threading.Lock()
        self.last_seen: dict[str, float] = {}

    def allow(self, keyword: str) -> bool:
        now = time.monotonic()
        with self.lock:
            last = self.last_seen.get(keyword, 0.0)
            if now - last < self.seconds:
                return False
            self.last_seen[keyword] = now
            return True


class AdaptiveSnowboySensitivity:
    def __init__(
        self,
        quiet_value: float = 0.38,
        moderate_value: float = 0.28,
        noisy_value: float = 0.28,
    ) -> None:
        self.quiet_value = quiet_value
        self.moderate_value = moderate_value
        self.noisy_value = noisy_value
        self._lock = threading.Lock()
        self._current_value = moderate_value
        self._last_logged: float | None = None

    def apply_base_sensitivity(self, base_value: float) -> None:
        base = float(np.clip(base_value, 0.2, 0.9))
        with self._lock:
            self.moderate_value = base
            self.quiet_value = float(np.clip(base + 0.10, 0.2, 0.95))
            self.noisy_value = float(np.clip(base - 0.10, 0.2, 0.95))
            self._current_value = self.moderate_value

    @property
    def current_value(self) -> float:
        with self._lock:
            return self._current_value

    def update_for_snr(self, snr_db: float) -> float:
        if snr_db > 20.0:
            next_value = self.quiet_value
        elif snr_db >= 10.0:
            next_value = self.moderate_value
        else:
            next_value = self.noisy_value

        with self._lock:
            if abs(self._current_value - next_value) > 1e-6:
                self._current_value = next_value
                print(
                    f"Adaptive Snowboy sensitivity -> {next_value:.2f} (SNR {snr_db:.1f} dB)",
                    flush=True,
                )
            return self._current_value

    def sensitivity_list(self, model_count: int) -> list[str]:
        value = f"{self.current_value:.2f}"
        return [value] * model_count


class DetectionDispatcher:
    def __init__(
        self,
        poster: AlertPoster,
        cooldown: CooldownGate,
        help_confirm_seconds: float,
        help_suppress_after_tulong_seconds: float,
    ) -> None:
        self.poster = poster
        self.cooldown = cooldown
        self.help_confirm_seconds = help_confirm_seconds
        self.help_suppress_after_tulong_seconds = help_suppress_after_tulong_seconds
        self.lock = threading.Lock()
        self.pending_help_timer: threading.Timer | None = None
        self.pending_help_payload: tuple[float, str, dict[str, object]] | None = None
        self.last_tulong_at = 0.0
        self.last_tulong_hint_at = 0.0

    def submit(
        self,
        keyword: str,
        confidence: float,
        source: str,
        context: dict[str, object] | None = None,
    ) -> None:
        context = context or {}
        if keyword == "tulong":
            self._publish_tulong(confidence, source, context)
            return
        if keyword == "help":
            if source == "snowboy":
                self._schedule_help(confidence, source, context)
            else:
                self._publish_help_now(confidence, source, context)
            return
        self._publish_generic(keyword, confidence, source, context)

    def note_vosk_text(self, text: str) -> None:
        if detect_tagalog_keyword(text) is None:
            return
        with self.lock:
            self.last_tulong_hint_at = time.monotonic()
            if self.pending_help_timer is not None:
                self.pending_help_timer.cancel()
                self.pending_help_timer = None
                self.pending_help_payload = None
                print(
                    "Pending Snowboy help cancelled by Vosk tulong hint",
                    flush=True,
                )

    def _publish_tulong(self, confidence: float, source: str, context: dict[str, object]) -> None:
        with self.lock:
            now = time.monotonic()
            self.last_tulong_at = now
            self.last_tulong_hint_at = now
            if self.pending_help_timer is not None:
                self.pending_help_timer.cancel()
                self.pending_help_timer = None
                self.pending_help_payload = None

        if self.cooldown.allow("tulong"):
            self.poster.publish(
                "tulong",
                confidence,
                source,
                direction=str(context.get("direction", "center")),
                extra={k: v for k, v in context.items() if k != "direction"},
            )

    def _schedule_help(self, confidence: float, source: str, context: dict[str, object]) -> None:
        now = time.monotonic()
        with self.lock:
            tulong_recent = max(self.last_tulong_at, self.last_tulong_hint_at)
            if now - tulong_recent < self.help_suppress_after_tulong_seconds:
                print("Snowboy help ignored near recent tulong detection", flush=True)
                return
            if self.pending_help_timer is not None:
                return

            self.pending_help_payload = (confidence, source, context)
            self.pending_help_timer = threading.Timer(
                self.help_confirm_seconds,
                self._publish_help,
            )
            self.pending_help_timer.daemon = True
            self.pending_help_timer.start()

    def _publish_help(self) -> None:
        with self.lock:
            payload = self.pending_help_payload
            self.pending_help_payload = None
            self.pending_help_timer = None
            tulong_recent = max(self.last_tulong_at, self.last_tulong_hint_at)
            if (
                time.monotonic() - tulong_recent
                < self.help_suppress_after_tulong_seconds
            ):
                print("Pending Snowboy help cancelled by tulong", flush=True)
                return

        if payload is None:
            return
        confidence, source, context = payload
        if self.cooldown.allow("help"):
            self.poster.publish(
                "help",
                confidence,
                source,
                direction=str(context.get("direction", "center")),
                extra={k: v for k, v in context.items() if k != "direction"},
            )

    def _publish_help_now(
        self,
        confidence: float,
        source: str,
        context: dict[str, object],
    ) -> None:
        with self.lock:
            tulong_recent = max(self.last_tulong_at, self.last_tulong_hint_at)
            if (
                time.monotonic() - tulong_recent
                < self.help_suppress_after_tulong_seconds
            ):
                print(f"{source} help ignored near recent tulong detection", flush=True)
                return

        if self.cooldown.allow("help"):
            self.poster.publish(
                "help",
                confidence,
                source,
                direction=str(context.get("direction", "center")),
                extra={k: v for k, v in context.items() if k != "direction"},
            )

    def _publish_generic(
        self,
        keyword: str,
        confidence: float,
        source: str,
        context: dict[str, object],
    ) -> None:
        if self.cooldown.allow(keyword):
            self.poster.publish(
                keyword,
                confidence,
                source,
                direction=str(context.get("direction", "center")),
                extra={k: v for k, v in context.items() if k != "direction"},
            )


def find_input_device(pa: pyaudio.PyAudio, hint: str) -> int:
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


def create_vosk_recognizer(model_path: Path, sample_rate: int) -> KaldiRecognizer:
    model = Model(str(model_path))
    recognizer = KaldiRecognizer(model, sample_rate)
    recognizer.SetWords(True)
    if hasattr(recognizer, "SetPartialWords"):
        recognizer.SetPartialWords(True)
    return recognizer


def _normalize_vosk_text(text: str) -> str:
    return " ".join(
        "".join(char for char in token.lower() if char.isalpha())
        for token in text.split()
    ).strip()


def detect_tagalog_keyword(text: str) -> str | None:
    normalized = _normalize_vosk_text(text)
    if not normalized:
        return None

    tokens = [token for token in normalized.split() if token]
    if not tokens:
        tokens = [normalized]

    for keyword, aliases in TAGALOG_KEYWORD_ALIASES.items():
        for alias in aliases:
            if " " in alias and alias in normalized:
                return keyword
            if alias in tokens:
                return keyword

    for token in tokens:
        for keyword in ("tulong", "saklolo", "sunog", "aray", "agai"):
            minimum_length = 3 if keyword in {"tulong", "aray", "agai"} else 4
            if len(token) >= minimum_length and keyword.startswith(token):
                return keyword
            if (
                len(token) >= minimum_length
                and SequenceMatcher(None, token, keyword).ratio() >= 0.72
            ):
                return keyword
    return None


def looks_like_tulong(text: str) -> bool:
    return detect_tagalog_keyword(text) == "tulong"


def read_vosk_text(recognizer: KaldiRecognizer, data: bytes) -> str:
    accepted = recognizer.AcceptWaveform(data)
    result = json.loads(recognizer.Result() if accepted else recognizer.PartialResult())
    return (result.get("text") or result.get("partial") or "").lower().strip()


def import_snowboydetect(swig_path: str, examples_path: str):
    for path in (swig_path, examples_path):
        if path and path not in sys.path:
            sys.path.insert(0, path)
    import snowboydetect  # pylint: disable=import-error,import-outside-toplevel

    return snowboydetect


def put_latest(target_queue: queue.Queue, data: dict[str, object]) -> None:
    try:
        target_queue.put_nowait(data)
    except queue.Full:
        try:
            target_queue.get_nowait()
        except queue.Empty:
            pass
        target_queue.put_nowait(data)


def write_audio_status(status_path: Path, packet: dict[str, object]) -> None:
    left = np.asarray(packet.get("left", []), dtype=np.float32)
    right = np.asarray(packet.get("right", []), dtype=np.float32)
    left_rms = float(np.sqrt(np.mean(np.square(left))) / 32768.0) if left.size else 0.0
    right_rms = float(np.sqrt(np.mean(np.square(right))) / 32768.0) if right.size else 0.0
    payload = {
        "left": round(left_rms, 4),
        "right": round(right_rms, 4),
        "rms": [round(left_rms, 4), round(right_rms, 4)],
        "direction": packet.get("direction", "center"),
        "noise_level_db": packet.get("noise_level_db", -90.0),
        "noise_floor_db": packet.get("noise_level_db", -90.0),
        "signal_level_db": packet.get("signal_level_db", -90.0),
        "snr_db": packet.get("snr_db", 0.0),
        "snr_estimate": packet.get("snr_db", 0.0),
        "noise_reduction_db": packet.get("noise_reduction_db", 0.0),
        "noise_suppression_active": packet.get("noise_suppression_active", False),
        "openwakeword_available": packet.get("openwakeword_available", False),
        "openwakeword_vad_score": packet.get("openwakeword_vad_score", 0.0),
        "openwakeword_is_speech": packet.get("openwakeword_is_speech", True),
        "openwakeword_model_dir": packet.get("openwakeword_model_dir"),
        "openwakeword_discovered_models": packet.get(
            "openwakeword_discovered_models",
            [],
        ),
        "openwakeword_loaded_models": packet.get("openwakeword_loaded_models", []),
        "openwakeword_missing_models": packet.get("openwakeword_missing_models", []),
        "openwakeword_skipped_models": packet.get("openwakeword_skipped_models", {}),
        "openwakeword_wake_word": packet.get("openwakeword_wake_word"),
        "openwakeword_wake_word_score": packet.get(
            "openwakeword_wake_word_score",
            0.0,
        ),
        "openwakeword_wake_words": packet.get("openwakeword_wake_words", []),
        "openwakeword_scores": packet.get("openwakeword_scores", []),
        "openwakeword_error": packet.get("openwakeword_error"),
        "source": "kws_shared_audio",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        status_path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError as exc:
        print(f"Audio status write failed: {exc}", file=sys.stderr, flush=True)


def split_audio_chunk(data: bytes, channels: int) -> dict[str, object]:
    samples = np.frombuffer(data, dtype=np.int16)
    if channels >= 2:
        usable = samples[: samples.size - (samples.size % channels)]
        framed = usable.reshape(-1, channels)
        left = framed[:, 0]
        right = framed[:, 1]
        mono = np.mean(framed[:, :2].astype(np.float32), axis=1).astype(np.int16)
    else:
        mono = samples
        left = samples
        right = samples

    return {
        "mono_bytes": mono.tobytes(),
        "mono_samples": mono,
        "raw_mono_samples": mono.copy(),
        "left": left,
        "right": right,
        "direction": estimate_direction(left, right),
    }


def audio_samples_to_float32(samples: np.ndarray) -> np.ndarray:
    audio = np.asarray(samples).reshape(-1)
    if audio.size == 0:
        return np.asarray([], dtype=np.float32)

    audio = audio.astype(np.float32, copy=False)
    if float(np.max(np.abs(audio))) > 1.5:
        audio = audio / 32768.0
    return np.clip(audio, -1.0, 1.0).astype(np.float32, copy=False)


def estimate_direction(left_chunk: np.ndarray, right_chunk: np.ndarray, sample_rate: int = SAMPLE_RATE) -> str:
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


def vosk_worker(
    audio_queue: queue.Queue,
    dispatcher: DetectionDispatcher,
    config: dict[str, object],
) -> None:
    sample_rate = int(config["sample_rate"])
    recognizer = create_vosk_recognizer(config["model_path"], sample_rate)
    debug = bool(config["debug"])
    last_debug_text = ""
    confidence = float(config["confidence"])
    verify_below_confidence = float(config["wav2vec2_verify_below_confidence"])
    context_seconds = max(0.1, float(config["wav2vec2_context_seconds"]))
    max_context_samples = max(int(sample_rate * context_seconds), sample_rate)
    recent_audio: deque[np.ndarray] = deque()
    recent_audio_sample_count = 0
    verifier = (
        Wav2Vec2Verifier(sample_rate=sample_rate)
        if bool(config["wav2vec2_enabled"])
        else None
    )
    print(f"Vosk ready for Tagalog distress keywords: {config['model_path']}", flush=True)
    if verifier is not None:
        print(
            "wav2vec2 verifier "
            f"backend={verifier.backend} available={verifier.available}",
            flush=True,
        )
    else:
        print("wav2vec2 verifier disabled by WAV2VEC2_VERIFIER_ENABLED=0", flush=True)

    while RUNNING:
        try:
            data = audio_queue.get(timeout=0.2)
        except queue.Empty:
            continue

        mono_samples = np.asarray(data["mono_samples"], dtype=np.int16)
        recent_audio.append(mono_samples.copy())
        recent_audio_sample_count += int(mono_samples.size)
        while recent_audio_sample_count > max_context_samples and recent_audio:
            removed_samples = recent_audio.popleft()
            recent_audio_sample_count -= int(removed_samples.size)

        text = read_vosk_text(recognizer, data["mono_bytes"])
        if debug and text and text != last_debug_text:
            print(f"vosk heard: {text}", flush=True)
            last_debug_text = text

        tagalog_keyword = detect_tagalog_keyword(text)
        if tagalog_keyword is not None:
            final_confidence = confidence
            context = _event_context(data)
            context["vosk_text"] = text
            print(
                "Vosk detection: "
                f"{tagalog_keyword} confidence={confidence:.2f} text='{text}'",
                flush=True,
            )
            if (
                verifier is not None
                and tagalog_keyword in TAGALOG_KEYWORDS
                and final_confidence < verify_below_confidence
            ):
                verification_samples = (
                    np.concatenate(tuple(recent_audio))
                    if recent_audio
                    else mono_samples
                )
                verified, verified_confidence = verifier.verify(
                    audio_samples_to_float32(verification_samples),
                    tagalog_keyword,
                )
                if not verified:
                    print(
                        "wav2vec2 verifier rejected Vosk detection: "
                        f"{tagalog_keyword}",
                        flush=True,
                    )
                    recognizer.Reset()
                    recent_audio.clear()
                    recent_audio_sample_count = 0
                    continue

                print(
                    "wav2vec2 verifier confirmed Vosk detection: "
                    f"{tagalog_keyword} confidence={verified_confidence:.2f}",
                    flush=True,
                )
                context["wav2vec2_verified"] = True
                context["wav2vec2_backend"] = verifier.backend
                context["vosk_original_confidence"] = final_confidence
                final_confidence = verified_confidence

            dispatcher.note_vosk_text(text)
            dispatcher.submit(
                tagalog_keyword,
                final_confidence,
                "vosk",
                context=context,
            )
            recognizer.Reset()
            recent_audio.clear()
            recent_audio_sample_count = 0


def snowboy_worker(
    audio_queue: queue.Queue,
    dispatcher: DetectionDispatcher,
    config: dict[str, object],
    sensitivity_controller: AdaptiveSnowboySensitivity,
) -> None:
    snowboydetect = import_snowboydetect(config["swig_path"], config["examples_path"])
    detector = snowboydetect.SnowboyDetect(
        str(config["resource_path"]).encode(),
        ",".join(str(path) for path in config["model_paths"]).encode(),
    )
    detector.SetAudioGain(float(config["audio_gain"]))

    current_sensitivities = ",".join(sensitivity_controller.sensitivity_list(len(config["model_paths"])))
    detector.SetSensitivity(current_sensitivities.encode())

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

        next_sensitivities = ",".join(
            sensitivity_controller.sensitivity_list(len(config["model_paths"]))
        )
        if next_sensitivities != current_sensitivities:
            detector.SetSensitivity(next_sensitivities.encode())
            current_sensitivities = next_sensitivities

        result = detector.RunDetection(data["mono_bytes"])
        if result > 0:
            index = result - 1
            spoken_keyword = (
                config["keywords"][index]
                if index < len(config["keywords"])
                else config["alert_keyword"]
            )
            context = _event_context(data)
            context["snowboy_keyword"] = spoken_keyword
            context["snowboy_sensitivity"] = sensitivity_controller.current_value
            dispatcher.submit(
                str(config["alert_keyword"]),
                float(config["confidence"]),
                "snowboy",
                context=context,
            )
        elif result == -1:
            print("Snowboy detection error", file=sys.stderr, flush=True)


def _event_context(data: dict[str, object]) -> dict[str, object]:
    context = {
        "direction": data.get("direction", "center"),
        "noise_level_db": data.get("noise_level_db", -90.0),
        "signal_level_db": data.get("signal_level_db", -90.0),
        "snr_db": data.get("snr_db", 0.0),
        "noise_reduction_db": data.get("noise_reduction_db", 0.0),
        "noise_suppression_active": data.get("noise_suppression_active", False),
        "suppression_strength": data.get("strength", 0.5),
        "suppression_sensitivity": data.get("sensitivity", 0.5),
        "openwakeword_available": data.get("openwakeword_available", False),
        "openwakeword_vad_score": data.get("openwakeword_vad_score", 0.0),
        "openwakeword_is_speech": data.get("openwakeword_is_speech", True),
        "openwakeword_model_dir": data.get("openwakeword_model_dir"),
        "openwakeword_discovered_models": data.get(
            "openwakeword_discovered_models",
            [],
        ),
        "openwakeword_loaded_models": data.get("openwakeword_loaded_models", []),
        "openwakeword_missing_models": data.get("openwakeword_missing_models", []),
        "openwakeword_skipped_models": data.get("openwakeword_skipped_models", {}),
        "openwakeword_wake_word": data.get("openwakeword_wake_word"),
        "openwakeword_wake_word_score": data.get(
            "openwakeword_wake_word_score",
            0.0,
        ),
        "openwakeword_wake_words": data.get("openwakeword_wake_words", []),
        "openwakeword_scores": data.get("openwakeword_scores", []),
    }
    openwakeword_error = data.get("openwakeword_error")
    if openwakeword_error:
        context["openwakeword_error"] = openwakeword_error
    sensitivity = data.get("snowboy_sensitivity")
    if sensitivity is not None:
        context["snowboy_sensitivity"] = sensitivity
    return context


def main() -> None:
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    vosk_model_path = Path(
        os.getenv("VOSK_MODEL_PATH", "/home/thesis/vosk-models/vosk-model-tl-ph-generic-0.6")
    )
    backend_url = os.getenv("BACKEND_ALERT_URL", "http://127.0.0.1:8765/api/alerts")
    queue_path = Path(os.getenv("ALERT_QUEUE_PATH", "/tmp/project_pi_alerts.jsonl"))
    audio_status_path = Path(
        os.getenv("PROJECT_PI_AUDIO_STATUS_PATH", str(DEFAULT_AUDIO_STATUS_PATH))
    )
    mic_hint = os.getenv("MIC_NAME_HINT", "seeed")
    sample_rate = int(os.getenv("KWS_SAMPLE_RATE", str(SAMPLE_RATE)))
    chunk_frames = int(os.getenv("KWS_CHUNK_FRAMES", str(CHUNK_FRAMES)))
    channels = int(os.getenv("KWS_CHANNELS", "2"))
    cooldown_seconds = float(os.getenv("KWS_COOLDOWN_SECONDS", "2.0"))
    debug = _env_bool("KWS_DEBUG", False)
    config_store = NoiseSuppressionConfigStore(
        Path(os.getenv("NOISE_SUPPRESSION_CONFIG_PATH", str(DEFAULT_CONFIG_PATH)))
    )
    current_noise_config = config_store.load()
    noise_suppressor = NoiseSuppressor(
        sample_rate=sample_rate,
        noise_reduction_strength=float(os.getenv("NOISE_SUPPRESSOR_STRENGTH", "0.70")),
        sensitivity=float(os.getenv("NOISE_SUPPRESSOR_SENSITIVITY", "0.50")),
        active=True,
        noise_profile_seconds=float(os.getenv("NOISE_PROFILE_SECONDS", "2.0")),
        profile_update_rate=float(os.getenv("NOISE_PROFILE_ADAPT_RATE", "0.05")),
    )
    noise_suppressor.apply_config(current_noise_config)
    openwakeword_enabled = _env_bool("OPENWAKEWORD_ENABLED", True)
    openwakeword_models_env = os.getenv("OPENWAKEWORD_MODELS")
    openwakeword_models = (
        _split_env(openwakeword_models_env)
        if openwakeword_models_env is not None
        else None
    )
    audio_preprocessor = AudioPreprocessor(
        wake_word_models=openwakeword_models,
        enabled=openwakeword_enabled,
        vad_threshold=float(os.getenv("OPENWAKEWORD_VAD_THRESHOLD", "0.40")),
        wake_word_threshold=float(os.getenv("OPENWAKEWORD_WAKE_THRESHOLD", "0.40")),
        wake_word_thresholds=_split_threshold_env(
            os.getenv("OPENWAKEWORD_MODEL_THRESHOLDS", "")
        ),
        enable_speex_noise_suppression=_env_bool(
            "OPENWAKEWORD_SPEEX_NOISE_SUPPRESSION",
            True,
        ),
    )
    print(
        "openWakeWord model directory: "
        f"{audio_preprocessor.model_dir}",
        flush=True,
    )
    if audio_preprocessor.discovered_wake_word_models:
        print(
            "openWakeWord discovered .onnx files: "
            f"{audio_preprocessor.discovered_wake_word_models}",
            flush=True,
        )
    if audio_preprocessor.available:
        loaded_openwakeword_models = audio_preprocessor.wake_word_models
        loaded_openwakeword_phrases = [
            _friendly_keyword(model_path)
            for model_path in loaded_openwakeword_models
        ]
        print(
            "openWakeWord ready: "
            f"models={loaded_openwakeword_models or ['vad-only']}, "
            f"phrases={loaded_openwakeword_phrases or ['vad-only']}, "
            f"vad={audio_preprocessor.vad_threshold:.2f}, "
            f"wake={audio_preprocessor.wake_word_threshold:.2f}",
            flush=True,
        )
        if audio_preprocessor.wake_word_thresholds:
            print(
                "openWakeWord per-model thresholds: "
                f"{audio_preprocessor.wake_word_thresholds}",
                flush=True,
            )
        if audio_preprocessor.missing_wake_word_models:
            print(
                "openWakeWord model files not found; skipped: "
                f"{audio_preprocessor.missing_wake_word_models}",
                flush=True,
            )
        if audio_preprocessor.skipped_wake_word_models:
            print(
                "openWakeWord model load warnings: "
                f"{audio_preprocessor.skipped_wake_word_models}",
                file=sys.stderr,
                flush=True,
            )
    elif openwakeword_enabled:
        print(
            "openWakeWord unavailable; continuing with Vosk/Snowboy only: "
            f"{audio_preprocessor.error}",
            file=sys.stderr,
            flush=True,
        )
    else:
        print("openWakeWord disabled; continuing with Vosk/Snowboy only", flush=True)
    noise_log_interval = float(os.getenv("NOISE_LOG_INTERVAL_SECONDS", "5.0"))
    openwakeword_score_log_threshold = float(
        os.getenv("OPENWAKEWORD_SCORE_LOG_THRESHOLD", "0.30")
    )
    adaptive_sensitivity = AdaptiveSnowboySensitivity(
        quiet_value=float(os.getenv("SNOWBOY_SENSITIVITY_QUIET", "0.38")),
        moderate_value=float(os.getenv("SNOWBOY_SENSITIVITY_MODERATE", "0.28")),
        noisy_value=float(os.getenv("SNOWBOY_SENSITIVITY_NOISY", "0.28")),
    )
    if current_noise_config.snowboy_sensitivity is not None:
        adaptive_sensitivity.apply_base_sensitivity(
            current_noise_config.snowboy_sensitivity
        )

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
    if len(snowboy_keywords) == 1 and len(snowboy_model_paths) > 1:
        snowboy_keywords = snowboy_keywords * len(snowboy_model_paths)
    if len(snowboy_keywords) != len(snowboy_model_paths):
        raise RuntimeError("SNOWBOY_KEYWORDS must match SNOWBOY_MODEL_PATHS")

    missing = [
        str(path)
        for path in [vosk_model_path, snowboy_resource_path, *snowboy_model_paths]
        if not path.exists()
    ]
    if missing:
        raise RuntimeError(f"Missing keyword model path(s): {', '.join(missing)}")

    poster = AlertPoster(backend_url, queue_path)
    cooldown = CooldownGate(cooldown_seconds)
    dispatcher = DetectionDispatcher(
        poster=poster,
        cooldown=cooldown,
        help_confirm_seconds=float(os.getenv("SNOWBOY_HELP_CONFIRM_SECONDS", "0.8")),
        help_suppress_after_tulong_seconds=float(
            os.getenv("SNOWBOY_SUPPRESS_AFTER_TULONG_SECONDS", "1.5")
        ),
    )
    vosk_queue: queue.Queue = queue.Queue(maxsize=32)
    snowboy_queue: queue.Queue = queue.Queue(maxsize=32)

    vosk_thread = threading.Thread(
        target=vosk_worker,
        args=(
            vosk_queue,
            dispatcher,
            {
                "model_path": vosk_model_path,
                "sample_rate": sample_rate,
                "confidence": float(os.getenv("VOSK_KEYWORD_CONFIDENCE", "0.40")),
                "debug": debug,
                "wav2vec2_enabled": _env_bool("WAV2VEC2_VERIFIER_ENABLED", True),
                "wav2vec2_verify_below_confidence": float(
                    os.getenv("WAV2VEC2_VERIFY_BELOW_CONFIDENCE", "0.70")
                ),
                "wav2vec2_context_seconds": float(
                    os.getenv("WAV2VEC2_CONTEXT_SECONDS", "2.0")
                ),
            },
        ),
        daemon=True,
    )
    snowboy_thread = threading.Thread(
        target=snowboy_worker,
        args=(
            snowboy_queue,
            dispatcher,
            {
                "swig_path": os.getenv("SNOWBOY_SWIG_PATH", "/home/thesis/snowboy/swig/Python3"),
                "examples_path": os.getenv(
                    "SNOWBOY_EXAMPLES_PATH", "/home/thesis/snowboy/examples/Python3"
                ),
                "resource_path": snowboy_resource_path,
                "model_paths": snowboy_model_paths,
                "keywords": snowboy_keywords,
                "alert_keyword": os.getenv("SNOWBOY_ALERT_KEYWORD", "help"),
                "audio_gain": float(os.getenv("SNOWBOY_AUDIO_GAIN", "1.0")),
                "confidence": float(os.getenv("SNOWBOY_CONFIDENCE", "0.95")),
                "sample_rate": sample_rate,
            },
            adaptive_sensitivity,
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
            channels=channels,
            format=pyaudio.paInt16,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=chunk_frames,
        )

        print(
            f"Capturing {noise_suppressor.noise_profile_seconds:.1f}s of ambient noise profile",
            flush=True,
        )
        while RUNNING and not noise_suppressor.profile_ready:
            data = stream.read(chunk_frames, exception_on_overflow=False)
            packet = split_audio_chunk(data, channels)
            noise_suppressor.capture_noise_profile(packet["raw_mono_samples"])

        vosk_thread.start()
        snowboy_thread.start()
        print(
            "Listening with openWakeWord as primary VAD/keyword engine; "
            "Vosk/Snowboy run only as speech fallback"
            + (
                f", {', '.join(audio_preprocessor.wake_word_models)} via openWakeWord"
                if audio_preprocessor.available and audio_preprocessor.wake_word_models
                else ""
            ),
            flush=True,
        )

        next_flush_at = 0.0
        next_noise_log_at = 0.0
        next_openwakeword_score_log_at = 0.0
        next_config_poll_at = 0.0
        while RUNNING:
            now = time.monotonic()
            if now >= next_config_poll_at:
                latest_config = config_store.load()
                if latest_config != current_noise_config:
                    current_noise_config = latest_config
                    noise_suppressor.apply_config(current_noise_config)
                    if current_noise_config.snowboy_sensitivity is not None:
                        adaptive_sensitivity.apply_base_sensitivity(
                            current_noise_config.snowboy_sensitivity
                        )
                    print(
                        "Updated live noise suppression settings: "
                        f"active={current_noise_config.active}, "
                        f"strength={current_noise_config.strength:.2f}, "
                        f"sensitivity={current_noise_config.sensitivity:.2f}, "
                        f"snowboy={current_noise_config.snowboy_sensitivity}",
                        flush=True,
                    )
                next_config_poll_at = now + 1.0

            data = stream.read(chunk_frames, exception_on_overflow=False)
            packet = split_audio_chunk(data, channels)
            raw_samples = packet["raw_mono_samples"]
            preprocessor_result = audio_preprocessor.process(raw_samples)
            speech_active = bool(preprocessor_result["is_speech"])
            cleaned_samples, metrics = noise_suppressor.process(raw_samples)
            preprocessed_samples = np.asarray(
                cleaned_samples,
                dtype=np.int16,
            )
            packet["mono_samples"] = preprocessed_samples
            packet["mono_bytes"] = preprocessed_samples.tobytes()

            noise_suppressor.update_noise_profile(raw_samples, is_speech=speech_active)
            packet.update(metrics)
            packet.update(audio_preprocessor.to_metrics(preprocessor_result))
            write_audio_status(audio_status_path, packet)
            adaptive_sensitivity.update_for_snr(float(packet.get("snr_db", 0.0)))

            openwakeword_matches: list[dict[str, object]] = []
            if speech_active:
                for wake_word in preprocessor_result["wake_words"]:
                    if not isinstance(wake_word, dict):
                        continue
                    score = float(wake_word.get("score", 0.0))
                    threshold = float(
                        wake_word.get(
                            "threshold",
                            audio_preprocessor.wake_word_threshold,
                        )
                    )
                    if score < threshold:
                        continue
                    openwakeword_matches.append(wake_word)

                openwakeword_posted = False
                openwakeword_matches.sort(
                    key=lambda wake_word: float(wake_word.get("score", 0.0)),
                    reverse=True,
                )
                for openwakeword_match in openwakeword_matches:
                    keyword = _friendly_keyword(
                        str(openwakeword_match.get("name", ""))
                    )
                    if not keyword:
                        continue
                    context = _event_context(packet)
                    context["openwakeword_model"] = keyword
                    print(
                        "openWakeWord detection: "
                        f"{keyword} "
                        f"score={float(openwakeword_match.get('score', 0.0)):.3f} "
                        f"threshold={float(openwakeword_match.get('threshold', 0.0)):.3f}",
                        flush=True,
                    )
                    dispatcher.submit(
                        keyword,
                        float(openwakeword_match.get("score", 0.0)),
                        "openwakeword",
                        context=context,
                    )
                    openwakeword_posted = True

                if not openwakeword_posted:
                    if now >= next_openwakeword_score_log_at:
                        openwakeword_scores = [
                            score
                            for score in packet.get("openwakeword_scores", [])
                            if isinstance(score, dict)
                            and float(score.get("score", 0.0))
                            >= openwakeword_score_log_threshold
                        ]
                        if openwakeword_scores:
                            openwakeword_scores.sort(
                                key=lambda score: float(score.get("score", 0.0)),
                                reverse=True,
                            )
                            formatted_scores = ", ".join(
                                f"{score.get('name')}="
                                f"{float(score.get('score', 0.0)):.3f}/"
                                f"{float(score.get('threshold', 0.0)):.3f}"
                                for score in openwakeword_scores[:5]
                            )
                            print(
                                "openWakeWord scores below threshold: "
                                f"{formatted_scores}",
                                flush=True,
                            )
                        next_openwakeword_score_log_at = now + 1.0
                    put_latest(vosk_queue, packet)
                    put_latest(snowboy_queue, packet)

            if now >= next_noise_log_at:
                print(
                    "Noise metrics: "
                    f"noise {packet['noise_level_db']:.1f} dB, "
                    f"signal {packet['signal_level_db']:.1f} dB, "
                    f"SNR {packet['snr_db']:.1f} dB, "
                    f"reduction {packet['noise_reduction_db']:.1f} dB, "
                    f"strength {packet['strength']:.2f}, "
                    f"sensitivity {packet['sensitivity']:.2f}",
                    flush=True,
                )
                next_noise_log_at = now + noise_log_interval

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
