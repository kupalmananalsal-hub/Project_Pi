#!/usr/bin/env python3
"""Replay recorded WAV files through the real keyword-spotting loop and score it.

Measurement only. The deployed loop (`kws_alert_dual.main`) runs unmodified with
its real engines (openWakeWord, noise suppressor, Vosk, Snowboy) and the real
`DetectionDispatcher` (cooldowns, Snowboy confirmation, "help" suppression).
Only the I/O edges are replaced: the microphone becomes a stream of WAV audio,
and the backend POST becomes an in-memory event recorder. No microphone is
opened, nothing is sent to the backend, no model or threshold is changed.

Fidelity, stated plainly:
- Isolation (default `--isolation per-recording`): every recording runs through
  its own `main()` with a fresh dispatcher, cooldown, Snowboy detector, pending
  "help" timer, noise suppressor and Vosk recognizer; the openWakeWord model is
  reused (loading it is slow) and `reset()` between recordings. This makes
  recordings independent samples. `--isolation continuous` instead streams all
  recordings back to back, which models one long listening session: Vosk partial
  text and openWakeWord buffers then carry across recordings.
- Audio: 16 kHz mono 16-bit PCM only. The mono signal is copied to every channel
  the unit configures (KWS_CHANNELS), so direction is always "center"; the last
  chunk is zero-padded; chunk size comes from the unit (KWS_CHUNK_FRAMES).
- Timing: paced in real time, because the worker threads and the Snowboy
  confirmation timer use the wall clock. The summary records the worst pacing
  lag; a lag above one chunk means the machine could not keep up, and the run is
  marked invalid as evidence. `--speed` other than 1.0 is never valid evidence.
- Dropped audio: the loop hands speech packets to the Vosk and Snowboy workers
  through bounded queues that discard the oldest packet when full. The harness
  counts every discarded packet, and every packet still queued when a run ends;
  either makes the run invalid as evidence.
- Configuration: `--env-file` (effective KEY=VALUE environment captured from the
  running service, see docs/m3_recognition_evidence_protocol.md) or `--unit`
  (Environment= lines of a unit file; ignores drop-ins and EnvironmentFile=).
  Noise-suppression settings come from `--noise-config`, a captured copy of the
  live settings file, frozen into a read-only snapshot; the live file is never read.
- Engines: the loop continues without an engine it cannot load (as on the Pi),
  which would silently measure a degraded detector. Every engine named in
  `--require-engines` (default all three) must load, or the run aborts.
- Evidence: `--evidence-mode preliminary` (default) reports detections only;
  folder names are provisional labels and no correctness metric is computed.
  `--evidence-mode validated` scores, and refuses to start unless every
  recording has asserted human-listening review and a supporting evidence reference
  in metadata.csv. These fields do not authenticate reviewers or prove ground truth.
- Safety: network connections are refused while the loop runs, outputs go to a
  scratch directory, and resource checks (memory, swap, temperature, scheduling
  lag) run before and during the replay so it cannot starve the live service.
  Run in a dedicated process with OS-level network/device/filesystem isolation:
  Python socket patches are defence in depth, not a sandbox for native libraries.
- Latency: from keyword onset when `--onsets` supplies annotated onsets,
  otherwise from recording start (labelled as such); measured to the moment the
  dispatcher publishes the alert.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import queue
import random
import shlex
import socket
import stat
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import types
import wave
from array import array
from datetime import datetime, timezone
from pathlib import Path

KWS_DIR = Path(__file__).resolve().parent
SAMPLE_RATE = 16000
ENGINES = ("openwakeword", "vosk", "snowboy")
PROTOCOL_DURATION_S = (1.0, 5.0)  # the protocol's recording length range
THREAD_STOP_TIMEOUT_S = 5.0
NOISE_CONFIG_FIELDS = ("active", "strength", "sensitivity", "snowboy_sensitivity")

# Resource limits. Preflight limits gate the start; abort limits stop a running replay.
DEFAULT_LIMITS = {
    "min_mem_available_mib": 1024.0,
    "max_swap_used_pct": 50.0,
    "max_memory_pressure_avg10": 5.0,
    "max_temperature_c": 70.0,
    "max_scheduling_lag_ms": 20.0,
    "abort_mem_available_mib": 512.0,
    "abort_temperature_c": 75.0,
}
# (reading, comparison, limit, required: False = checked only where the kernel exposes it)
PREFLIGHT_CHECKS = (
    ("mem_available_mib", ">=", "min_mem_available_mib", True),
    ("swap_used_pct", "<=", "max_swap_used_pct", True),
    ("memory_pressure_some_avg10", "<=", "max_memory_pressure_avg10", False),
    ("temperature_c", "<=", "max_temperature_c", True),
    ("scheduling_lag_ms", "<=", "max_scheduling_lag_ms", True),
)
RUNTIME_CHECKS = (
    ("mem_available_mib", ">=", "abort_mem_available_mib", True),
    ("temperature_c", "<=", "abort_temperature_c", True),
    ("swap_used_pct", "<=", "max_swap_used_pct", True),
    ("memory_pressure_some_avg10", "<=", "max_memory_pressure_avg10", False),
)


def parse_unit_environment(path: Path) -> dict[str, str]:
    """Environment= assignments of a systemd unit (drop-ins and EnvironmentFile= are not read)."""
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.startswith("Environment="):
            continue
        for item in shlex.split(line[len("Environment="):]):
            key, separator, value = item.partition("=")
            if separator:
                env[key.strip()] = value
    return env


def parse_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE lines, e.g. the effective engine environment captured from the running service."""
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            key, separator, value = line.partition("=")
            if separator:
                env[key.strip()] = value
    return env


def read_wav(path: Path) -> array:
    with wave.open(str(path), "rb") as handle:
        fmt = (handle.getframerate(), handle.getnchannels(), handle.getsampwidth())
        if fmt != (SAMPLE_RATE, 1, 2):
            raise ValueError(
                f"{path}: {fmt[0]} Hz, {fmt[1]} channel(s), {8 * fmt[2]}-bit; replay needs 16 kHz "
                "mono 16-bit PCM. Convert a copy offline as docs/m3_recognition_evidence_protocol.md "
                "describes; never replace the original.")
        count = handle.getnframes()
        raw = handle.readframes(count)
        if not count or len(raw) != count * 2 or handle.getcomptype() != "NONE":
            raise ValueError(f"{path}: empty, compressed or truncated WAV")
        samples = array("h")
        samples.frombytes(raw)
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Timeline:
    """Lead-in, then each recording followed by a silent gap, as one stream.

    A detection belongs to the latest recording that started before it (its own
    audio or the gap after it); detections during the lead-in belong to none.
    """

    def __init__(self, lead_in: array, recordings: list[array], gap_seconds: float):
        self.samples = array("h", lead_in)
        self.windows: list[tuple[float, float]] = []
        gap = array("h", bytes(2 * int(gap_seconds * SAMPLE_RATE)))
        for recording in recordings:
            start = len(self.samples) / SAMPLE_RATE
            self.samples.extend(recording)
            self.windows.append((start, len(self.samples) / SAMPLE_RATE))
            self.samples.extend(gap)

    def attribute(self, t: float) -> int | None:
        owner = None
        for index, (start, _end) in enumerate(self.windows):
            if t >= start:
                owner = index
        return owner


class ReplayStream:
    """Stands in for the PyAudio input stream: serves a timeline in real time."""

    def __init__(self, timeline: Timeline, channels: int, speed: float, on_end):
        self.timeline = timeline
        self.channels = max(1, channels)
        self.speed = speed
        self.on_end = on_end
        self.position = 0
        self.started_at: float | None = None
        self.max_lag_s = 0.0
        self.chunk_frames = 0
        self.lock = threading.Lock()

    def now(self) -> float:
        """Audio time (seconds) of the stream position: the detection clock."""
        with self.lock:
            return self.position / SAMPLE_RATE

    def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
        del exception_on_overflow
        self.chunk_frames = frames
        if self.started_at is None:
            self.started_at = time.monotonic()
        samples = self.timeline.samples
        with self.lock:
            start = self.position
            chunk = samples[start:start + frames]
            self.position = start + frames
            ended = self.position >= len(samples)
        if len(chunk) < frames:
            chunk.extend(array("h", bytes(2 * (frames - len(chunk)))))
        if ended:
            self.on_end()
        # When this read is due: the loop asks for the next chunk after processing the last.
        due = self.started_at + start / (SAMPLE_RATE * self.speed)
        self.max_lag_s = max(self.max_lag_s, time.monotonic() - due)
        delay = self.started_at + (start + frames) / (SAMPLE_RATE * self.speed) - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        if self.channels == 1:
            return chunk.tobytes()
        interleaved = array("h", bytes(2 * frames * self.channels))
        for channel in range(self.channels):
            interleaved[channel::self.channels] = chunk
        return interleaved.tobytes()

    def stop_stream(self) -> None:
        pass

    def close(self) -> None:
        pass


class ReplayPyAudio:
    def __init__(self, stream_factory):
        self.stream_factory = stream_factory

    def get_device_count(self) -> int:
        return 1

    def get_device_info_by_index(self, index: int) -> dict[str, object]:
        del index
        return {"name": "replay (seeed respeaker stand-in)", "maxInputChannels": 2}

    def open(self, **kwargs) -> ReplayStream:
        if int(kwargs.get("rate", SAMPLE_RATE)) != SAMPLE_RATE:
            raise ValueError("replay supports 16 kHz only")
        return self.stream_factory(int(kwargs.get("channels", 1)))

    def terminate(self) -> None:
        pass


class EventRecorder:
    """Stands in for AlertPoster: records what the loop would have POSTed, and when."""

    def __init__(self, clock):
        self.clock = clock
        self.lock = threading.Lock()
        self.events: list[dict[str, object]] = []
        self.scores: list[tuple[float, str, float]] = []
        self.drops: list[float] = []  # audio time of every packet discarded from a full engine queue

    def __call__(self, backend_url, queue_path, **kwargs):  # used in place of the AlertPoster class
        del backend_url, queue_path, kwargs
        return self

    def outbox_status(self) -> None:
        return None

    def start_worker(self) -> None:
        pass

    def stop_worker(self) -> None:
        pass

    def flush(self) -> None:
        pass

    def publish(self, keyword, confidence, source, *, direction="center", extra=None) -> None:
        del direction, extra
        with self.lock:
            self.events.append({"t": self.clock(), "keyword": str(keyword),
                                "confidence": float(confidence), "source": str(source)})

    def note_scores(self, scores) -> None:
        t = self.clock()
        with self.lock:
            for item in scores or []:
                if isinstance(item, dict):
                    self.scores.append((t, str(item.get("name", "")), float(item.get("score", 0.0))))

    def note_drop(self) -> None:
        t = self.clock()
        with self.lock:
            self.drops.append(t)


def dither(seconds: float, seed: int = 0) -> array:
    """Near-silent lead-in (+/-2 LSB) for the noise profile; exact zeros give it a degenerate spectrum."""
    rng = random.Random(seed)
    return array("h", (rng.randint(-2, 2) for _ in range(int(seconds * SAMPLE_RATE))))


class EngineCache:
    """Patches kws engine constructors: heavy models load once, and load status is recorded.

    Also replaces `put_latest` with a counting copy of the same behaviour, so a packet the
    loop discards from a full engine queue is recorded instead of silently lost.
    """

    def __init__(self, kws):
        self.kws = kws
        self.status = {name: False for name in ENGINES}
        self.openwakeword: dict[str, object] = {}
        self.preprocessor = None
        self.vosk_models: dict[str, object] = {}
        self.verifier = None
        self.recorder: EventRecorder | None = None
        self.queues: list[queue.Queue] = []  # engine queues fed during the current run

    def install(self):
        kws, cache = self.kws, self
        originals = {name: getattr(kws, name) for name in
                     ("AudioPreprocessor", "Model", "Wav2Vec2Verifier", "create_vosk_recognizer",
                      "import_snowboydetect", "put_latest")}

        def audio_preprocessor(**kwargs):
            if cache.preprocessor is None:
                cache.preprocessor = originals["AudioPreprocessor"](**kwargs)
                original_process = cache.preprocessor.process

                def process(frame):
                    result = original_process(frame)
                    if cache.recorder is not None:
                        cache.recorder.note_scores(result.get("scores"))
                    return result

                cache.preprocessor.process = process
            else:
                model = getattr(cache.preprocessor, "model", None)
                if hasattr(model, "reset"):
                    model.reset()  # clear openWakeWord feature/prediction buffers between recordings
            pre = cache.preprocessor
            cache.status["openwakeword"] = bool(getattr(pre, "available", False)) and bool(
                getattr(pre, "wake_word_models", []))
            cache.openwakeword = {
                "available": bool(getattr(pre, "available", False)),
                "loaded_models": list(getattr(pre, "wake_word_models", []) or []),
                "missing_models": list(getattr(pre, "missing_wake_word_models", []) or []),
                "skipped_models": dict(getattr(pre, "skipped_wake_word_models", {}) or {}),
                "thresholds": dict(getattr(pre, "wake_word_thresholds", {}) or {}),
                "error": getattr(pre, "error", None),
            }
            return pre

        def vosk_model(path):
            if path not in cache.vosk_models:
                cache.vosk_models[path] = originals["Model"](path)
            return cache.vosk_models[path]

        def verifier(**kwargs):
            if cache.verifier is None:
                cache.verifier = originals["Wav2Vec2Verifier"](**kwargs)
            return cache.verifier

        def create_vosk_recognizer(model_path, sample_rate):
            recognizer = originals["create_vosk_recognizer"](model_path, sample_rate)
            cache.status["vosk"] = True
            return recognizer

        def import_snowboydetect(swig_path, examples_path):
            module = originals["import_snowboydetect"](swig_path, examples_path)

            def detector(*args, **kwargs):
                instance = module.SnowboyDetect(*args, **kwargs)
                cache.status["snowboy"] = True
                return instance

            return types.SimpleNamespace(SnowboyDetect=detector)

        def put_latest(target_queue, data):
            # Same behaviour as kws_alert_dual.put_latest (keep the newest packet), plus a count.
            if not any(seen is target_queue for seen in cache.queues):
                cache.queues.append(target_queue)
            try:
                target_queue.put_nowait(data)
            except queue.Full:
                try:
                    target_queue.get_nowait()
                    if cache.recorder is not None:
                        cache.recorder.note_drop()
                except queue.Empty:
                    pass
                target_queue.put_nowait(data)

        kws.AudioPreprocessor = audio_preprocessor
        kws.Model = vosk_model
        kws.Wav2Vec2Verifier = verifier
        kws.create_vosk_recognizer = create_vosk_recognizer
        kws.import_snowboydetect = import_snowboydetect
        kws.put_latest = put_latest
        return originals


class NetworkGuard:
    """Refuses every IP connection and name lookup while active, loopback included.

    The live backend listens on 127.0.0.1, so a replay that reached it would raise a
    real alert. Refused attempts are recorded; any attempt invalidates the run.
    """

    METHODS = ("connect", "connect_ex", "sendto")

    def __init__(self):
        self.attempts: list[str] = []
        self.saved: dict[str, object] = {}

    def __enter__(self):
        self.saved = {name: getattr(socket.socket, name) for name in self.METHODS}
        self.saved["getaddrinfo"] = socket.getaddrinfo

        def refuse(what):
            self.attempts.append(what)
            raise PermissionError(f"replay_eval: network access is disabled during replay ({what})")

        def guarded(name):
            original = self.saved[name]

            def method(sock, *args):
                if sock.family in (socket.AF_INET, socket.AF_INET6):
                    refuse(f"{name} {args[-1]!r}" if args else name)
                return original(sock, *args)

            return method

        for name in self.METHODS:
            setattr(socket.socket, name, guarded(name))
        socket.getaddrinfo = lambda host, *args, **kwargs: refuse(f"getaddrinfo {host!r}")
        return self

    def __exit__(self, *exc):
        for name in self.METHODS:
            setattr(socket.socket, name, self.saved[name])
        socket.getaddrinfo = self.saved["getaddrinfo"]
        return False


def read_resources(root: Path = Path("/")) -> dict[str, float | None]:
    """Memory, swap, memory pressure and SoC temperature from /proc and /sys; None where unreadable."""
    reading: dict[str, float | None] = {"mem_available_mib": None, "swap_used_pct": None,
                                        "memory_pressure_some_avg10": None, "temperature_c": None}
    try:
        info = {}
        for line in (root / "proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition(":")
            if value.split():
                info[key] = int(value.split()[0])  # kB
        reading["mem_available_mib"] = round(info["MemAvailable"] / 1024, 1)
        swap_total = info.get("SwapTotal", 0)
        reading["swap_used_pct"] = (round(100 * (swap_total - info.get("SwapFree", 0)) / swap_total, 1)
                                    if swap_total else 0.0)
    except (OSError, KeyError, ValueError):
        pass
    try:  # "some avg10=0.00 avg60=0.00 avg300=0.00 total=0"
        first = (root / "proc/pressure/memory").read_text(encoding="utf-8").splitlines()[0]
        reading["memory_pressure_some_avg10"] = float(first.split()[1].partition("=")[2])
    except (OSError, IndexError, ValueError):
        pass
    try:
        temp = (root / "sys/class/thermal/thermal_zone0/temp").read_text(encoding="utf-8")
        reading["temperature_c"] = int(temp.strip()) / 1000
    except (OSError, ValueError):
        pass
    return reading


def read_throttled() -> int | None:
    """Raspberry Pi firmware throttle flags (`vcgencmd get_throttled`), None where unavailable."""
    try:
        output = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True,
                                timeout=5).stdout
        return int(output.strip().partition("=")[2], 16)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def scheduling_lag_ms(samples: int = 100, interval_s: float = 0.01) -> float:
    """Worst oversleep of short sleeps: how late this process gets the CPU back."""
    worst = 0.0
    for _ in range(samples):
        start = time.monotonic()
        time.sleep(interval_s)
        worst = max(worst, time.monotonic() - start - interval_s)
    return round(worst * 1000, 2)


def limit_failures(reading: dict[str, object], limits: dict[str, float], checks) -> list[str]:
    failures = []
    for key, comparison, limit_key, required in checks:
        value, limit = reading.get(key), limits[limit_key]
        if value is None:
            if required:
                failures.append(f"{key} unreadable")
        elif not (value >= limit if comparison == ">=" else value <= limit):
            failures.append(f"{key}={value} (limit {comparison} {limit})")
    throttled = reading.get("throttled")
    if throttled is not None and int(throttled) & 0xF:
        failures.append(f"throttled=0x{int(throttled):x} (under-voltage, frequency cap, throttling "
                        "or soft temperature limit active now)")
    return failures


def resource_preflight(limits: dict[str, float], root: Path = Path("/"), *,
                       throttled_reader=read_throttled, lag_reader=scheduling_lag_ms) -> dict[str, object]:
    reading: dict[str, object] = dict(read_resources(root))
    reading["throttled"] = throttled_reader()
    reading["scheduling_lag_ms"] = lag_reader()
    return {"reading": reading, "failures": limit_failures(reading, limits, PREFLIGHT_CHECKS)}


class ResourceWatchdog(threading.Thread):
    """Stops the replay loop if memory or temperature crosses an abort limit while it runs."""

    def __init__(self, kws, limits: dict[str, float], root: Path = Path("/"), interval_s: float = 2.0):
        super().__init__(name="replay-resource-watchdog", daemon=True)
        self.kws, self.limits, self.root, self.interval_s = kws, limits, root, interval_s
        self.reason: str | None = None
        self.finished = threading.Event()

    def check(self) -> bool:
        reading = dict(read_resources(self.root))
        reading["throttled"] = read_throttled()
        failures = limit_failures(reading, self.limits, RUNTIME_CHECKS)
        if failures:
            self.reason = "; ".join(failures)
            self.kws.RUNNING = False
        return bool(failures)

    def run(self) -> None:
        while not self.finished.wait(self.interval_s):
            if self.check():
                return


class ReplayAborted(RuntimeError):
    def __init__(self, reason: str, completed: int):
        super().__init__(f"replay aborted after {completed} run(s): {reason}")
        self.reason, self.completed = reason, completed


def _run_once(kws, cache: EngineCache, recordings: list[array], gap_seconds: float,
              lead_in: array, speed: float):
    timeline = Timeline(lead_in, recordings, gap_seconds)
    holder: dict[str, ReplayStream] = {}

    def stop() -> None:
        kws.RUNNING = False

    def make_stream(channels: int) -> ReplayStream:
        holder["stream"] = ReplayStream(timeline, channels, speed, stop)
        return holder["stream"]

    recorder = EventRecorder(lambda: holder["stream"].now() if "stream" in holder else 0.0)
    cache.recorder = recorder
    cache.queues = []
    kws.pyaudio = types.SimpleNamespace(PyAudio=lambda: ReplayPyAudio(make_stream), paInt16=8)
    kws.AlertPoster = recorder
    before = set(threading.enumerate())
    kws.RUNNING = True
    try:
        kws.main()
    finally:
        kws.RUNNING = False
        deadline = time.monotonic() + THREAD_STOP_TIMEOUT_S
        for thread in set(threading.enumerate()) - before:
            if thread is not threading.current_thread():
                thread.join(max(0.0, deadline - time.monotonic()))
    stream = holder.get("stream")
    pacing = {"max_lag_s": round(stream.max_lag_s, 4) if stream else None,
              "chunk_s": stream.chunk_frames / SAMPLE_RATE if stream else None,
              "queue_drops": len(recorder.drops),
              "unprocessed_packets": sum(q.qsize() for q in cache.queues),
              "threads_not_stopped": sorted(t.name for t in set(threading.enumerate()) - before
                                            if t.is_alive())}
    return timeline, recorder, pacing


def run_replay(kws, recordings: list[array], *, env: dict[str, str], gap_seconds: float,
               lead_in: array, speed: float = 1.0, isolate: bool = True,
               require_engines: tuple[str, ...] = ENGINES,
               abort_limits: dict[str, float] | None = None, resource_root: Path = Path("/")):
    """Run kws.main() over the recordings.

    Returns a list of (timeline, recorder, pacing) runs and the engine report:
    one run per recording when isolated, one run in total when continuous.
    With `abort_limits`, a watchdog stops the replay (ReplayAborted) if memory or
    temperature crosses them.
    """
    saved = {name: getattr(kws, name) for name in ("pyaudio", "AlertPoster", "RUNNING")}
    saved_env = {key: os.environ.get(key) for key in env}
    cache = EngineCache(kws)
    originals = {}
    runs = []
    watchdog = ResourceWatchdog(kws, abort_limits, resource_root) if abort_limits else None
    guard = NetworkGuard()
    try:
        os.environ.update(env)
        originals = cache.install()
        if watchdog and not watchdog.check():
            watchdog.start()
        batches = [[r] for r in recordings] if isolate else [recordings]
        with guard:
            for batch in batches:
                if watchdog and watchdog.reason:
                    raise ReplayAborted(watchdog.reason, len(runs))
                runs.append(_run_once(kws, cache, batch, gap_seconds, lead_in, speed))
                if watchdog and watchdog.reason:
                    raise ReplayAborted(watchdog.reason, len(runs))
                if runs[-1][2]["threads_not_stopped"]:
                    raise ReplayAborted("worker threads did not stop; do not reuse this process", len(runs))
                missing = [name for name in require_engines if not cache.status[name]]
                if missing:
                    raise RuntimeError(
                        f"Required engine(s) did not load: {missing}; openWakeWord: {cache.openwakeword}. "
                        "Measuring without them would report a degraded detector.")
    finally:
        if watchdog:
            watchdog.finished.set()
            if watchdog.is_alive():
                watchdog.join(THREAD_STOP_TIMEOUT_S)
        for name, value in {**saved, **originals}.items():
            setattr(kws, name, value)
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return runs, {"loaded": dict(cache.status), "openwakeword": cache.openwakeword,
                  "network_attempts": guard.attempts}


def duration_flag(seconds: float) -> str:
    low, high = PROTOCOL_DURATION_S
    return "under_1s" if seconds < low else "over_5s" if seconds > high else ""


def score_rows(items: list[dict[str, object]], runs):
    """Per-recording prediction rows plus every event, each tagged with its recording.

    Scoring conventions (label/score also usable by evaluate_keyword_models):
    - score (exact match): a positive recording scores 1 only if its own expected
      keyword fired; a different keyword is a miss (FN), never a TP. A negative
      recording scores 1 if any alert fired.
    - any_distress: 1 if any alert fired (system-level "an alarm was raised").
    - Extra or repeated detections never turn a miss into a hit; every event is
      kept in event_keyword_counts, and per-keyword scoring charges a wrongly
      predicted keyword as that keyword's FP.
    - Latency is measured to the first event of the expected keyword.
    - queue_drops: audio packets discarded from a full engine queue during the
      recording or its gap (any drop invalidates the run as evidence).
    Returns (rows, lead_in_events, tagged_events).
    """
    attributed: list[list[dict[str, object]]] = [[] for _ in items]
    max_scores: list[dict[str, float]] = [{} for _ in items]
    drops = [0 for _ in items]
    windows: list[tuple[float, float]] = []
    lead_in_events: list[dict[str, object]] = []
    offset = 0
    for timeline, recorder, _pacing in runs:
        for event in recorder.events:
            owner = timeline.attribute(float(event["t"]))
            if owner is None:
                lead_in_events.append(event)
            else:
                attributed[offset + owner].append(event)
        for t, name, score in recorder.scores:
            owner = timeline.attribute(t)
            if owner is not None:
                current = max_scores[offset + owner]
                current[name] = max(score, current.get(name, 0.0))
        for t in getattr(recorder, "drops", []):
            owner = timeline.attribute(t)
            if owner is not None:
                drops[offset + owner] += 1
        windows.extend(timeline.windows)
        offset += len(timeline.windows)

    rows = []
    tagged_events = [{**event, "path": None, "recording_t": None} for event in lead_in_events]
    for index, item in enumerate(items):
        start, end = windows[index]
        events = sorted(attributed[index], key=lambda e: e["t"])
        tagged_events.extend({**e, "path": item["path"], "recording_t": round(float(e["t"]) - start, 3)}
                             for e in events)
        keywords = list(dict.fromkeys(str(e["keyword"]) for e in events))
        keyword_counts: dict[str, int] = {}
        for event in events:
            keyword_counts[str(event["keyword"])] = keyword_counts.get(str(event["keyword"]), 0) + 1
        expected = str(item.get("expected_keyword") or "")
        is_positive = int(item["label"]) == 1
        matched = bool(expected) and expected in keywords
        matching = [e for e in events if str(e["keyword"]) == expected] if is_positive else events
        first = float(matching[0]["t"]) if matching else None
        onset = item.get("onset_s")
        rows.append({
            "path": item["path"],
            "label": item["label"],
            "category": item.get("category", ""),
            "score": 1.0 if (matched if is_positive else events) else 0.0,
            "any_distress": int(bool(events)),
            "event_count": len(events),
            "expected_keyword": expected,
            "expected_detected": int(matched),
            "wrong_keywords": ";".join(k for k in keywords if is_positive and k != expected),
            "detected_keywords": ";".join(keywords),
            "event_keyword_counts": ";".join(f"{k}={n}" for k, n in sorted(keyword_counts.items())),
            "sources": ";".join(dict.fromkeys(str(e["source"]) for e in events)),
            "latency_from_recording_start_s": round(first - start, 3) if first is not None else "",
            "latency_from_onset_s": (round(first - start - float(onset), 3)
                                     if first is not None and onset not in (None, "") else ""),
            "duration_s": round(end - start, 3),
            "duration_flag": duration_flag(end - start),
            "queue_drops": drops[index],
            "speaker_id": item.get("speaker_id", ""),
            "audio_sha256": item.get("audio_sha256", ""),
            "openwakeword_max_scores": ";".join(
                f"{name}={score:.4f}" for name, score in sorted(max_scores[index].items())),
        })
    return rows, lead_in_events, tagged_events


def _keyword_counts(row: dict[str, object]) -> dict[str, int]:
    counts = {}
    for part in filter(None, str(row.get("event_keyword_counts", "")).split(";")):
        keyword, _, count = part.rpartition("=")
        counts[keyword] = int(count)
    return counts


def _latency_stats(values):
    values = sorted(values)
    if not values:
        return {"count": 0, "median": None, "p90": None, "max": None}
    return {"count": len(values), "median": round(statistics.median(values), 3),
            "p90": round(values[int(0.9 * (len(values) - 1))], 3), "max": values[-1]}


def summarize(rows: list[dict[str, object]], lead_in_events: list[dict[str, object]]) -> dict[str, object]:
    from evaluate_keyword_models import compute_binary_metrics

    negatives = [r for r in rows if int(r["label"]) == 0]
    positives = [r for r in rows if int(r["label"]) == 1]
    negative_hours = sum(float(r["duration_s"]) for r in negatives) / 3600
    false_alarm_events = sum(int(r["event_count"]) for r in negatives)
    onset_latencies = [float(r["latency_from_onset_s"]) for r in positives if r["latency_from_onset_s"] != ""]
    start_latencies = [float(r["latency_from_recording_start_s"]) for r in positives
                       if r["latency_from_recording_start_s"] != ""]

    def speakers(group):
        return len({r["speaker_id"] for r in group if r["speaker_id"]})

    by_category: dict[str, dict[str, int]] = {}
    for row in negatives:
        entry = by_category.setdefault(str(row["category"]), {
            "recordings": 0, "false_positive_recordings": 0, "false_alarm_events": 0})
        entry["recordings"] += 1
        entry["false_positive_recordings"] += int(float(row["score"]) >= 0.5)
        entry["false_alarm_events"] += int(row["event_count"])

    false_alarm_events_by_keyword: dict[str, int] = {}
    for row in negatives:
        for keyword, count in _keyword_counts(row).items():
            false_alarm_events_by_keyword[keyword] = false_alarm_events_by_keyword.get(keyword, 0) + count

    # One binary problem per keyword: actual = recording's expected keyword is K,
    # predicted = K fired. A "help" recording that fires only "tulong" is an FN for
    # help and an FP for tulong.
    keywords = sorted({str(r["expected_keyword"]) for r in positives if r["expected_keyword"]}
                      | {k for r in rows for k in _keyword_counts(r)})
    per_keyword = {
        keyword: compute_binary_metrics(
            [{"label": int(r["expected_keyword"] == keyword), "score": float(keyword in _keyword_counts(r))}
             for r in rows],
            threshold=0.5)
        for keyword in keywords
    }

    return {
        # Primary, recording level, exact keyword: a positive is detected only when its
        # own keyword fires; a negative is a false positive when any alert fires.
        "exact_keyword": compute_binary_metrics(rows, threshold=0.5),
        # System level: was any distress alert raised, whichever keyword?
        "any_distress": compute_binary_metrics(
            [{"label": r["label"], "score": r["any_distress"]} for r in rows], threshold=0.5),
        "per_keyword": per_keyword,
        "positives_with_wrong_keyword_only": sum(
            1 for r in positives if int(r["any_distress"]) and not int(r["expected_detected"])),
        "positives_with_extra_keywords": sum(
            1 for r in positives if int(r["expected_detected"]) and r["wrong_keywords"]),
        # Event level: every alert the loop published during negative audio.
        "event_level": {
            "false_alarm_events": false_alarm_events,
            "false_alarm_events_by_keyword": dict(sorted(false_alarm_events_by_keyword.items())),
            "negative_audio_hours": round(negative_hours, 6),
            "false_alarm_events_per_hour": (round(false_alarm_events / negative_hours, 6)
                                            if negative_hours > 0 else None),
        },
        "latency": {
            "from_keyword_onset_s": _latency_stats(onset_latencies),
            "from_recording_start_s": _latency_stats(start_latencies),
            "note": ("to the first event of the expected keyword; from_keyword_onset_s needs "
                     "annotated onsets (--onsets); from_recording_start_s includes any silence "
                     "before the keyword"),
        },
        "recordings": {"positive": len(positives), "negative": len(negatives)},
        "speakers": {"positive": speakers(positives), "negative": speakers(negatives),
                     "total": speakers(rows)},
        "negatives_by_category": dict(sorted(by_category.items())),
        "lead_in_events": len(lead_in_events),
    }


PRELIMINARY_NOTICE = ("PRELIMINARY: recording labels are not human-verified (folder names are "
                      "provisional), so no correctness metric is computed. Not evidence of "
                      "detection accuracy or false-positive performance.")
PRELIMINARY_COLUMNS = {"label": "provisional_label", "expected_keyword": "provisional_keyword",
                       "expected_detected": "provisional_keyword_detected",
                       "wrong_keywords": "other_keywords"}


def preliminary_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Detections only: labels renamed as provisional and the correctness score removed."""
    return [{PRELIMINARY_COLUMNS.get(k, k): v for k, v in row.items() if k != "score"} for row in rows]


def preliminary_summary(rows: list[dict[str, object]], lead_in_events) -> dict[str, object]:
    events_by_keyword: dict[str, int] = {}
    for row in rows:
        for keyword, count in _keyword_counts(row).items():
            events_by_keyword[keyword] = events_by_keyword.get(keyword, 0) + count
    return {
        "evidence_status": "preliminary",
        "notice": PRELIMINARY_NOTICE,
        "metrics": None,
        "detections": {
            "recordings": len(rows),
            "recordings_with_any_alert": sum(int(r["any_distress"]) for r in rows),
            "alert_events": sum(int(r["event_count"]) for r in rows),
            "alert_events_by_keyword": dict(sorted(events_by_keyword.items())),
            "lead_in_events": len(lead_in_events),
            "recordings_outside_1_to_5_s": sum(1 for r in rows if r["duration_flag"]),
        },
    }


def unverified_items(items: list[dict[str, object]]) -> list[str]:
    """Reject unsupported review assertions; this does not authenticate their truth.

    A supporting review record is required, not inferred from text screening.
    Evidence references remain local and must be independently checked by researchers.
    """
    return [str(i["path"]) for i in items
            if i.get("review_status") != "verified"
            or i.get("reviewed_label") != ("positive" if int(i["label"]) == 1 else "negative")
            or i.get("review_method") != "human_listening"
            or str(i.get("review_evidence") or "").strip().casefold()
            in ("", "unknown", "unassessed", "n/a", "none", "not_checked")]


def invalid_reasons(run: dict[str, object]) -> list[str]:
    """Why a run is not valid evidence; empty means valid."""
    reasons = []
    if run.get("evidence_mode") != "validated":
        reasons.append("preliminary run: recording labels are not human-verified")
    if run.get("speed") != 1.0:
        reasons.append(f"speed {run.get('speed')} is not real time")
    if run.get("chunk_s") is None or float(run.get("max_pacing_lag_s") or 0.0) > float(run["chunk_s"]):
        reasons.append("the machine could not keep real time (pacing lag above one chunk)")
    if run.get("queue_drops"):
        reasons.append(f"{run['queue_drops']} audio packet(s) dropped from full engine queues")
    if run.get("unprocessed_packets"):
        reasons.append(f"{run['unprocessed_packets']} audio packet(s) still queued when a run ended")
    if run.get("threads_not_stopped"):
        reasons.append(f"threads still running after a run: {run['threads_not_stopped']}")
    if run.get("network_attempts"):
        reasons.append(f"{len(run['network_attempts'])} network access attempt(s) refused")
    if not run.get("noise_config_snapshot_unchanged"):
        reasons.append("noise-suppression snapshot changed or missing")
    if not run.get("configuration_unchanged", True):
        reasons.append("engine configuration or model hashes changed during replay")
    if run.get("unverified_model_assets"):
        reasons.append(f"model content provenance incomplete: {run['unverified_model_assets']}")
    if sorted(run.get("required_engines") or ()) != sorted(ENGINES):
        reasons.append("not all three engines were required to load")
    if run.get("resource_checks") != "passed":
        reasons.append(f"resource checks {run.get('resource_checks')}")
    return reasons


def load_items(dataset_dir: Path, *, split: str, subset: str | None, limit: int | None,
               onsets: dict[str, float]) -> list[dict[str, object]]:
    """Recordings from metadata.csv. dev: positive/ and negative/; holdout: physical_holdout/
    (laid out as physical_holdout/positive/<keyword>/ and physical_holdout/negative/<class>/)."""
    items = []
    with (dataset_dir / "metadata.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            path = row.get("path", "").replace("\\", "/")
            parts = path.split("/")
            if split == "holdout":
                if parts[0] != "physical_holdout":
                    continue
                parts = parts[1:]
            elif parts[0] == "physical_holdout":
                continue  # the untouched holdout never enters development runs
            if len(parts) < 3 or parts[0] not in ("positive", "negative"):
                continue
            if subset and subset not in path:
                continue
            candidate = Path(path)
            if (candidate.is_absolute() or ".." in candidate.parts or ":" in path
                    or not (dataset_dir / candidate).resolve().is_relative_to(dataset_dir.resolve())):
                raise ValueError(f"unsafe recording path: {path}")
            label = 1 if parts[0] == "positive" else 0
            items.append({
                "path": path, "label": label, "category": parts[1],
                "expected_keyword": row.get("keyword", "") if label else "",
                "speaker_id": row.get("speaker_id", ""), "onset_s": onsets.get(path),
                "review_status": (row.get("review_status") or "").strip(),
                "reviewed_label": (row.get("reviewed_label") or "").strip(),
                "review_method": (row.get("review_method") or "").strip(),
                "review_evidence": (row.get("review_evidence") or "").strip(),
            })
            if limit and len(items) >= limit:
                break
    return items


def load_onsets(path: Path | None) -> dict[str, float]:
    if path is None:
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["path"].replace("\\", "/"): float(row["onset_s"]) for row in csv.DictReader(handle)}


def isolate_environment(env: dict[str, str], scratch: Path,
                        noise_config: Path) -> tuple[dict[str, str], dict[str, object]]:
    """Point every output at scratch and freeze the noise settings into a read-only snapshot.

    The live loop polls its noise-settings file every second, and the app can change
    it at any time; the replay reads only the snapshot, so its settings cannot move.
    """
    snapshot = scratch / "noise_suppression_snapshot.json"
    snapshot.write_bytes(noise_config.read_bytes())
    snapshot.chmod(stat.S_IREAD)
    isolated = {
        **env,
        "NOISE_SUPPRESSION_CONFIG_PATH": str(snapshot),
        "PROJECT_PI_AUDIO_STATUS_PATH": str(scratch / "audio_status.json"),
        "ALERT_QUEUE_PATH": str(scratch / "alerts.jsonl"),
        "BACKEND_ALERT_URL": "http://127.0.0.1:9/replay-does-not-post",
        "PROJECT_PI_API_TOKEN": "",
        # Model loaders must use local files only (a hub download would leave the machine).
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
    }
    return isolated, {"noise_config_source": str(noise_config),
                      "noise_config_snapshot": str(snapshot),
                      "noise_config_snapshot_sha256": sha256_file(snapshot)}


def effective_noise_settings(kws, snapshot: Path) -> dict[str, object]:
    config = kws.NoiseSuppressionConfigStore(snapshot).load()
    return {name: getattr(config, name, None) for name in NOISE_CONFIG_FIELDS}


def import_kws():
    for path in (KWS_DIR, KWS_DIR.parent):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    try:
        return importlib.import_module("kws_alert_dual")
    except ImportError as exc:
        raise SystemExit(
            f"replay_eval: missing dependency {exc.name or exc!s}; run it with the deployed KWS "
            "environment (e.g. ~/kws-env/bin/python). Nothing was replayed.") from exc


def model_content_record(paths: list[Path]) -> dict[str, object]:
    """Stream selected files or complete directory trees; never follow symlinks.

    Per-file SHA-256 and a sorted manifest digest identify contents, not versions.
    Missing, unreadable or linked assets are explicitly unverified. Directory keys
    are relative to their root, so a Vosk model copied elsewhere keeps its digest.
    """
    files: dict[str, str] = {}
    issues: list[str] = []

    def add(path: Path, key: str) -> None:
        try:
            if path.is_symlink() or not path.is_file():
                issues.append(f"not a regular unlinked file: {key}")
            else:
                files[key] = sha256_file(path)
        except OSError as exc:
            issues.append(f"unreadable: {key} ({type(exc).__name__})")

    for path in paths:
        if path.is_symlink():
            issues.append(f"symlink not followed: {path}")
        elif path.is_dir():
            def scan_error(exc):
                issues.append(f"directory unreadable ({type(exc).__name__})")

            for directory, dirs, names in os.walk(path, followlinks=False, onerror=scan_error):
                for name in sorted(dirs):
                    if (Path(directory) / name).is_symlink():
                        issues.append(f"symlink not followed: {Path(directory) / name}")
                dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
                for name in sorted(names):
                    member = Path(directory) / name
                    key = member.relative_to(path).as_posix() if len(paths) == 1 else str(member)
                    add(member, key)
        else:
            add(path, str(path))
    manifest = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"paths": [str(p) for p in paths], "files_sha256": dict(sorted(files.items())),
            "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
            "status": "hashed" if files and not issues else "unverified",
            "issues": issues or ([] if files else ["no model files found"])}


def configuration_record(source: Path, env: dict[str, str]) -> dict[str, object]:
    # Match the deployed path selection without importing engines or loading assets.
    project = Path(env.get("PROJECT_PI_ROOT", str(KWS_DIR.parents[1]))).expanduser()
    dataset = Path(env.get("DATASET_DIR", str(project / "dataset"))).expanduser()
    default = dataset / "audio/openwakeword_models"
    legacy = project / "raspberry_pi/kws/openwakeword_models"
    model_dir = Path(env["OPENWAKEWORD_MODEL_DIR"]).expanduser() if env.get(
        "OPENWAKEWORD_MODEL_DIR") else (default if default.exists() or not legacy.exists() else legacy)
    explicit = env.get("OPENWAKEWORD_MODELS")
    oww_paths = ([Path(p.strip()) for p in explicit.split(",") if p.strip()] if explicit
                 else sorted(model_dir.glob("*.onnx")))
    # The deployed wrapper requires these external-weight companions for ONNX models.
    oww_paths += [Path(str(p) + ".data") for p in list(oww_paths) if p.suffix.lower() == ".onnx"]
    snowboy_paths = env.get("SNOWBOY_MODEL_PATHS", env.get("SNOWBOY_MODEL_PATH",
        "/home/thesis/snowboy/examples/Python3/resources/models/help.pmdl"))
    assets = {
        "openwakeword": model_content_record(oww_paths),
        "vosk": model_content_record([Path(env.get("VOSK_MODEL_PATH",
            "/home/thesis/vosk-models/vosk-model-tl-ph-generic-0.6"))]),
        "snowboy_models": model_content_record([Path(p.strip()) for p in snowboy_paths.split(",") if p.strip()]),
        "snowboy_resource": model_content_record([Path(env.get("SNOWBOY_RESOURCE_PATH",
            "/home/thesis/snowboy/examples/Python3/resources/common.res"))]),
    }
    versions = {}
    for package in ("vosk", "openwakeword", "onnxruntime", "numpy", "scipy", "torch", "transformers", "PyAudio"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    try:
        commit = subprocess.run(["git", "-C", str(KWS_DIR), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = ""
    keys = [k for k in env if not any(x in k.upper() for x in ("TOKEN", "SECRET", "PASSWORD")) and k.startswith(("OPENWAKEWORD_", "SNOWBOY_", "VOSK_", "KWS_",
                                            "NOISE_", "WAV2VEC2_"))]
    return {
        "config_source": str(source),
        "config_sha256": sha256_file(source),
        "engine_environment": {k: env[k] for k in sorted(keys)},
        "openwakeword_models_sha256": assets["openwakeword"]["files_sha256"],
        "model_content_provenance": assets,
        "unverified_model_assets": [name for name, record in assets.items() if record["status"] != "hashed"],
        "runtime_package_versions": versions,
        "unverified_components": ["package/native library contents (versions only)",
            "openWakeWord bundled embedding, melspectrogram and VAD assets",
            "Snowboy Python/SWIG/native bindings", "wav2vec2 model/cache assets", "OS/drivers/firmware"],
        "code_commit": commit,
    }


def parse_limit_overrides(values: list[str]) -> dict[str, float]:
    limits = dict(DEFAULT_LIMITS)
    for value in values:
        key, separator, number = value.partition("=")
        if not separator or key not in limits:
            raise ValueError(f"--resource-limit {value!r}: expected KEY=NUMBER with KEY in {sorted(limits)}")
        parsed = float(number)
        if not math.isfinite(parsed) or parsed < 0:
            raise ValueError(f"resource limit {key} must be finite and nonnegative")
        limits[key] = parsed
    return limits


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dataset-dir", type=Path, required=True,
                        help="keyword dataset root containing metadata.csv")
    config = parser.add_mutually_exclusive_group(required=True)
    config.add_argument("--env-file", type=Path,
                        help="effective engine environment (KEY=VALUE) captured from the running service")
    config.add_argument("--unit", type=Path, help="unit file; Environment= lines only")
    parser.add_argument("--noise-config", type=Path, required=True,
                        help="captured copy of the live noise-suppression settings JSON ({} if the "
                             "live file does not exist); frozen into a read-only snapshot")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--evidence-mode", choices=("preliminary", "validated"), default="preliminary",
                        help="preliminary: detections only; validated: scored, needs review_status=verified, "
                             "matching reviewed_label, review_method=human_listening and a supporting "
                             "review_evidence reference in metadata.csv (operator assertions, not proof)")
    parser.add_argument("--split", choices=("dev", "holdout"), default="dev",
                        help="dev: positive/ + negative/; holdout: physical_holdout/ (final report only)")
    parser.add_argument("--subset", help="only metadata paths containing this text, e.g. negative/hello")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--onsets", type=Path, help="CSV with path,onset_s keyword-onset annotations")
    parser.add_argument("--isolation", choices=("per-recording", "continuous"), default="per-recording")
    parser.add_argument("--require-engines", default=",".join(ENGINES),
                        help="comma list that must load; empty string disables the check")
    parser.add_argument("--gap-seconds", type=float, default=3.5,
                        help="silence after each recording; must exceed the 2.2 s suppression window")
    parser.add_argument("--lead-in-seconds", type=float, default=2.5,
                        help="near-silence before the audio, for the noise profile")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="1.0 = real time; any other value is not valid evidence")
    parser.add_argument("--resource-limit", action="append", default=[], metavar="KEY=NUMBER",
                        help=f"override a resource limit (defaults: {DEFAULT_LIMITS}); recorded in the summary")
    parser.add_argument("--skip-resource-checks", action="store_true",
                        help="development machines without Pi sensors only; the run is then not valid evidence")
    parser.add_argument("--nice", type=int, default=10,
                        help="lower this process's CPU priority so the live service keeps precedence (POSIX)")
    args = parser.parse_args(argv)
    try:
        limits = parse_limit_overrides(args.resource_limit)
    except ValueError as exc:
        parser.error(str(exc))
    for name in ("speed", "gap_seconds", "lead_in_seconds"):
        value = getattr(args, name)
        if not math.isfinite(value) or value < 0 or (name == "speed" and value == 0):
            parser.error(f"--{name.replace('_', '-')} must be finite and positive (zero allowed for gaps/lead-in)")
    if args.nice < 0:
        parser.error("--nice must not raise process priority")
    if args.out_dir.exists() and (not args.out_dir.is_dir() or any(args.out_dir.iterdir())):
        parser.error("--out-dir must be a new or empty directory; existing evidence is preserved")
    if not args.noise_config.is_file():
        parser.error(f"--noise-config {args.noise_config}: not a file (capture the live settings, or {{}})")

    items = load_items(args.dataset_dir, split=args.split, subset=args.subset, limit=args.limit,
                       onsets=load_onsets(args.onsets))
    if not items:
        parser.error("no recordings matched")
    if args.evidence_mode == "validated":
        unverified = unverified_items(items)
        if unverified:
            parser.error(f"--evidence-mode validated: {len(unverified)} of {len(items)} recordings lack a "
                         f"supported human-review assertion (first: {unverified[0]}); use --evidence-mode preliminary")
    recordings = [read_wav(args.dataset_dir / str(item["path"])) for item in items]
    for item in items:
        item["audio_sha256"] = sha256_file(args.dataset_dir / str(item["path"]))
    if args.skip_resource_checks:
        preflight = {"reading": None, "failures": []}
        resource_status = "skipped"
    else:
        preflight = resource_preflight(limits)
        if preflight["failures"]:
            print(json.dumps({"resource_preflight": preflight}, indent=2), file=sys.stderr)
            print("replay_eval: resource preflight failed; nothing was replayed", file=sys.stderr)
            return 3
        resource_status = "passed"
    if args.nice and hasattr(os, "nice"):
        os.nice(args.nice)

    source = args.env_file or args.unit
    supplied_env = parse_env_file(source) if args.env_file else parse_unit_environment(source)
    # Freeze inherited engine variables too; the main loop uses environment defaults.
    env = {**os.environ, **supplied_env}
    scratch = Path(tempfile.mkdtemp(prefix="kws-replay-"))
    env, isolation_record = isolate_environment(env, scratch, args.noise_config)
    frozen_configuration = configuration_record(source, env)
    snapshot = Path(isolation_record["noise_config_snapshot"])
    # Import under offline model-loader flags and network denial as well as replay.
    old_import_env = {k: os.environ.get(k) for k in env}
    import_guard = NetworkGuard()
    try:
        os.environ.update(env)
        with import_guard:
            kws = import_kws()
    finally:
        for key, value in old_import_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    isolate = args.isolation == "per-recording"
    audio = sum(len(r) for r in recordings) / SAMPLE_RATE + len(items) * args.gap_seconds
    if isolate:
        audio += len(items) * args.lead_in_seconds
    print(f"Replaying {len(items)} recordings ({args.isolation}, {args.evidence_mode}, "
          f"~{audio / args.speed / 60:.1f} min)", flush=True)

    started = datetime.now(timezone.utc).isoformat()
    required = tuple(name for name in args.require_engines.split(",") if name)
    try:
        runs, engines = run_replay(kws, recordings, env=env, gap_seconds=args.gap_seconds,
                                   lead_in=dither(args.lead_in_seconds), speed=args.speed,
                                   isolate=isolate, require_engines=required,
                                   abort_limits=None if args.skip_resource_checks else limits)
    except ReplayAborted as exc:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / "aborted.json").write_text(json.dumps(
            {"aborted": exc.reason, "completed_runs": exc.completed, "started_at": started,
             "valid_as_evidence": False}, indent=2) + "\n", encoding="utf-8")
        print(f"replay_eval: {exc}", file=sys.stderr)
        return 3
    rows, lead_in_events, tagged_events = score_rows(items, runs)

    max_lag = max((p["max_lag_s"] or 0.0) for _t, _r, p in runs)
    chunk_s = next((p["chunk_s"] for _t, _r, p in runs if p["chunk_s"]), None)
    run = {
        "started_at": started,
        "evidence_mode": args.evidence_mode,
        "isolation": args.isolation,
        "split": args.split,
        "speed": args.speed,
        "max_pacing_lag_s": max_lag,
        "chunk_s": chunk_s,
        "queue_drops": sum(p["queue_drops"] for _t, _r, p in runs),
        "unprocessed_packets": sum(p["unprocessed_packets"] for _t, _r, p in runs),
        "threads_not_stopped": sorted({n for _t, _r, p in runs for n in p["threads_not_stopped"]}),
        "network_attempts": import_guard.attempts + engines.pop("network_attempts"),
        "required_engines": list(required),
        "resource_checks": resource_status,
        "resource_limits": limits,
        "resource_preflight": preflight["reading"],
        "gap_seconds": args.gap_seconds,
        "lead_in_seconds": args.lead_in_seconds,
        "dataset_dir": str(args.dataset_dir),
        "subset": args.subset,
        "onsets": str(args.onsets) if args.onsets else None,
        **isolation_record,
        "noise_settings_effective": effective_noise_settings(kws, snapshot),
        "noise_config_snapshot_unchanged": (snapshot.exists() and sha256_file(snapshot)
                                            == isolation_record["noise_config_snapshot_sha256"]),
        **frozen_configuration,
        "configuration_unchanged": configuration_record(source, env) == frozen_configuration,
    }
    run["invalid_reasons"] = invalid_reasons(run)
    run["valid_as_evidence"] = not run["invalid_reasons"]

    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "events.jsonl").open("w", encoding="utf-8") as handle:
        for event in tagged_events:  # path = owning recording (null: lead-in)
            handle.write(json.dumps(event) + "\n")
    if args.evidence_mode == "validated" and run["valid_as_evidence"]:
        write_csv(args.out_dir / "predictions.csv", rows)
        summary = {"evidence_status": "validated", **summarize(rows, lead_in_events)}
        printed = ("evidence_status", "exact_keyword", "any_distress", "event_level", "recordings", "speakers")
    else:
        write_csv(args.out_dir / "preliminary_detections.csv", preliminary_rows(rows))
        summary = preliminary_summary(rows, lead_in_events)
        if args.evidence_mode == "validated":
            summary["evidence_status"] = "invalid"
            summary["notice"] = "INVALID RUN: correctness metrics withheld; see run.invalid_reasons"
        printed = ("evidence_status", "notice", "detections")
    summary["engines"] = engines
    summary["label_provenance"] = {
        "notice": "Metadata assertions are not independently authenticated ground truth; "
                  "researchers must verify supporting review records before publishing metrics.",
        "recordings": [{"path": i["path"], "audio_sha256": i["audio_sha256"],
                        **{k: i[k] for k in ("review_status", "reviewed_label", "review_method", "review_evidence")}}
                       for i in items],
    }
    summary["run"] = run
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in printed}, indent=2))
    if not run["valid_as_evidence"]:
        print("WARNING: run not valid as evidence: " + "; ".join(run["invalid_reasons"]), file=sys.stderr)
    return 3 if args.evidence_mode == "validated" and not run["valid_as_evidence"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
