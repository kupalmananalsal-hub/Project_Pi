"""Replay harness: drives the real kws_alert_dual.main() with FAKE engines.

These tests check the harness plumbing (stream, isolation, attribution, metrics).
They say nothing about recognition accuracy: no real openWakeWord, Vosk or
Snowboy model runs here.
"""
import importlib.util
import math
import os
import sys
import json
import queue
import socket
import stat
import tempfile
import time
import types
import unittest
from unittest.mock import patch
import wave
from array import array
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KWS_DIR = PROJECT_ROOT / "raspberry_pi" / "kws"
sys.path.insert(0, str(KWS_DIR))

import replay_eval  # noqa: E402

LOUD = 4000  # the fake openWakeWord "hears help" above this RMS
LIVE_IO = []  # set if the loop ever reached the real microphone or HTTP client


class FakeConfig:
    active, strength, sensitivity, snowboy_sensitivity = True, 0.5, 0.5, None


class FakeConfigStore:
    paths = []  # every settings file the loop was pointed at

    def __init__(self, path):
        FakeConfigStore.paths.append(Path(path))
        self.config = FakeConfig()

    def load(self):
        return self.config


class FakeNoiseSuppressor:
    noise_profile_seconds = 0.1

    def __init__(self, **kwargs):
        self.profile_ready = False

    def apply_config(self, config):
        pass

    def capture_noise_profile(self, samples):
        self.profile_ready = True

    def process(self, samples):
        return samples, {"noise_level_db": -60.0, "signal_level_db": -20.0, "snr_db": 40.0,
                         "noise_reduction_db": 0.0, "noise_suppression_active": True,
                         "strength": 0.5, "sensitivity": 0.5}

    def update_noise_profile(self, samples, is_speech):
        pass


class FakeOwwModel:
    resets = 0

    def reset(self):
        FakeOwwModel.resets += 1


class FakeAudioPreprocessor:
    """openWakeWord stand-in: 'help' scores 0.9 on loud frames."""
    available = True

    def __init__(self, **kwargs):
        self.model = FakeOwwModel()
        self.model_dir = "fake"
        self.discovered_wake_word_models = ["help.onnx"]
        self.available = type(self).available
        self.wake_word_models = ["help.onnx"] if self.available else []
        self.vad_threshold = 0.4
        self.wake_word_threshold = 0.3
        self.wake_word_thresholds = {"help": 0.3}
        self.missing_wake_word_models = []
        self.skipped_wake_word_models = {}
        self.error = None if self.available else "fake: not loaded"

    def process(self, frame):
        rms = math.sqrt(float(np.mean(np.square(np.asarray(frame, dtype=np.float64))))) if len(frame) else 0.0
        loud = rms > LOUD
        score = {"name": "help", "raw_name": "help", "score": 0.9 if loud else 0.05, "threshold": 0.3}
        return {"available": True, "is_speech": loud, "vad_score": 1.0 if loud else 0.0,
                "wake_words": [score] if loud else [], "scores": [score] if loud else []}

    def to_metrics(self, result):
        return {"openwakeword_available": True}


class FakeRecognizer:
    delay_s = 0.0  # > 0 makes the Vosk worker slower than real time, so its queue overflows

    def __init__(self, model, rate):
        pass

    def SetWords(self, value):
        pass

    def AcceptWaveform(self, data):
        if FakeRecognizer.delay_s:
            time.sleep(FakeRecognizer.delay_s)
        return False

    def PartialResult(self):
        return '{"partial": ""}'

    def Result(self):
        return '{"text": ""}'

    def Reset(self):
        pass


class FakeSnowboy:
    def __init__(self, resource, models):
        pass

    def SetAudioGain(self, gain):
        pass

    def SetSensitivity(self, value):
        pass

    def SampleRate(self):
        return 16000

    def RunDetection(self, data):
        return 0


def load_kws_with_fake_engines(kws_dir=KWS_DIR, preprocessor=FakeAudioPreprocessor):
    stubs = {name: types.ModuleType(name) for name in
             ("vosk", "audio_preprocessor", "noise_suppressor", "wav2vec2_verifier",
              "pyaudio", "requests", "snowboydetect")}
    stubs["vosk"].Model = lambda path: object()
    stubs["vosk"].KaldiRecognizer = FakeRecognizer
    stubs["audio_preprocessor"].AudioPreprocessor = preprocessor
    stubs["noise_suppressor"].DEFAULT_CONFIG_PATH = Path("noise.json")
    stubs["noise_suppressor"].NoiseSuppressionConfigStore = FakeConfigStore
    stubs["noise_suppressor"].NoiseSuppressor = FakeNoiseSuppressor
    stubs["wav2vec2_verifier"].Wav2Vec2Verifier = object
    stubs["pyaudio"].PyAudio = lambda: LIVE_IO.append("microphone opened")
    stubs["requests"].Session = lambda: LIVE_IO.append("HTTP session created")
    stubs["snowboydetect"].SnowboyDetect = FakeSnowboy
    name = "kws_replay_under_test"
    previous = {key: sys.modules.get(key) for key in (*stubs, name)}
    sys.modules.update(stubs)
    spec = importlib.util.spec_from_file_location(name, Path(kws_dir) / "kws_alert_dual.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module, previous


def restore(previous):
    for name, module in previous.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def tone(seconds, amplitude):
    n = int(seconds * replay_eval.SAMPLE_RATE)
    return array("h", (int(amplitude * math.sin(2 * math.pi * 440 * i / replay_eval.SAMPLE_RATE)) for i in range(n)))


def fake_env(temp: Path) -> dict:
    for name in ("vosk-model", "common.res", "help.pmdl"):
        (temp / name).write_text("fake")
    return {
        "VOSK_MODEL_PATH": str(temp / "vosk-model"),
        "SNOWBOY_RESOURCE_PATH": str(temp / "common.res"),
        "SNOWBOY_MODEL_PATHS": str(temp / "help.pmdl"),
        "SNOWBOY_SWIG_PATH": str(temp), "SNOWBOY_EXAMPLES_PATH": str(temp),
        "WAV2VEC2_VERIFIER_ENABLED": "0", "KWS_CHANNELS": "2", "KWS_CHUNK_FRAMES": "1280",
        "KWS_COOLDOWN_SECONDS": "2.0",
        "PROJECT_PI_AUDIO_STATUS_PATH": str(temp / "status.json"),
        "NOISE_SUPPRESSION_CONFIG_PATH": str(temp / "noise.json"),
    }


def replay(recordings, items, *, kws_dir=KWS_DIR, isolate=True, gap=0.6,
           preprocessor=FakeAudioPreprocessor, speed=1.0):
    kws, previous = load_kws_with_fake_engines(kws_dir, preprocessor)
    try:
        with tempfile.TemporaryDirectory() as temp:
            runs, engines = replay_eval.run_replay(
                kws, recordings, env=fake_env(Path(temp)), gap_seconds=gap,
                lead_in=replay_eval.dither(0.3), isolate=isolate, speed=speed)
    finally:
        restore(previous)
    rows, lead_in_events, _tagged = replay_eval.score_rows(items, runs)
    return rows, lead_in_events, runs, engines


def synthetic_runs(durations, events, gap=3.5, lead_in=1.0):
    """One continuous run with silent recordings and hand-placed alerts.

    events: (recording index, seconds after that recording starts, keyword).
    """
    sr = replay_eval.SAMPLE_RATE
    timeline = replay_eval.Timeline(array("h", bytes(2 * int(lead_in * sr))),
                                    [array("h", bytes(2 * int(d * sr))) for d in durations], gap)
    recorder = types.SimpleNamespace(scores=[], events=[
        {"t": timeline.windows[i][0] + dt, "keyword": k, "confidence": 0.9, "source": "openwakeword"}
        for i, dt, k in events])
    return [(timeline, recorder, {"max_lag_s": 0.0, "chunk_s": 0.08})]


def item(path, label, keyword="", speaker="sp", onset=None):
    return {"path": path, "label": label, "category": path.split("/")[1],
            "expected_keyword": keyword, "speaker_id": speaker, "onset_s": onset}


class ReplayHarnessTest(unittest.TestCase):
    def test_unit_environment_matches_tracked_service(self):
        env = replay_eval.parse_unit_environment(PROJECT_ROOT / "raspberry_pi/systemd/kws-alert.service")
        self.assertEqual(env["KWS_CHANNELS"], "2")
        self.assertIn("tulong=0.20", env["OPENWAKEWORD_MODEL_THRESHOLDS"])
        self.assertIn("ang sakit=0.20", env["OPENWAKEWORD_MODEL_THRESHOLDS"])  # quoted value with a space

    def test_env_file_parser_reads_captured_effective_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "effective.env"
            path.write_text("# captured\nOPENWAKEWORD_MODEL_THRESHOLDS=tulong=0.20,ang sakit=0.20\nKWS_CHANNELS=2\n")
            env = replay_eval.parse_env_file(path)
        self.assertEqual(env["OPENWAKEWORD_MODEL_THRESHOLDS"], "tulong=0.20,ang sakit=0.20")
        self.assertEqual(env["KWS_CHANNELS"], "2")

    def test_detections_are_attributed_to_the_recording_whose_gap_they_fall_in(self):
        timeline = replay_eval.Timeline(array("h", bytes(2 * 16000)),
                                        [array("h", bytes(2 * 8000))] * 2, gap_seconds=2.0)
        self.assertEqual(timeline.windows, [(1.0, 1.5), (3.5, 4.0)])
        self.assertIsNone(timeline.attribute(0.5))
        self.assertEqual(timeline.attribute(3.4), 0)
        self.assertEqual(timeline.attribute(3.6), 1)

    def test_real_kws_loop_scores_a_positive_and_a_negative(self):
        items = [item("positive/help/a.wav", 1, "help", "sp1", onset=0.1),
                 item("negative/silence/b.wav", 0, speaker="sp2")]
        rows, lead_in_events, runs, engines = replay(
            [tone(0.6, 12000), tone(0.6, 30)], items)
        self.assertEqual(len(runs), 2)  # isolated: one main() per recording
        self.assertEqual(engines["loaded"], {"openwakeword": True, "vosk": True, "snowboy": True})
        self.assertEqual([r["score"] for r in rows], [1.0, 0.0])
        self.assertEqual(rows[0]["detected_keywords"], "help")
        self.assertEqual(rows[0]["sources"], "openwakeword")
        self.assertNotEqual(rows[0]["latency_from_onset_s"], "")
        self.assertAlmostEqual(float(rows[0]["latency_from_recording_start_s"]) - 0.1,
                               float(rows[0]["latency_from_onset_s"]), places=3)
        self.assertIn("help=0.9000", rows[0]["openwakeword_max_scores"])
        self.assertEqual(lead_in_events, [])

        summary = replay_eval.summarize(rows, lead_in_events)
        metrics = summary["exact_keyword"]
        self.assertEqual((metrics["true_positives"], metrics["true_negatives"],
                          metrics["false_positives"], metrics["false_negatives"]), (1, 1, 0, 0))
        self.assertEqual(metrics["denominators"]["recall"], 1)
        self.assertEqual(summary["speakers"], {"positive": 1, "negative": 1, "total": 2})
        self.assertEqual(summary["latency"]["from_keyword_onset_s"]["count"], 1)

    def test_isolation_does_not_carry_cooldown_between_recordings(self):
        # Two 'help' recordings 0.6 s apart: continuous replay hits the 2 s keyword
        # cooldown, isolated replay scores each recording on its own.
        items = [item("positive/help/a.wav", 1, "help"), item("positive/help/b.wav", 1, "help")]
        recordings = [tone(0.4, 12000), tone(0.4, 12000)]
        isolated, _, _, _ = replay(recordings, items, isolate=True)
        continuous, _, _, _ = replay(recordings, items, isolate=False)
        self.assertEqual([r["score"] for r in isolated], [1.0, 1.0])
        self.assertEqual([r["score"] for r in continuous], [1.0, 0.0])

    def test_openwakeword_model_is_reset_between_isolated_recordings(self):
        FakeOwwModel.resets = 0
        items = [item("negative/silence/a.wav", 0), item("negative/silence/b.wav", 0),
                 item("negative/silence/c.wav", 0)]
        replay([tone(0.2, 10)] * 3, items)
        self.assertEqual(FakeOwwModel.resets, 2)  # loaded once, reset before runs 2 and 3

    def test_missing_required_engine_aborts_instead_of_measuring_a_degraded_detector(self):
        class Unavailable(FakeAudioPreprocessor):
            available = False

        with self.assertRaisesRegex(RuntimeError, "openwakeword"):
            replay([tone(0.2, 10)], [item("negative/silence/a.wav", 0)], preprocessor=Unavailable)

    def test_repeated_false_alarms_are_all_counted_per_keyword_and_traceable(self):
        # Review finding 2: three false 'help' alerts in one negative WAV must count 3 in the
        # per-keyword breakdown (it used to say 1) and agree with the event total.
        items = [item("negative/hello/a.wav", 0, speaker="s1"), item("negative/hi/b.wav", 0, speaker="s2")]
        rows, lead_in, tagged = replay_eval.score_rows(
            items, synthetic_runs([1800.0, 1800.0],
                                  [(0, 0.5, "help"), (0, 10.0, "help"), (0, 20.0, "help")]))
        summary = replay_eval.summarize(rows, lead_in)
        self.assertEqual(rows[0]["event_keyword_counts"], "help=3")
        self.assertEqual(summary["exact_keyword"]["false_positives"], 1)  # one recording
        self.assertEqual(summary["event_level"]["false_alarm_events"], 3)  # three alerts
        self.assertEqual(summary["event_level"]["false_alarm_events_by_keyword"], {"help": 3})
        self.assertEqual(sum(summary["event_level"]["false_alarm_events_by_keyword"].values()),
                         summary["event_level"]["false_alarm_events"])
        self.assertEqual(summary["event_level"]["false_alarm_events_per_hour"], 3.0)  # 3 events / 1 h
        self.assertEqual(summary["negatives_by_category"]["hello"],
                         {"recordings": 1, "false_positive_recordings": 1, "false_alarm_events": 3})
        # Every exported event names its recording.
        self.assertEqual([e["path"] for e in tagged], ["negative/hello/a.wav"] * 3)
        self.assertEqual([e["recording_t"] for e in tagged], [0.5, 10.0, 20.0])
        # No positives: recall-side metrics are not estimable, never 0.
        self.assertIsNone(summary["exact_keyword"]["recall"])
        self.assertIsNone(summary["exact_keyword"]["false_negative_rate"])
        self.assertIsNone(summary["latency"]["from_recording_start_s"]["median"])

    def test_wrong_keyword_on_a_positive_is_a_miss_not_a_hit(self):
        # Review finding 1: a 'help' recording that only fires 'tulong' is an FN for the
        # exact-keyword metric (and for help), an FP for tulong, and still an alarm at
        # system level.
        items = [item("positive/help/a.wav", 1, "help", onset=0.2),
                 item("positive/tulong/b.wav", 1, "tulong"),
                 item("negative/hi/c.wav", 0)]
        rows, lead_in, _ = replay_eval.score_rows(
            items, synthetic_runs([1.0, 1.0, 1.0], [(0, 0.6, "tulong"), (1, 0.5, "tulong")]))
        summary = replay_eval.summarize(rows, lead_in)
        self.assertEqual(rows[0]["score"], 0.0)
        self.assertEqual(rows[0]["any_distress"], 1)
        self.assertEqual(rows[0]["wrong_keywords"], "tulong")
        self.assertEqual(rows[0]["latency_from_onset_s"], "")  # the wrong keyword is not a detection
        exact = summary["exact_keyword"]
        self.assertEqual((exact["true_positives"], exact["false_negatives"],
                          exact["false_positives"], exact["true_negatives"]), (1, 1, 0, 1))
        any_distress = summary["any_distress"]
        self.assertEqual((any_distress["true_positives"], any_distress["false_negatives"]), (2, 0))
        help_metrics, tulong_metrics = summary["per_keyword"]["help"], summary["per_keyword"]["tulong"]
        self.assertEqual((help_metrics["true_positives"], help_metrics["false_negatives"],
                          help_metrics["false_positives"], help_metrics["true_negatives"]), (0, 1, 0, 2))
        self.assertEqual((tulong_metrics["true_positives"], tulong_metrics["false_negatives"],
                          tulong_metrics["false_positives"], tulong_metrics["true_negatives"]), (1, 0, 1, 1))
        self.assertEqual(summary["positives_with_wrong_keyword_only"], 1)
        self.assertEqual(summary["latency"]["from_recording_start_s"]["count"], 1)  # tulong recording only

    def test_extra_keyword_does_not_undo_a_correct_detection(self):
        items = [item("positive/help/a.wav", 1, "help")]
        rows, lead_in, _ = replay_eval.score_rows(
            items, synthetic_runs([1.0], [(0, 0.3, "tulong"), (0, 0.5, "help")]))
        summary = replay_eval.summarize(rows, lead_in)
        self.assertEqual(rows[0]["score"], 1.0)
        self.assertEqual(rows[0]["latency_from_recording_start_s"], 0.5)  # first *help* event
        self.assertEqual(summary["positives_with_extra_keywords"], 1)
        self.assertEqual(summary["per_keyword"]["tulong"]["false_positives"], 1)

    def test_holdout_is_excluded_from_development_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "metadata.csv").write_text(
                "path,keyword,speaker_id\n"
                "positive/help/a.wav,help,s1\n"
                "negative/hello/b.wav,hello,s2\n"
                "physical_holdout/positive/help/c.wav,help,s3\n"
                "physical_holdout/negative/hi/d.wav,hi,s4\n", encoding="utf-8")
            dev = replay_eval.load_items(root, split="dev", subset=None, limit=None, onsets={})
            holdout = replay_eval.load_items(root, split="holdout", subset=None, limit=None, onsets={})
        self.assertEqual([i["path"] for i in dev], ["positive/help/a.wav", "negative/hello/b.wav"])
        self.assertEqual([(i["path"], i["label"], i["category"]) for i in holdout],
                         [("physical_holdout/positive/help/c.wav", 1, "help"),
                          ("physical_holdout/negative/hi/d.wav", 0, "hi")])

    def test_wav_reader_rejects_unsupported_format(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "stereo.wav"
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(2)
                handle.setsampwidth(2)
                handle.setframerate(16000)
                handle.writeframes(bytes(400))
            with self.assertRaises(ValueError):
                replay_eval.read_wav(path)

    @unittest.skipUnless(os.environ.get("PROJECT_PI_M1M2_KWS_DIR"),
                         "set PROJECT_PI_M1M2_KWS_DIR to the Milestone 1-2 raspberry_pi/kws")
    def test_harness_drives_milestone_1_2_loop(self):
        items = [item("positive/help/a.wav", 1, "help"), item("negative/silence/b.wav", 0)]
        rows, _, _, engines = replay([tone(0.6, 12000), tone(0.6, 30)], items,
                                     kws_dir=os.environ["PROJECT_PI_M1M2_KWS_DIR"])
        self.assertEqual([r["score"] for r in rows], [1.0, 0.0])
        self.assertTrue(all(engines["loaded"].values()))


def write_wav(path: Path, samples: array, rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(samples.tobytes())


def fake_root(temp: Path, *, mem_kib=3_000_000, swap=(1_000_000, 900_000), temp_milli_c=55_000,
              pressure="some avg10=0.10 avg60=0.00 avg300=0.00 total=1") -> Path:
    """A stand-in for / with the /proc and /sys files the resource checks read."""
    (temp / "proc/pressure").mkdir(parents=True, exist_ok=True)
    (temp / "proc/self").mkdir(exist_ok=True)
    (temp / "proc/self/cgroup").write_text("", encoding="utf-8")
    (temp / "proc/self/mountinfo").write_text("", encoding="utf-8")
    (temp / "sys/class/thermal/thermal_zone0").mkdir(parents=True, exist_ok=True)
    (temp / "proc/meminfo").write_text(
        f"MemTotal:        8000000 kB\nMemAvailable:    {mem_kib} kB\n"
        f"SwapTotal:       {swap[0]} kB\nSwapFree:        {swap[1]} kB\n", encoding="utf-8")
    if pressure is not None:
        (temp / "proc/pressure/memory").write_text(pressure + "\n", encoding="utf-8")
    if temp_milli_c is not None:
        (temp / "sys/class/thermal/thermal_zone0/temp").write_text(f"{temp_milli_c}\n", encoding="utf-8")
    return temp


def valid_run(**changes) -> dict:
    run = {"evidence_mode": "validated", "speed": 1.0, "chunk_s": 0.08, "max_pacing_lag_s": 0.01,
           "queue_drops": 0, "unprocessed_packets": 0, "threads_not_stopped": [], "network_attempts": [],
           "noise_config_snapshot_unchanged": True, "required_engines": list(replay_eval.ENGINES),
           "resource_checks": "passed"}
    run.update(changes)
    return run


class ReplaySafetyTest(unittest.TestCase):
    """C1.10 safeguards: dropped audio, frozen settings, evidence status, side effects, resources."""

    def setUp(self):
        LIVE_IO.clear()
        FakeConfigStore.paths.clear()

    def test_counting_put_latest_keeps_production_behaviour_and_counts_each_drop(self):
        kws, previous = load_kws_with_fake_engines()
        try:
            production = queue.Queue(maxsize=2)
            for packet in (1, 2, 3, 4):
                kws.put_latest(production, packet)
            cache = replay_eval.EngineCache(kws)
            originals = cache.install()
            cache.recorder = replay_eval.EventRecorder(lambda: 7.5)
            counted = queue.Queue(maxsize=2)
            for packet in (1, 2, 3, 4):
                kws.put_latest(counted, packet)
            for name, value in originals.items():
                setattr(kws, name, value)
        finally:
            restore(previous)
        self.assertEqual(list(counted.queue), list(production.queue))  # newest kept, oldest dropped
        self.assertEqual(list(counted.queue), [3, 4])
        self.assertEqual(cache.recorder.drops, [7.5, 7.5])  # two packets discarded, both counted
        self.assertEqual(len(cache.queues), 1)

    def test_slow_engine_drops_are_counted_attributed_and_invalidate_the_run(self):
        FakeRecognizer.delay_s = 0.1  # Vosk worker far slower than the 8 ms chunks at speed 10
        try:
            rows, _, runs, _ = replay([tone(4.0, 12000)], [item("positive/help/a.wav", 1, "help")],
                                      speed=10.0)
        finally:
            FakeRecognizer.delay_s = 0.0
        pacing = runs[0][2]
        self.assertGreater(pacing["queue_drops"], 0)
        self.assertEqual(rows[0]["queue_drops"], pacing["queue_drops"])
        self.assertEqual(pacing["threads_not_stopped"], [])
        reasons = replay_eval.invalid_reasons(valid_run(queue_drops=pacing["queue_drops"],
                                                        unprocessed_packets=pacing["unprocessed_packets"]))
        self.assertTrue(any("dropped" in reason for reason in reasons))

    def test_normal_run_has_no_drops_no_leftover_packets_and_no_lingering_threads(self):
        _rows, _, runs, engines = replay([tone(0.6, 12000), tone(0.6, 30)],
                                         [item("positive/help/a.wav", 1, "help"), item("negative/silence/b.wav", 0)])
        for _timeline, _recorder, pacing in runs:
            self.assertEqual((pacing["queue_drops"], pacing["unprocessed_packets"], pacing["threads_not_stopped"]),
                             (0, 0, []))
        self.assertEqual(engines["network_attempts"], [])
        self.assertEqual(LIVE_IO, [])  # neither the microphone nor the HTTP client was created

    def test_noise_settings_come_from_a_frozen_read_only_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            live = temp / "live" / "project_pi_noise_suppression.json"
            live.parent.mkdir()
            live.write_text('{"strength": 0.9}', encoding="utf-8")
            captured = temp / "captured.json"
            captured.write_bytes(live.read_bytes())
            scratch = temp / "scratch"
            scratch.mkdir()
            env = {**fake_env(temp), "NOISE_SUPPRESSION_CONFIG_PATH": str(live)}
            isolated, record = replay_eval.isolate_environment(env, scratch, captured)
            snapshot = Path(isolated["NOISE_SUPPRESSION_CONFIG_PATH"])
            live.write_text('{"strength": 0.1}', encoding="utf-8")  # the app changes live settings mid-run

            kws, previous = load_kws_with_fake_engines()
            try:
                replay_eval.run_replay(kws, [tone(0.3, 30)], env=isolated, gap_seconds=0.3,
                                       lead_in=replay_eval.dither(0.2))
                effective = replay_eval.effective_noise_settings(kws, snapshot)
            finally:
                restore(previous)
            self.assertEqual(snapshot.parent, scratch)
            self.assertEqual(snapshot.read_text(encoding="utf-8"), '{"strength": 0.9}')
            self.assertEqual(record["noise_config_snapshot_sha256"], replay_eval.sha256_file(snapshot))
            self.assertFalse(snapshot.stat().st_mode & stat.S_IWUSR)  # read-only
            self.assertIn(snapshot, FakeConfigStore.paths)
            self.assertNotIn(live, FakeConfigStore.paths)  # the loop never opened the live file
            self.assertEqual(set(effective), set(replay_eval.NOISE_CONFIG_FIELDS))
            snapshot.chmod(stat.S_IREAD | stat.S_IWRITE)  # let the temporary directory be removed

    def test_replay_writes_nothing_to_live_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            live = temp / "live"
            live.mkdir()
            for name in ("audio_status.json", "alerts.jsonl", "noise.json"):
                (live / name).write_text("{}", encoding="utf-8")
            before = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in live.iterdir()}
            env = {**fake_env(temp),
                   "PROJECT_PI_AUDIO_STATUS_PATH": str(live / "audio_status.json"),
                   "ALERT_QUEUE_PATH": str(live / "alerts.jsonl"),
                   "NOISE_SUPPRESSION_CONFIG_PATH": str(live / "noise.json"),
                   "BACKEND_ALERT_URL": "http://127.0.0.1:8765/api/alerts",
                   "PROJECT_PI_API_TOKEN": "not-a-real-token-but-must-be-cleared"}
            scratch = temp / "scratch"
            scratch.mkdir()
            isolated, record = replay_eval.isolate_environment(env, scratch, live / "noise.json")
            self.assertEqual(isolated["PROJECT_PI_API_TOKEN"], "")
            self.assertEqual((isolated["HF_HUB_OFFLINE"], isolated["TRANSFORMERS_OFFLINE"]), ("1", "1"))
            self.assertIn(":9/", isolated["BACKEND_ALERT_URL"])
            for key in ("PROJECT_PI_AUDIO_STATUS_PATH", "ALERT_QUEUE_PATH", "NOISE_SUPPRESSION_CONFIG_PATH"):
                self.assertEqual(Path(isolated[key]).parent, scratch)
            kws, previous = load_kws_with_fake_engines()
            try:
                _runs, engines = replay_eval.run_replay(kws, [tone(0.6, 12000)], env=isolated,
                                                        gap_seconds=0.3, lead_in=replay_eval.dither(0.2))
            finally:
                restore(previous)
            after = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in live.iterdir()}
            self.assertEqual(after, before)
            self.assertTrue((scratch / "audio_status.json").exists())  # status went to scratch instead
            self.assertEqual(LIVE_IO, [])
            self.assertEqual(engines["network_attempts"], [])
            Path(record["noise_config_snapshot"]).chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_network_guard_refuses_loopback_and_lookups_then_restores_sockets(self):
        original_connect, original_lookup = socket.socket.connect, socket.getaddrinfo
        with replay_eval.NetworkGuard() as guard:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                with self.assertRaises(PermissionError):
                    sock.connect(("127.0.0.1", 8765))  # where the live backend listens
            with self.assertRaises(PermissionError):
                socket.getaddrinfo("huggingface.co", 443)
        self.assertEqual(len(guard.attempts), 2)
        self.assertIs(socket.socket.connect, original_connect)
        self.assertIs(socket.getaddrinfo, original_lookup)

    def test_missing_dependency_stops_before_anything_is_replayed(self):
        saved = {name: sys.modules.get(name) for name in ("kws_alert_dual", "pyaudio", "vosk")}
        sys.modules.pop("kws_alert_dual", None)
        sys.modules["pyaudio"] = None  # importing it now raises ImportError
        sys.modules["vosk"] = None
        try:
            with self.assertRaises(SystemExit) as raised:
                replay_eval.import_kws()
        finally:
            restore(saved)
        self.assertIn("missing dependency", str(raised.exception))
        self.assertIn("Nothing was replayed", str(raised.exception))

    def test_invalid_runs_are_never_valid_as_evidence(self):
        self.assertEqual(replay_eval.invalid_reasons(valid_run()), [])
        cases = {
            "preliminary": valid_run(evidence_mode="preliminary"),
            "speed": valid_run(speed=2.0),
            "lag": valid_run(max_pacing_lag_s=0.2),
            "dropped": valid_run(queue_drops=3),
            "still queued": valid_run(unprocessed_packets=1),
            "threads": valid_run(threads_not_stopped=["vosk"]),
            "network": valid_run(network_attempts=["connect ('127.0.0.1', 8765)"]),
            "snapshot": valid_run(noise_config_snapshot_unchanged=False),
            "engines": valid_run(required_engines=["openwakeword"]),
            "resource checks": valid_run(resource_checks="skipped"),
        }
        for expected, run in cases.items():
            with self.subTest(expected):
                reasons = replay_eval.invalid_reasons(run)
                self.assertEqual(len(reasons), 1)
                self.assertIn(expected, reasons[0])

    def test_validated_mode_needs_every_label_human_verified(self):
        items = [item("positive/help/a.wav", 1, "help"), item("negative/hi/b.wav", 0)]
        self.assertEqual(replay_eval.unverified_items(items), ["positive/help/a.wav", "negative/hi/b.wav"])
        items[0].update(review_status="verified", reviewed_label="positive",
                        review_method="human_listening", review_evidence="synthetic-001")
        items[1].update(review_status="machine_screened", reviewed_label="negative",
                        review_method="human_listening", review_evidence="synthetic-002")
        self.assertEqual(replay_eval.unverified_items(items), ["negative/hi/b.wav"])
        items[1]["review_status"] = "verified"
        self.assertEqual(replay_eval.unverified_items(items), [])
        items[0]["reviewed_label"] = "negative"  # reviewer disagrees with the folder
        self.assertEqual(replay_eval.unverified_items(items), ["positive/help/a.wav"])

    def _dataset(self, root: Path, metadata: str) -> list[str]:
        (root / "data").mkdir()
        (root / "data/metadata.csv").write_text(metadata, encoding="utf-8")
        write_wav(root / "data/positive/help/a.wav", tone(0.6, 12000))
        write_wav(root / "data/negative/random_speech/b.wav", tone(0.6, 30))
        (root / "effective.env").write_text(
            "\n".join(f"{k}={v}" for k, v in fake_env(root).items()) + "\n", encoding="utf-8")
        (root / "noise.json").write_text("{}", encoding="utf-8")
        return ["--dataset-dir", str(root / "data"), "--env-file", str(root / "effective.env"),
                "--noise-config", str(root / "noise.json"), "--out-dir", str(root / "out"),
                "--gap-seconds", "0.6", "--lead-in-seconds", "0.3", "--nice", "0"]

    def test_validated_mode_refuses_to_start_on_unreviewed_recordings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = self._dataset(root, "path,keyword,speaker_id,review_status\n"
                                       "positive/help/a.wav,help,s1,not_reviewed\n"
                                       "negative/random_speech/b.wav,,s2,machine_screened\n")
            with self.assertRaises(SystemExit) as raised:
                replay_eval.main([*args, "--evidence-mode", "validated", "--skip-resource-checks"])
            self.assertEqual(raised.exception.code, 2)
            self.assertFalse((root / "out").exists())  # nothing measured, nothing written

    def test_preliminary_run_reports_detections_without_correctness_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = self._dataset(root, "path,keyword,speaker_id\n"
                                       "positive/help/a.wav,help,s1\n"
                                       "negative/random_speech/b.wav,,s2\n")
            kws, previous = load_kws_with_fake_engines()
            real_import = replay_eval.import_kws
            replay_eval.import_kws = lambda: kws
            try:
                code = replay_eval.main([*args, "--skip-resource-checks"])
            finally:
                replay_eval.import_kws = real_import
                restore(previous)
            summary = json.loads((root / "out/summary.json").read_text(encoding="utf-8"))
            header = (root / "out/preliminary_detections.csv").read_text(encoding="utf-8").splitlines()[0]
            self.assertEqual(code, 0)
            self.assertFalse((root / "out/predictions.csv").exists())
            self.assertEqual(summary["evidence_status"], "preliminary")
            self.assertIsNone(summary["metrics"])
            for metric in ("exact_keyword", "any_distress", "per_keyword", "event_level"):
                self.assertNotIn(metric, summary)
            self.assertEqual(summary["detections"]["recordings"], 2)
            self.assertEqual(summary["detections"]["recordings_with_any_alert"], 1)
            self.assertNotIn("score", header.split(","))
            self.assertIn("provisional_label", header.split(","))
            self.assertFalse(summary["run"]["valid_as_evidence"])
            self.assertIn("preliminary run: recording labels are not human-verified",
                          summary["run"]["invalid_reasons"])
            self.assertEqual(summary["run"]["noise_config_snapshot_sha256"],
                             replay_eval.hashlib.sha256(b"{}").hexdigest())
            self.assertTrue(summary["run"]["noise_config_snapshot_unchanged"])
            self.assertEqual(len(summary["run"]["noise_settings_effective"]), 4)
            snapshot = Path(summary["run"]["noise_config_snapshot"])
            snapshot.chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_resource_preflight_passes_a_healthy_machine(self):
        with tempfile.TemporaryDirectory() as temp:
            result = replay_eval.resource_preflight(replay_eval.DEFAULT_LIMITS, fake_root(Path(temp)),
                                                    throttled_reader=lambda: 0, lag_reader=lambda: 2.0)
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["reading"]["temperature_c"], 55.0)
        self.assertEqual(result["reading"]["swap_used_pct"], 10.0)

    def test_resource_preflight_refuses_low_memory_heat_swap_lag_and_throttling(self):
        cases = {
            "mem_available_mib": dict(mem_kib=800 * 1024),  # the ~800 MiB reported on the Pi
            "temperature_c": dict(temp_milli_c=75_000),
            "swap_used_pct": dict(swap=(1_000_000, 100_000)),
            "memory_pressure_some_avg10": dict(pressure="some avg10=12.50 avg60=3.00 avg300=1.00 total=9"),
        }
        for expected, overrides in cases.items():
            with self.subTest(expected), tempfile.TemporaryDirectory() as temp:
                failures = replay_eval.resource_preflight(
                    replay_eval.DEFAULT_LIMITS, fake_root(Path(temp), **overrides),
                    throttled_reader=lambda: 0, lag_reader=lambda: 2.0)["failures"]
                self.assertEqual(len(failures), 1)
                self.assertTrue(failures[0].startswith(expected))
        with tempfile.TemporaryDirectory() as temp:
            root = fake_root(Path(temp))
            lag = replay_eval.resource_preflight(replay_eval.DEFAULT_LIMITS, root,
                                                 throttled_reader=lambda: 0, lag_reader=lambda: 45.0)
            soft_limit = replay_eval.resource_preflight(replay_eval.DEFAULT_LIMITS, root,
                                                        throttled_reader=lambda: 0x8, lag_reader=lambda: 2.0)
        self.assertTrue(lag["failures"][0].startswith("scheduling_lag_ms"))
        self.assertIn("soft temperature limit", soft_limit["failures"][0])

    def test_unreadable_sensors_fail_the_preflight_but_optional_pressure_does_not(self):
        with tempfile.TemporaryDirectory() as temp:
            no_sensor = replay_eval.resource_preflight(
                replay_eval.DEFAULT_LIMITS, fake_root(Path(temp), temp_milli_c=None, pressure=None),
                throttled_reader=lambda: None, lag_reader=lambda: 2.0)
        self.assertEqual(no_sensor["failures"], ["temperature_c unreadable"])
        with tempfile.TemporaryDirectory() as temp:
            nothing = replay_eval.resource_preflight(replay_eval.DEFAULT_LIMITS, Path(temp) / "missing",
                                                     throttled_reader=lambda: None, lag_reader=lambda: 2.0)
        self.assertEqual(nothing["failures"], ["mem_available_mib unreadable", "swap_used_pct unreadable",
                                               "temperature_c unreadable"])

    def test_resource_limit_overrides_are_validated(self):
        limits = replay_eval.parse_limit_overrides(["min_mem_available_mib=700"])
        self.assertEqual(limits["min_mem_available_mib"], 700.0)
        with self.assertRaises(ValueError):
            replay_eval.parse_limit_overrides(["min_memory=1"])

    def test_watchdog_stops_the_loop_when_the_pi_overheats(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fake_root(Path(temp), temp_milli_c=80_000)
            loop = types.SimpleNamespace(RUNNING=True)
            watchdog = replay_eval.ResourceWatchdog(loop, replay_eval.DEFAULT_LIMITS, root, interval_s=0.01)
            watchdog.start()
            watchdog.join(2.0)
        self.assertFalse(loop.RUNNING)
        self.assertIn("temperature_c=80.0", watchdog.reason)

    def test_replay_does_not_start_when_an_abort_limit_is_already_crossed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fake_root(Path(temp), mem_kib=300 * 1024)
            kws, previous = load_kws_with_fake_engines()
            try:
                with self.assertRaises(replay_eval.ReplayAborted) as raised:
                    replay_eval.run_replay(kws, [tone(0.3, 30)], env=fake_env(Path(temp)), gap_seconds=0.3,
                                           lead_in=replay_eval.dither(0.2),
                                           abort_limits=replay_eval.DEFAULT_LIMITS, resource_root=root)
            finally:
                restore(previous)
        self.assertEqual(raised.exception.completed, 0)
        self.assertIn("mem_available_mib", raised.exception.reason)

    def test_short_and_long_recordings_are_replayed_whole_and_flagged(self):
        # 0.86 s mirrors the shortest clip found in review; 12 s the longest exception clip.
        items = [item("positive/help/short.wav", 1, "help"), item("negative/random_speech/long.wav", 0)]
        rows, _, runs, _ = replay([tone(0.86, 12000), tone(12.0, 30)], items, speed=8.0)
        self.assertEqual([r["duration_s"] for r in rows], [0.86, 12.0])
        self.assertEqual([r["duration_flag"] for r in rows], ["under_1s", "over_5s"])
        self.assertEqual(rows[0]["detected_keywords"], "help")  # the padded last chunk still counts
        self.assertEqual(rows[1]["event_count"], 0)
        self.assertEqual(sum(p["queue_drops"] for _t, _r, p in runs), 0)

    def test_44_1_khz_audio_is_rejected_with_conversion_guidance(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cd_rate.wav"
            write_wav(path, array("h", bytes(2 * 4410)), rate=44100)
            with self.assertRaisesRegex(ValueError, r"44100 Hz.*Convert a copy offline.*never replace"):
                replay_eval.read_wav(path)



class ResumedSafetyTests(unittest.TestCase):
    def test_limits_reject_nonfinite_and_negative(self):
        for value in ("nan", "inf", "-1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replay_eval.parse_limit_overrides(["min_mem_available_mib=" + value])

    def test_machine_screened_labels_cannot_be_scored(self):
        self.assertEqual(replay_eval.unverified_items([
            dict(path="negative/random_speech/synthetic.wav", label=0,
                 review_status="machine_screened", reviewed_label="negative")
        ]), ["negative/random_speech/synthetic.wav"])

    def test_metadata_traversal_rejected_before_audio_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "metadata.csv").write_text(
                "path,keyword\nnegative/../../outside.wav,\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsafe recording path"):
                replay_eval.load_items(root, split="dev", subset=None, limit=None, onsets={})

    def test_runtime_resource_checks_include_pressure_and_swap(self):
        reading = dict(mem_available_mib=2000, temperature_c=50,
                       swap_used_pct=99, memory_pressure_some_avg10=99)
        reasons = replay_eval.limit_failures(reading, replay_eval.DEFAULT_LIMITS,
                                              replay_eval.RUNTIME_CHECKS)
        self.assertEqual(len(reasons), 2)

    def test_truncated_wav_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "truncated.wav"
            write_wav(path, tone(.1, 30))
            path.write_bytes(path.read_bytes()[:-2])
            with self.assertRaisesRegex(ValueError, "truncated WAV"):
                replay_eval.read_wav(path)

    def test_validated_but_invalid_run_withholds_metrics(self):
        from unittest.mock import patch
        # Reuse the existing dataset fixture without touching real recordings.
        owner = ReplaySafetyTest
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = owner()._dataset(root,
                "path,keyword,speaker_id,review_status,reviewed_label,review_method,review_evidence\n"
                "positive/help/a.wav,help,s1,verified,positive,human_listening,synthetic-001\n"
                "negative/random_speech/b.wav,,s2,verified,negative,human_listening,synthetic-002\n")
            kws, previous = load_kws_with_fake_engines()
            try:
                with patch.object(replay_eval, "import_kws", return_value=kws):
                    self.assertEqual(replay_eval.main(
                        [*args, "--evidence-mode", "validated", "--skip-resource-checks"]), 3)
            finally:
                restore(previous)
            summary = json.loads((root / "out/summary.json").read_text())
            self.assertEqual(summary["evidence_status"], "invalid")
            self.assertIsNone(summary["metrics"])
            self.assertNotIn("exact_keyword", summary)
            self.assertFalse((root / "out/predictions.csv").exists())
            Path(summary["run"]["noise_config_snapshot"]).chmod(stat.S_IREAD | stat.S_IWRITE)


    def test_existing_output_is_not_reused_or_overwritten(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = ReplaySafetyTest()._dataset(root, "path,keyword\nnegative/random_speech/b.wav,\n")
            (root / "out").mkdir()
            previous = root / "out/predictions.csv"
            previous.write_text("previous evidence", encoding="utf-8")
            with patch.object(replay_eval, "import_kws") as imported:
                with self.assertRaises(SystemExit):
                    replay_eval.main([*args, "--skip-resource-checks"])
                imported.assert_not_called()
            self.assertEqual(previous.read_text(), "previous evidence")

    def test_changed_configuration_invalidates_evidence(self):
        reasons = replay_eval.invalid_reasons(dict(configuration_unchanged=False))
        self.assertIn("engine configuration or model hashes changed during replay", reasons)


class ReviewCorrectionTests(unittest.TestCase):
    def test_sha256_streams_instead_of_reading_entire_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "large.bin"
            data = b"synthetic" * 400000
            path.write_bytes(data)
            with patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded read")):
                self.assertEqual(replay_eval.sha256_file(path), replay_eval.hashlib.sha256(data).hexdigest())

    def test_model_provenance_covers_vosk_snowboy_and_explicit_oww(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "effective.env"
            source.write_text("# synthetic\n")
            files = {"vosk/am/final.mdl": b"acoustic", "vosk/conf/model.conf": b"config",
                     "help.pmdl": b"snowboy", "common.res": b"resource", "custom.onnx": b"wake",
                     "custom.onnx.data": b"external weights"}
            for name, data in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            env = {"VOSK_MODEL_PATH": str(root / "vosk"),
                   "SNOWBOY_MODEL_PATHS": str(root / "help.pmdl"),
                   "SNOWBOY_RESOURCE_PATH": str(root / "common.res"),
                   "OPENWAKEWORD_MODELS": str(root / "custom.onnx"),
                   "OPENWAKEWORD_MODEL_DIR": str(root / "absent")}
            first = replay_eval.configuration_record(source, env)
            assets = first["model_content_provenance"]
            self.assertEqual(assets["vosk"]["files_sha256"], {
                "am/final.mdl": replay_eval.hashlib.sha256(b"acoustic").hexdigest(),
                "conf/model.conf": replay_eval.hashlib.sha256(b"config").hexdigest()})
            for key in ("vosk", "snowboy_resource", "snowboy_models", "openwakeword"):
                self.assertEqual(assets[key]["status"], "hashed")
            for name in files:
                path = root / name
                old = path.read_bytes()
                path.write_bytes(old + b"changed")
                self.assertNotEqual(replay_eval.configuration_record(source, env), first, name)
                path.write_bytes(old)
            (root / "common.res").unlink()
            missing = replay_eval.configuration_record(source, env)["model_content_provenance"]
            self.assertNotEqual(missing["snowboy_resource"]["status"], "hashed")

    def test_verification_flags_alone_do_not_supply_label_provenance(self):
        sample = dict(path="negative/speech/a.wav", label=0,
                      review_status="verified", reviewed_label="negative")
        self.assertEqual(replay_eval.unverified_items([sample]), [sample["path"]])
        sample.update(review_method="human_listening", review_evidence="synthetic-review-001")
        self.assertEqual(replay_eval.unverified_items([sample]), [])
        for evidence in ("", "unknown", "unassessed", "N/A"):
            sample["review_evidence"] = evidence
            self.assertEqual(replay_eval.unverified_items([sample]), [sample["path"]])
        sample.update(review_evidence="synthetic-review-001", review_method="transcript_screening")
        self.assertEqual(replay_eval.unverified_items([sample]), [sample["path"]])

    def test_cli_invalid_validated_runs_preserve_diagnostics_and_fail(self):
        cases = {"pacing": {"max_lag_s": .5}, "drops": {"queue_drops": 1},
                 "backlog": {"unprocessed_packets": 1}, "skipped_resources": {},
                 "network": {}, "speed": {}, "provenance": {}, "valid": {}}
        for name, overrides in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                args = ReplaySafetyTest()._dataset(root,
                    "path,keyword,review_status,reviewed_label,review_method,review_evidence\n"
                    "negative/random_speech/b.wav,,verified,negative,human_listening,synthetic-001\n")
                recording = tone(.6, 30)
                timeline = replay_eval.Timeline(array("h"), [recording], 0)
                recorder = replay_eval.EventRecorder(lambda: 0)
                pacing = dict(max_lag_s=0, chunk_s=.08, queue_drops=0,
                              unprocessed_packets=0, threads_not_stopped=[])
                pacing.update(overrides)
                engines = dict(loaded={k: True for k in replay_eval.ENGINES}, openwakeword={},
                               network_attempts=["synthetic refused connection"] if name == "network" else [])
                kws = types.SimpleNamespace(NoiseSuppressionConfigStore=FakeConfigStore)
                extra = ["--skip-resource-checks"] if name == "skipped_resources" else []
                if name == "speed":
                    extra += ["--speed", "2"]
                with patch.object(replay_eval, "import_kws", return_value=kws), \
                     patch.object(replay_eval, "configuration_record", return_value=(
                         {"unverified_model_assets": ["vosk"]} if name == "provenance" else {})), \
                     patch.object(replay_eval, "resource_preflight", return_value=dict(reading={}, failures=[])), \
                     patch.object(replay_eval, "run_replay", return_value=([(timeline, recorder, pacing)], engines)):
                    code = replay_eval.main([*args, "--evidence-mode", "validated", *extra])
                summary = json.loads((root / "out/summary.json").read_text())
                self.assertEqual(code, 0 if name == "valid" else 3)
                self.assertTrue((root / "out/events.jsonl").exists())
                if name == "valid":
                    self.assertEqual(summary["evidence_status"], "validated")
                    self.assertTrue((root / "out/predictions.csv").exists())
                else:
                    self.assertEqual(summary["evidence_status"], "invalid")
                    self.assertIsNone(summary["metrics"])
                    self.assertTrue((root / "out/preliminary_detections.csv").exists())
                    self.assertFalse((root / "out/predictions.csv").exists())
                Path(summary["run"]["noise_config_snapshot"]).chmod(stat.S_IREAD | stat.S_IWRITE)

    def test_model_tree_hash_is_relocation_independent_and_detects_added_files(self):
        with tempfile.TemporaryDirectory() as temp:
            roots = [Path(temp) / name for name in ("first", "second")]
            for root in roots:
                root.mkdir()
                (root / "model").write_bytes(b"synthetic")
            first = replay_eval.model_content_record([roots[0]])
            self.assertEqual(first["manifest_sha256"],
                             replay_eval.model_content_record([roots[1]])["manifest_sha256"])
            (roots[1] / "new-conf").write_bytes(b"new")
            self.assertNotEqual(first["manifest_sha256"],
                                replay_eval.model_content_record([roots[1]])["manifest_sha256"])

    @unittest.skipUnless(os.name == "posix", "symlink fixture needs POSIX permissions")
    def test_model_tree_does_not_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "model"
            root.mkdir()
            outside = Path(temp) / "outside"
            outside.write_bytes(b"not part of model")
            (root / "link").symlink_to(outside)
            report = replay_eval.model_content_record([root])
            self.assertEqual(report["status"], "unverified")
            self.assertEqual(report["files_sha256"], {})

    def test_missing_and_empty_model_assets_are_explicitly_unverified(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for paths in ([], [root], [root / "missing"]):
                with self.subTest(paths=paths):
                    report = replay_eval.model_content_record(paths)
                    self.assertEqual(report["status"], "unverified")
                    self.assertTrue(report["issues"])

    def test_empty_oww_selection_uses_deployed_directory_discovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model_dir = root / "dataset/audio/openwakeword_models"
            model_dir.mkdir(parents=True)
            (model_dir / "help.onnx").write_bytes(b"synthetic graph")
            (model_dir / "help.onnx.data").write_bytes(b"synthetic weights")
            source = root / "effective.env"
            source.write_text("# synthetic")
            result = replay_eval.configuration_record(source,
                {"PROJECT_PI_ROOT": str(root), "OPENWAKEWORD_MODELS": ""})
            self.assertEqual(result["model_content_provenance"]["openwakeword"]["status"], "hashed")


def cgroup_fixture(root, *, version=2, membership="/worker", mount_root="/", mount="/sys/fs/cgroup"):
    proc = root / "proc/self"
    proc.mkdir(parents=True, exist_ok=True)
    proc.joinpath("cgroup").write_text(
        f"0::{membership}\n" if version == 2 else f"5:cpu,memory:{membership}\n")
    proc.joinpath("mountinfo").write_text(
        f"30 20 0:28 {mount_root} {mount} ro - "
        + ("cgroup2 cgroup rw\n" if version == 2 else "cgroup cgroup rw,cpu,memory\n"))
    base = root.joinpath(*Path(mount).parts[1:])
    base.mkdir(parents=True, exist_ok=True)
    set_cgroup_memory(base, "max" if version == 2 else str(2**63 - 4096), 0, version)
    relative = membership.removeprefix(mount_root).lstrip("/") if mount_root != "/" else membership.lstrip("/")
    leaf = base / relative
    for directory in [*reversed(leaf.relative_to(base).parents), leaf.relative_to(base)]:
        (base / directory).mkdir(parents=True, exist_ok=True)
    return base, leaf


def set_cgroup_memory(directory, limit, usage, version=2):
    directory.mkdir(parents=True, exist_ok=True)
    limit_name, usage_name = (("memory.max", "memory.current") if version == 2 else
                              ("memory.limit_in_bytes", "memory.usage_in_bytes"))
    (directory / limit_name).write_text(str(limit))
    (directory / usage_name).write_text(str(usage))


class ContainerMemoryTests(unittest.TestCase):
    def preflight(self, root):
        return replay_eval.resource_preflight(replay_eval.DEFAULT_LIMITS, root,
            throttled_reader=lambda: 0, lag_reader=lambda: 1)

    def test_healthy_container_and_host_minimum(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fake_root(Path(temp), mem_kib=4 * 1024 * 1024)
            _, leaf = cgroup_fixture(root)
            set_cgroup_memory(leaf, 3 * 1024**3, 1024**3)
            result = self.preflight(root)
            self.assertEqual(result["failures"], [])
            self.assertEqual(result["reading"]["mem_available_mib"], 2048)
            self.assertEqual(result["reading"]["memory"]["host_available_bytes"], 4 * 1024**3)
            # Host pressure still wins even when the container has ample headroom.
            root.joinpath("proc/meminfo").write_text(
                "MemAvailable: 716800 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n")
            self.assertEqual(self.preflight(root)["reading"]["mem_available_mib"], 700)

    def test_near_exhaustion_blocks_despite_ample_host_ram(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fake_root(Path(temp), mem_kib=8 * 1024 * 1024)
            _, leaf = cgroup_fixture(root)
            set_cgroup_memory(leaf, 2 * 1024**3, 1900 * 1024**2)
            result = self.preflight(root)
            self.assertEqual(result["reading"]["mem_available_mib"], 148)
            self.assertTrue(any("mem_available_mib=148" in reason for reason in result["failures"]))

    def test_nested_ancestor_usage_not_leaf_usage_determines_headroom(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fake_root(Path(temp))
            _, leaf = cgroup_fixture(root, membership="/parent/worker")
            set_cgroup_memory(leaf, 2 * 1024**3, 100 * 1024**2)
            set_cgroup_memory(leaf.parent, 3 * 1024**3, 2800 * 1024**2)
            reading = self.preflight(root)["reading"]
            self.assertEqual(reading["mem_available_mib"], 272)
            self.assertEqual(len(reading["memory"]["cgroup"]["ancestors"]), 3)

    def test_unlimited_limits_use_host_but_still_check_ancestors(self):
        for version, unlimited in ((2, "max"), (1, str(2**63 - 4096)), (1, "-1")):
            with self.subTest(version=version, unlimited=unlimited), tempfile.TemporaryDirectory() as temp:
                root = fake_root(Path(temp), mem_kib=2048 * 1024)
                _, leaf = cgroup_fixture(root, version=version)
                set_cgroup_memory(leaf, unlimited, 123, version)
                result = self.preflight(root)
                self.assertEqual(result["failures"], [])
                self.assertEqual(result["reading"]["mem_available_mib"], 2048)

    def test_v1_finite_limits_and_ancestor_usage(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fake_root(Path(temp))
            _, leaf = cgroup_fixture(root, version=1, membership="/parent/worker")
            set_cgroup_memory(leaf, 2 * 1024**3, 0, 1)
            set_cgroup_memory(leaf.parent, 1024**3, 700 * 1024**2, 1)
            result = self.preflight(root)
            self.assertEqual(result["reading"]["mem_available_mib"], 324)
            self.assertEqual(result["reading"]["memory"]["cgroup"]["version"], 1)

    def test_v1_combined_memory_swap_cap_also_constrains_allocations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fake_root(Path(temp))
            _, leaf = cgroup_fixture(root, version=1)
            set_cgroup_memory(leaf, 2 * 1024**3, 0, 1)
            (leaf / "memory.memsw.limit_in_bytes").write_text(str(2 * 1024**3))
            (leaf / "memory.memsw.usage_in_bytes").write_text(str(1900 * 1024**2))
            self.assertEqual(self.preflight(root)["reading"]["mem_available_mib"], 148)

    def test_v1_incomplete_combined_memory_swap_metrics_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fake_root(Path(temp))
            _, leaf = cgroup_fixture(root, version=1)
            set_cgroup_memory(leaf, 2 * 1024**3, 0, 1)
            (leaf / "memory.memsw.limit_in_bytes").write_text(str(2 * 1024**3))
            self.assertIsNone(self.preflight(root)["reading"]["mem_available_mib"])

    def test_zero_and_overlimit_usage_are_zero_headroom(self):
        for limit, usage in ((0, 0), (1024, 2048)):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as temp:
                root = fake_root(Path(temp))
                _, leaf = cgroup_fixture(root)
                set_cgroup_memory(leaf, limit, usage)
                self.assertEqual(self.preflight(root)["reading"]["mem_available_mib"], 0)

    def test_missing_and_malformed_metrics_fail_closed(self):
        for metric, value in (("memory.max", None), ("memory.current", None),
                              ("memory.max", "garbage"), ("memory.current", "-1"),
                              ("memory.current", "nan"), ("memory.max", "1.5")):
            with self.subTest(metric=metric, value=value), tempfile.TemporaryDirectory() as temp:
                root = fake_root(Path(temp))
                _, leaf = cgroup_fixture(root)
                set_cgroup_memory(leaf, 2 * 1024**3, 0)
                if value is None:
                    (leaf / metric).unlink()
                else:
                    (leaf / metric).write_text(value)
                result = self.preflight(root)
                self.assertIsNone(result["reading"]["mem_available_mib"])
                self.assertTrue(result["reading"]["memory"]["failures"])
                self.assertIn("mem_available_mib unreadable", result["failures"])

    def test_unreadable_metrics_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fake_root(Path(temp))
            _, leaf = cgroup_fixture(root)
            set_cgroup_memory(leaf, 2 * 1024**3, 0)
            original = Path.read_text
            def deny(path, *args, **kwargs):
                if path == leaf / "memory.current":
                    raise PermissionError("synthetic unreadable metric")
                return original(path, *args, **kwargs)
            with patch.object(Path, "read_text", deny):
                self.assertIsNone(self.preflight(root)["reading"]["mem_available_mib"])

    def test_discovery_errors_fail_closed(self):
        for name, value in (("cgroup", None), ("mountinfo", None),
                            ("cgroup", "malformed"), ("mountinfo", "malformed")):
            with self.subTest(name=name, value=value), tempfile.TemporaryDirectory() as temp:
                root = fake_root(Path(temp))
                _, leaf = cgroup_fixture(root)
                set_cgroup_memory(leaf, 2 * 1024**3, 0)
                path = root / "proc/self" / name
                path.unlink() if value is None else path.write_text(value)
                self.assertIsNone(self.preflight(root)["reading"]["mem_available_mib"])

    def test_no_memory_controller_uses_host(self):
        with tempfile.TemporaryDirectory() as temp:
            result = self.preflight(fake_root(Path(temp), mem_kib=2048 * 1024))
            self.assertEqual(result["failures"], [])
            self.assertEqual(result["reading"]["memory"]["source"], "host")
            self.assertEqual(result["reading"]["mem_available_mib"], 2048)

    def test_real_v2_root_without_limit_interface_uses_host(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fake_root(Path(temp))
            base, _ = cgroup_fixture(root, membership="/")
            (base / "memory.max").unlink()
            (base / "memory.current").unlink()
            (base / "cgroup.controllers").write_text("cpu memory pids\n")
            self.assertEqual(self.preflight(root)["failures"], [])

    def test_escaped_mountpoint_and_hybrid_hierarchy_use_memory_controller(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fake_root(Path(temp))
            _, leaf = cgroup_fixture(root, version=1, mount="/sys/fs/cgroup/memory group")
            set_cgroup_memory(leaf, 2 * 1024**3, 1024**3, 1)
            info = root / "proc/self/mountinfo"
            info.write_text(info.read_text().replace("memory group", r"memory\040group")
                            + "31 20 0:29 / /sys/unified ro - cgroup2 cgroup rw\n")
            group = root / "proc/self/cgroup"
            group.write_text(group.read_text() + "0::/other\n")
            self.assertEqual(self.preflight(root)["reading"]["mem_available_mib"], 1024)

    def test_unsafe_paths_and_missing_mapping_fail_closed(self):
        for membership in ("/../outside", "/different/worker"):
            with self.subTest(membership=membership), tempfile.TemporaryDirectory() as temp:
                root = fake_root(Path(temp))
                cgroup_fixture(root)
                (root / "proc/self/cgroup").write_text(f"0::{membership}\n")
                if "different" in membership:
                    info = root / "proc/self/mountinfo"
                    info.write_text(info.read_text().replace("0:28 / ", "0:28 /other "))
                self.assertIsNone(self.preflight(root)["reading"]["mem_available_mib"])

    def test_missing_ancestor_usage_fails_even_with_healthy_leaf(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fake_root(Path(temp))
            _, leaf = cgroup_fixture(root, membership="/parent/worker")
            set_cgroup_memory(leaf, 2 * 1024**3, 0)
            set_cgroup_memory(leaf.parent, 3 * 1024**3, 0)
            (leaf.parent / "memory.current").unlink()
            self.assertIsNone(self.preflight(root)["reading"]["mem_available_mib"])

    def test_hidden_ancestor_mount_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fake_root(Path(temp))
            _, leaf = cgroup_fixture(root, membership="/parent/worker", mount_root="/parent")
            set_cgroup_memory(leaf, 2 * 1024**3, 0)
            result = self.preflight(root)
            self.assertIsNone(result["reading"]["mem_available_mib"])
            self.assertTrue(any("ancestor" in s for s in result["reading"]["memory"]["failures"]))

    def test_memory_crossing_abort_threshold_stops_watchdog(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fake_root(Path(temp))
            _, leaf = cgroup_fixture(root)
            set_cgroup_memory(leaf, 2 * 1024**3, 0)
            loop = types.SimpleNamespace(RUNNING=True)
            watchdog = replay_eval.ResourceWatchdog(loop, replay_eval.DEFAULT_LIMITS, root)
            with patch.object(replay_eval, "read_throttled", return_value=0):
                self.assertFalse(watchdog.check())
                set_cgroup_memory(leaf, 2 * 1024**3, 1800 * 1024**2)
                self.assertTrue(watchdog.check())
            self.assertFalse(loop.RUNNING)
            self.assertIn("mem_available_mib=248", watchdog.reason)
            self.assertEqual(watchdog.last_reading["memory"]["effective_headroom_bytes"], 248 * 1024**2)

    def test_cli_preflight_failure_is_nonzero_and_saved_before_audio_load(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = ReplaySafetyTest()._dataset(root, "path,keyword\nnegative/random_speech/b.wav,\n")
            sensor_root = fake_root(root / "sensors")
            _, leaf = cgroup_fixture(sensor_root)
            set_cgroup_memory(leaf, 256 * 1024**2, 100 * 1024**2)
            preflight = self.preflight(sensor_root)
            with patch.object(replay_eval, "resource_preflight", return_value=preflight), \
                 patch.object(replay_eval, "read_wav") as audio, \
                 patch.object(replay_eval, "import_kws") as engines:
                self.assertEqual(replay_eval.main(args), 3)
                audio.assert_not_called()
                engines.assert_not_called()
            report = json.loads((root / "out/preflight_failed.json").read_text())
            self.assertFalse(report["valid_as_evidence"])
            self.assertEqual(report["resource_preflight"]["reading"]["mem_available_mib"], 156)

    def test_replay_propagates_cgroup_abort_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = fake_root(Path(temp))
            _, leaf = cgroup_fixture(root)
            set_cgroup_memory(leaf, 2 * 1024**3, 0)
            kws, previous = load_kws_with_fake_engines()
            monitor = replay_eval.ResourceWatchdog(kws, replay_eval.DEFAULT_LIMITS, root)
            def cross_limit(*args):
                set_cgroup_memory(leaf, 2 * 1024**3, 1800 * 1024**2)
                monitor.check()
                return None, None, {}
            try:
                with patch.object(replay_eval, "ResourceWatchdog", return_value=monitor), \
                     patch.object(replay_eval, "_run_once", side_effect=cross_limit), \
                     patch.object(replay_eval, "read_throttled", return_value=0):
                    with self.assertRaises(replay_eval.ReplayAborted) as error:
                        replay_eval.run_replay(kws, [tone(.1, 30)], env=fake_env(root),
                            gap_seconds=0, lead_in=array("h"), abort_limits=replay_eval.DEFAULT_LIMITS,
                            resource_root=root)
            finally:
                restore(previous)
            self.assertEqual(error.exception.resource_reading["mem_available_mib"], 248)

    def test_cli_resource_abort_retains_snapshot_and_nonzero_status(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = ReplaySafetyTest()._dataset(root, "path,keyword\nnegative/random_speech/b.wav,\n")
            sensors = fake_root(root / "sensors")
            _, leaf = cgroup_fixture(sensors)
            set_cgroup_memory(leaf, 2 * 1024**3, 0)
            healthy = self.preflight(sensors)
            set_cgroup_memory(leaf, 2 * 1024**3, 1800 * 1024**2)
            failed = replay_eval.read_resources(sensors)
            with patch.object(replay_eval, "resource_preflight", return_value=healthy), \
                 patch.object(replay_eval, "import_kws", return_value=types.SimpleNamespace()), \
                 patch.object(replay_eval, "configuration_record", return_value={}), \
                 patch.object(replay_eval, "run_replay", side_effect=replay_eval.ReplayAborted(
                     "synthetic memory threshold crossed", 0, failed)):
                self.assertEqual(replay_eval.main(args), 3)
            report = json.loads((root / "out/aborted.json").read_text())
            self.assertFalse(report["valid_as_evidence"])
            self.assertEqual(report["resource_reading"]["mem_available_mib"], 248)
            self.assertFalse((root / "out/predictions.csv").exists())


if __name__ == "__main__":
    unittest.main()
