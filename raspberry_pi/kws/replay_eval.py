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
- Configuration: `--env-file` (effective KEY=VALUE environment captured from the
  running service, see docs/m3_recognition_evidence_protocol.md) or `--unit`
  (Environment= lines of a unit file; ignores drop-ins and EnvironmentFile=).
- Engines: the loop continues without an engine it cannot load (as on the Pi),
  which would silently measure a degraded detector. Every engine named in
  `--require-engines` (default all three) must load, or the run aborts.
- Latency: from keyword onset when `--onsets` supplies annotated onsets,
  otherwise from recording start (labelled as such); measured to the moment the
  dispatcher publishes the alert.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import os
import random
import shlex
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
        if (handle.getframerate(), handle.getnchannels(), handle.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            raise ValueError(f"{path}: need 16 kHz mono 16-bit PCM")
        samples = array("h")
        samples.frombytes(handle.readframes(handle.getnframes()))
    if sys.byteorder == "big":
        samples.byteswap()
    return samples


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

    def __call__(self, backend_url, queue_path):  # used in place of the AlertPoster class
        del backend_url, queue_path
        return self

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


def dither(seconds: float, seed: int = 0) -> array:
    """Near-silent lead-in (+/-2 LSB) for the noise profile; exact zeros give it a degenerate spectrum."""
    rng = random.Random(seed)
    return array("h", (rng.randint(-2, 2) for _ in range(int(seconds * SAMPLE_RATE))))


class EngineCache:
    """Patches kws engine constructors: heavy models load once, and load status is recorded."""

    def __init__(self, kws):
        self.kws = kws
        self.status = {name: False for name in ENGINES}
        self.openwakeword: dict[str, object] = {}
        self.preprocessor = None
        self.vosk_models: dict[str, object] = {}
        self.verifier = None
        self.recorder: EventRecorder | None = None

    def install(self):
        kws, cache = self.kws, self
        originals = {name: getattr(kws, name) for name in
                     ("AudioPreprocessor", "Model", "Wav2Vec2Verifier", "create_vosk_recognizer",
                      "import_snowboydetect")}

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

        kws.AudioPreprocessor = audio_preprocessor
        kws.Model = vosk_model
        kws.Wav2Vec2Verifier = verifier
        kws.create_vosk_recognizer = create_vosk_recognizer
        kws.import_snowboydetect = import_snowboydetect
        return originals


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
    kws.pyaudio = types.SimpleNamespace(PyAudio=lambda: ReplayPyAudio(make_stream), paInt16=8)
    kws.AlertPoster = recorder
    kws.RUNNING = True
    kws.main()
    stream = holder.get("stream")
    pacing = {"max_lag_s": round(stream.max_lag_s, 4) if stream else None,
              "chunk_s": stream.chunk_frames / SAMPLE_RATE if stream else None}
    return timeline, recorder, pacing


def run_replay(kws, recordings: list[array], *, env: dict[str, str], gap_seconds: float,
               lead_in: array, speed: float = 1.0, isolate: bool = True,
               require_engines: tuple[str, ...] = ENGINES):
    """Run kws.main() over the recordings.

    Returns a list of (timeline, recorder, pacing) runs and the engine report:
    one run per recording when isolated, one run in total when continuous.
    """
    saved = {name: getattr(kws, name) for name in ("pyaudio", "AlertPoster", "RUNNING")}
    saved_env = {key: os.environ.get(key) for key in env}
    cache = EngineCache(kws)
    originals = {}
    runs = []
    try:
        os.environ.update(env)
        originals = cache.install()
        batches = [[r] for r in recordings] if isolate else [recordings]
        for batch in batches:
            runs.append(_run_once(kws, cache, batch, gap_seconds, lead_in, speed))
            missing = [name for name in require_engines if not cache.status[name]]
            if missing:
                raise RuntimeError(
                    f"Required engine(s) did not load: {missing}; openWakeWord: {cache.openwakeword}. "
                    "Measuring without them would report a degraded detector.")
    finally:
        for name, value in {**saved, **originals}.items():
            setattr(kws, name, value)
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return runs, {"loaded": dict(cache.status), "openwakeword": cache.openwakeword}


def score_rows(items: list[dict[str, object]], runs):
    """Per-recording prediction rows (label/score also usable by evaluate_keyword_models)."""
    attributed: list[list[dict[str, object]]] = [[] for _ in items]
    max_scores: list[dict[str, float]] = [{} for _ in items]
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
        windows.extend(timeline.windows)
        offset += len(timeline.windows)

    rows = []
    for index, item in enumerate(items):
        start, end = windows[index]
        events = sorted(attributed[index], key=lambda e: e["t"])
        keywords = list(dict.fromkeys(str(e["keyword"]) for e in events))
        expected = str(item.get("expected_keyword") or "")
        first = float(events[0]["t"]) if events else None
        onset = item.get("onset_s")
        rows.append({
            "path": item["path"],
            "label": item["label"],
            "category": item.get("category", ""),
            "score": 1.0 if events else 0.0,
            "event_count": len(events),
            "expected_keyword": expected,
            "expected_detected": int(bool(expected) and expected in keywords),
            "detected_keywords": ";".join(keywords),
            "sources": ";".join(dict.fromkeys(str(e["source"]) for e in events)),
            "latency_from_recording_start_s": round(first - start, 3) if first is not None else "",
            "latency_from_onset_s": (round(first - start - float(onset), 3)
                                     if first is not None and onset not in (None, "") else ""),
            "duration_s": round(end - start, 3),
            "speaker_id": item.get("speaker_id", ""),
            "openwakeword_max_scores": ";".join(
                f"{name}={score:.4f}" for name, score in sorted(max_scores[index].items())),
        })
    return rows, lead_in_events


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

    return {
        # Recording level: one row per recording; an alert anywhere in it is a detection.
        "recording_level": compute_binary_metrics(rows, threshold=0.5),
        # Event level: every alert the loop published during negative audio.
        "event_level": {
            "false_alarm_events": false_alarm_events,
            "negative_audio_hours": round(negative_hours, 6),
            "false_alarm_events_per_hour": (round(false_alarm_events / negative_hours, 6)
                                            if negative_hours > 0 else None),
        },
        "expected_keyword_recall": {
            "value": (round(sum(int(r["expected_detected"]) for r in positives) / len(positives), 6)
                      if positives else None),
            "denominator": len(positives),
        },
        "latency": {
            "from_keyword_onset_s": _latency_stats(onset_latencies),
            "from_recording_start_s": _latency_stats(start_latencies),
            "note": ("from_keyword_onset_s needs annotated onsets (--onsets); "
                     "from_recording_start_s includes any silence before the keyword"),
        },
        "recordings": {"positive": len(positives), "negative": len(negatives)},
        "speakers": {"positive": speakers(positives), "negative": speakers(negatives),
                     "total": speakers(rows)},
        "negatives_by_category": dict(sorted(by_category.items())),
        "false_alarm_events_by_keyword": _count_keywords(negatives),
        "lead_in_events": len(lead_in_events),
    }


def _count_keywords(rows):
    counts: dict[str, int] = {}
    for row in rows:
        for keyword in filter(None, str(row["detected_keywords"]).split(";")):
            counts[keyword] = counts.get(keyword, 0) + 1
    return dict(sorted(counts.items()))


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
            label = 1 if parts[0] == "positive" else 0
            items.append({
                "path": path, "label": label, "category": parts[1],
                "expected_keyword": row.get("keyword", "") if label else "",
                "speaker_id": row.get("speaker_id", ""), "onset_s": onsets.get(path),
            })
            if limit and len(items) >= limit:
                break
    return items


def load_onsets(path: Path | None) -> dict[str, float]:
    if path is None:
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["path"].replace("\\", "/"): float(row["onset_s"]) for row in csv.DictReader(handle)}


def configuration_record(source: Path, env: dict[str, str]) -> dict[str, object]:
    model_dir = Path(env.get("OPENWAKEWORD_MODEL_DIR", ""))
    models = {}
    if model_dir.is_dir():
        for path in sorted(model_dir.glob("*.onnx*")):
            models[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        commit = subprocess.run(["git", "-C", str(KWS_DIR), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = ""
    keys = [k for k in env if k.startswith(("OPENWAKEWORD_", "SNOWBOY_", "VOSK_", "KWS_",
                                            "NOISE_", "WAV2VEC2_"))]
    return {
        "config_source": str(source),
        "config_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "engine_environment": {k: env[k] for k in sorted(keys)},
        "openwakeword_models_sha256": models,
        "code_commit": commit,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dataset-dir", type=Path, required=True,
                        help="keyword dataset root containing metadata.csv")
    config = parser.add_mutually_exclusive_group(required=True)
    config.add_argument("--env-file", type=Path,
                        help="effective engine environment (KEY=VALUE) captured from the running service")
    config.add_argument("--unit", type=Path, help="unit file; Environment= lines only")
    parser.add_argument("--out-dir", type=Path, required=True)
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
    args = parser.parse_args(argv)

    items = load_items(args.dataset_dir, split=args.split, subset=args.subset, limit=args.limit,
                       onsets=load_onsets(args.onsets))
    if not items:
        parser.error("no recordings matched")
    recordings = [read_wav(args.dataset_dir / str(item["path"])) for item in items]
    source = args.env_file or args.unit
    env = parse_env_file(source) if args.env_file else parse_unit_environment(source)
    scratch = Path(tempfile.mkdtemp(prefix="kws-replay-"))
    # Never touch the live service's files or post anywhere.
    env.update({
        "PROJECT_PI_AUDIO_STATUS_PATH": str(scratch / "audio_status.json"),
        "ALERT_QUEUE_PATH": str(scratch / "alerts.jsonl"),
        "BACKEND_ALERT_URL": "http://127.0.0.1:9/replay-does-not-post",
        "PROJECT_PI_API_TOKEN": "",
    })
    isolate = args.isolation == "per-recording"
    audio = sum(len(r) for r in recordings) / SAMPLE_RATE + len(items) * args.gap_seconds
    if isolate:
        audio += len(items) * args.lead_in_seconds
    print(f"Replaying {len(items)} recordings ({args.isolation}, ~{audio / args.speed / 60:.1f} min)",
          flush=True)

    for path in (KWS_DIR, KWS_DIR.parent):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    kws = importlib.import_module("kws_alert_dual")
    started = datetime.now(timezone.utc).isoformat()
    required = tuple(name for name in args.require_engines.split(",") if name)
    runs, engines = run_replay(kws, recordings, env=env, gap_seconds=args.gap_seconds,
                               lead_in=dither(args.lead_in_seconds), speed=args.speed,
                               isolate=isolate, require_engines=required)
    rows, lead_in_events = score_rows(items, runs)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (args.out_dir / "events.jsonl").open("w", encoding="utf-8") as handle:
        for _timeline, recorder, _pacing in runs:
            for event in recorder.events:
                handle.write(json.dumps(event) + "\n")
    max_lag = max((p["max_lag_s"] or 0.0) for _t, _r, p in runs)
    chunk_s = next((p["chunk_s"] for _t, _r, p in runs if p["chunk_s"]), None)
    summary = summarize(rows, lead_in_events)
    summary["engines"] = engines
    summary["run"] = {
        "started_at": started,
        "isolation": args.isolation,
        "split": args.split,
        "speed": args.speed,
        "max_pacing_lag_s": max_lag,
        "chunk_s": chunk_s,
        "valid_as_evidence": args.speed == 1.0 and chunk_s is not None and max_lag <= chunk_s,
        "gap_seconds": args.gap_seconds,
        "lead_in_seconds": args.lead_in_seconds,
        "dataset_dir": str(args.dataset_dir),
        "subset": args.subset,
        "onsets": str(args.onsets) if args.onsets else None,
        **configuration_record(source, env),
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("recording_level", "event_level", "recordings", "speakers")},
                     indent=2))
    if not summary["run"]["valid_as_evidence"]:
        print("WARNING: run not valid as evidence (speed != 1.0 or the machine could not keep real time)",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
