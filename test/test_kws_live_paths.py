"""C1.45 scripted-worker and dispatcher regression guards.

C1.44 characterized defective prefix/fusion behavior. C1.45 replaces those
assertions with corrected expectations after reproducing the original failures.
All recognizers, packets and transcripts here are synthetic; no audio or model.
"""
import json
import queue
import threading
import time
import types
import unittest

from test.test_kws_event_id import load_kws_module, restore_modules


class Poster:
    def __init__(self):
        self.published = []

    def publish(self, keyword, confidence, source, **kwargs):
        self.published.append((keyword, source))


class ScriptedRecognizer:
    """Vosk stand-in: one (accepted, text) step per audio chunk, in order."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.current = (False, "")
        self.resets = 0

    def AcceptWaveform(self, data):
        self.current = self.steps.pop(0) if self.steps else (False, "")
        return self.current[0]

    def Result(self):
        return json.dumps({"text": self.current[1]})

    def PartialResult(self):
        return json.dumps({"partial": self.current[1]})

    def Reset(self):
        self.resets += 1


class Samples(list):
    @property
    def size(self):
        return len(self)

    def copy(self):
        return Samples(self)


def partials(word):
    """What Vosk's partial result shows while `word` is being spoken, then the final."""
    return [(False, word[:n]) for n in range(1, len(word) + 1)] + [(True, word)]


class LivePathTestCase(unittest.TestCase):
    CONFIRM = 0.05
    SUPPRESS = 0.3

    def setUp(self):
        self.kws, previous = load_kws_module()
        self.addCleanup(restore_modules, previous)
        self.kws.np = types.SimpleNamespace(
            int16=int, asarray=lambda values, dtype=None: Samples(values))

    def dispatcher(self):
        poster = Poster()
        dispatcher = self.kws.DetectionDispatcher(
            poster=poster, cooldown=self.kws.CooldownGate(2.0),
            help_confirm_seconds=self.CONFIRM, help_suppress_after_tulong_seconds=self.SUPPRESS)
        return dispatcher, poster

    def vosk_pair(self, dispatcher, text):
        """Exactly what vosk_worker does for one matched transcript (lines 1132-1197)."""
        keyword = self.kws.detect_tagalog_keyword(text)
        if keyword is not None:
            dispatcher.note_vosk_text(text)
            dispatcher.submit(keyword, 0.75, "vosk")
        return keyword

    def run_vosk_worker(self, steps):
        """Feed one chunk per step through the real vosk_worker loop."""
        dispatcher, poster = self.dispatcher()
        recognizer = ScriptedRecognizer(steps)
        audio = queue.Queue()
        for _ in steps:
            audio.put({"mono_samples": [0] * 4, "mono_bytes": b"\0" * 8})
        config = {"sample_rate": 16000, "debug": False, "confidence": 0.75,
                  "wav2vec2_verify_below_confidence": 0.0, "wav2vec2_context_seconds": 1.0,
                  "model_path": "stub"}
        self.kws.RUNNING = True
        worker = threading.Thread(target=self.kws.vosk_worker,
                                  args=(audio, dispatcher, config, recognizer, None), daemon=True)
        worker.start()
        deadline = time.monotonic() + 5
        while not audio.empty() and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.3)  # the worker's queue timeout is 0.2 s
        self.kws.RUNNING = False
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        return poster.published, recognizer


class LiveVoskLoopTest(LivePathTestCase):
    def test_genuine_tulong_is_published_from_the_live_loop(self):
        # Recall guard on the real path.
        published, _ = self.run_vosk_worker(partials("tulong"))
        self.assertEqual(published, [("tulong", "vosk")])

    def test_requested_negatives_publish_nothing_from_the_live_loop(self):
        for word in ("hi", "hello", "kamusta", "kumusta", "umaga", "salamat", "sige"):
            published, recognizer = self.run_vosk_worker(partials(word))
            self.assertEqual(published, [], word)
            self.assertEqual(recognizer.resets, 0, word)

    def test_ordinary_word_prefixes_do_not_publish(self):
        for word in ("tulog", "tuloy", "araw", "agad", "sunod", "magandang umaga", "tara"):
            published, recognizer = self.run_vosk_worker(partials(word))
            self.assertEqual(published, [], word)
            self.assertEqual(recognizer.resets, 0, word)


class DispatcherLiveWiringTest(LivePathTestCase):
    def settle(self):
        time.sleep(self.CONFIRM + 0.1)

    def test_genuine_tulong_pair_preserves_independent_snowboy_help(self):
        # Independent sources retain their detections; acoustic correlation is not inferred.
        dispatcher, poster = self.dispatcher()
        self.vosk_pair(dispatcher, "tulong")
        dispatcher.submit("help", 0.75, "snowboy")
        self.settle()
        self.assertEqual(poster.published, [("tulong", "vosk"), ("help", "snowboy")])

    def test_unrelated_speech_does_not_touch_a_pending_snowboy_help(self):
        dispatcher, poster = self.dispatcher()
        dispatcher.submit("help", 0.75, "snowboy")
        self.assertIsNone(self.vosk_pair(dispatcher, "magandang umaga"))
        self.settle()
        self.assertEqual(poster.published, [("help", "snowboy")])

    def test_ordinary_word_does_not_replace_pending_snowboy_help(self):
        dispatcher, poster = self.dispatcher()
        dispatcher.submit("help", 0.75, "snowboy")
        self.assertIsNone(self.vosk_pair(dispatcher, "araw"))
        self.settle()
        self.assertEqual(poster.published, [("help", "snowboy")])

    def test_ordinary_word_does_not_suppress_openwakeword_help(self):
        dispatcher, poster = self.dispatcher()
        self.assertIsNone(self.vosk_pair(dispatcher, "tulog"))
        dispatcher.submit("help", 0.6, "openwakeword")
        self.assertEqual(poster.published, [("help", "openwakeword")])

    def test_vosk_tulong_submission_preserves_independent_openwakeword_help(self):
        # A Vosk submission cannot establish that independent help is a misfire.
        dispatcher, poster = self.dispatcher()
        dispatcher.submit("tulong", 0.75, "vosk")
        dispatcher.submit("help", 0.6, "openwakeword")
        self.assertEqual(poster.published, [("tulong", "vosk"), ("help", "openwakeword")])

    def test_openwakeword_and_snowboy_help_together_publish_one_help(self):
        # Same-keyword overlap is merged by the per-keyword cooldown, not by correlation.
        dispatcher, poster = self.dispatcher()
        dispatcher.submit("help", 0.6, "openwakeword")
        dispatcher.submit("help", 0.75, "snowboy")
        self.settle()
        self.assertEqual(poster.published, [("help", "openwakeword")])

    def test_openwakeword_tulong_preserves_independent_snowboy_help(self):
        dispatcher, poster = self.dispatcher()
        dispatcher.submit("tulong", 0.8, "openwakeword")
        dispatcher.submit("help", 0.75, "snowboy")
        self.settle()
        self.assertEqual(poster.published, [("tulong", "openwakeword"), ("help", "snowboy")])

    def test_different_keywords_from_one_moment_are_separate_events(self):
        # No cross-engine correlation exists: a Vosk keyword other than tulong and an
        # openWakeWord help from the same moment are published as two events (each gets
        # its own event_id in AlertPoster.publish), so the backend cannot merge them.
        dispatcher, poster = self.dispatcher()
        dispatcher.submit("help", 0.6, "openwakeword")
        self.vosk_pair(dispatcher, "saklolo")
        self.assertEqual(poster.published, [("help", "openwakeword"), ("saklolo", "vosk")])

    def test_suppression_ends_after_the_window(self):
        dispatcher, poster = self.dispatcher()
        dispatcher.submit("tulong", 0.8, "openwakeword")
        time.sleep(self.SUPPRESS + 0.05)
        dispatcher.submit("help", 0.6, "openwakeword")
        self.assertEqual(poster.published, [("tulong", "openwakeword"), ("help", "openwakeword")])


if __name__ == "__main__":
    unittest.main()
