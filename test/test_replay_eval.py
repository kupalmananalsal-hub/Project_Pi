"""Replay harness: drives the real kws_alert_dual.main() with FAKE engines.

These tests check the harness plumbing (stream, isolation, attribution, metrics).
They say nothing about recognition accuracy: no real openWakeWord, Vosk or
Snowboy model runs here.
"""
import importlib.util
import math
import os
import sys
import tempfile
import types
import unittest
import wave
from array import array
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
KWS_DIR = PROJECT_ROOT / "raspberry_pi" / "kws"
sys.path.insert(0, str(KWS_DIR))

import replay_eval  # noqa: E402

LOUD = 4000  # the fake openWakeWord "hears help" above this RMS


class FakeConfig:
    active, strength, sensitivity, snowboy_sensitivity = True, 0.5, 0.5, None


class FakeConfigStore:
    def __init__(self, path):
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
    def __init__(self, model, rate):
        pass

    def SetWords(self, value):
        pass

    def AcceptWaveform(self, data):
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
    stubs["pyaudio"].PyAudio = object
    stubs["requests"].Session = object
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
           preprocessor=FakeAudioPreprocessor):
    kws, previous = load_kws_with_fake_engines(kws_dir, preprocessor)
    try:
        with tempfile.TemporaryDirectory() as temp:
            runs, engines = replay_eval.run_replay(
                kws, recordings, env=fake_env(Path(temp)), gap_seconds=gap,
                lead_in=replay_eval.dither(0.3), isolate=isolate)
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


if __name__ == "__main__":
    unittest.main()
