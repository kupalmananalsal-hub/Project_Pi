"""C1.45 exact-alias/cancellation regressions, synthetic ASR only.

No audio, models, network or real timers. Worker fixtures execute vosk_worker
synchronously with a scripted recognizer and a finite packet feed.
"""
import contextlib
import io
import queue
import types
import unittest
from unittest.mock import patch

from test.test_kws_event_id import load_kws_module, restore_modules
from test.test_kws_live_paths import Samples, ScriptedRecognizer


class ManualTimer:
    def __init__(self, delay, callback):
        self.callback = callback
        self.cancelled = False
        self.daemon = False
    def start(self): pass
    def cancel(self): self.cancelled = True
    def fire(self):
        if not self.cancelled: self.callback()


class Recorder:
    def __init__(self): self.events = []
    def publish(self, keyword, confidence, source, **kwargs):
        self.events.append((keyword, confidence, source))


class RecognitionDefectRemediationTest(unittest.TestCase):
    def setUp(self):
        self.kws, previous = load_kws_module()
        self.addCleanup(restore_modules, previous)
        self.now = 1000.0
        clock = patch.object(self.kws.time, "monotonic", side_effect=lambda: self.now)
        clock.start(); self.addCleanup(clock.stop)
        timer = patch.object(self.kws.threading, "Timer", ManualTimer)
        timer.start(); self.addCleanup(timer.stop)
        self.kws.np = types.SimpleNamespace(int16=int,
            asarray=lambda values, dtype=None: Samples(values))

    def dispatcher(self):
        poster = Recorder()
        dispatcher = self.kws.DetectionDispatcher(poster, self.kws.CooldownGate(2), 1.2, 2.2)
        return dispatcher, poster

    def run_worker(self, steps):
        dispatcher, poster = self.dispatcher()
        recognizer = ScriptedRecognizer(steps)
        count = 0
        module = self.kws
        class Packets:
            def get(inner, timeout):
                nonlocal count
                if count == len(steps):
                    module.RUNNING = False
                    raise queue.Empty
                count += 1
                return {"mono_samples": [0]*4, "mono_bytes": b"\0"*8}
        config = {"sample_rate":16000, "debug":False, "confidence":.75,
                  "wav2vec2_verify_below_confidence":0.0,
                  "wav2vec2_context_seconds":1.0, "model_path":"stub"}
        module.RUNNING = True
        with contextlib.redirect_stdout(io.StringIO()):
            module.vosk_worker(Packets(), dispatcher, config, recognizer, None)
        return poster.events, recognizer

    def test_nine_non_alias_words_do_not_match(self):
        for word in ("tulog","tuloy","tulo","araw","aral","aga","agad","sunod","sundo"):
            with self.subTest(word=word): self.assertIsNone(self.kws.detect_tagalog_keyword(word))

    def test_configured_aliases_and_canonical_words_are_preserved(self):
        fixtures = {
            "tulong":"tulong", "tolong":"tulong", "tulon":"tulong", "tulom":"tulong",
            "tulungan":"tulong", "tulungan mo":"tulong", "tulungan mo ako":"tulong",
            "tulungan niyo":"tulong", "tulungan niyo ako":"tulong",
            "saklolo":"saklolo", "sakolo":"saklolo", "saglolo":"saklolo", "saklola":"saklolo",
            "ang sakit":"ang sakit", "sakit":"ang sakit", "masakit":"ang sakit",
            "nanasakit":"ang sakit", "sumasakit":"ang sakit",
            "aray":"aray", "aray ko":"aray", "aray naman":"aray",
            "agai":"agai", "agay":"agai", "agay ko":"agai",
            "sunog":"sunog", "may sunog":"sunog",
            "kailangan ko ng tulong":"tulong", "kailangan tulong":"tulong",
            "kailangan ko tulong":"tulong", "nangangailangan ng tulong":"tulong"}
        for text, keyword in fixtures.items():
            with self.subTest(text=text): self.assertEqual(self.kws.detect_tagalog_keyword(text), keyword)

    def test_unlisted_prefix_does_not_become_completed_keyword(self):
        self.assertIsNone(self.kws.detect_tagalog_keyword("tul"))
        self.assertEqual(self.kws.detect_tagalog_keyword("tulong"), "tulong")

    def test_multiword_alias_requires_whole_token_boundaries(self):
        self.assertIsNone(self.kws.detect_tagalog_keyword("ang sakitness"))
        self.assertEqual(self.kws.detect_tagalog_keyword("ANG SAKIT!"), "ang sakit")

    def test_valid_non_tulong_keywords_do_not_cancel_snowboy_help(self):
        # Genuine aray etc. exercises the ANY-match bug independently of fuzzy fixes.
        for text in ("aray", "saklolo", "sunog", "masakit", "agai", "araw"):
            with self.subTest(text=text):
                dispatcher, poster = self.dispatcher()
                dispatcher.submit("help", .75, "snowboy")
                timer = dispatcher.pending_help_timer
                dispatcher.note_vosk_text(text)
                self.assertFalse(timer.cancelled)
                timer.fire()
                self.assertEqual(poster.events, [("help", .75, "snowboy")])

    def test_ambiguous_vosk_prefix_and_word_cannot_veto_openwakeword_help(self):
        for text in ("tul", "tulog", "tuloy", "araw"):
            with self.subTest(text=text):
                dispatcher, poster = self.dispatcher()
                dispatcher.note_vosk_text(text)
                dispatcher.submit("help", .6, "openwakeword")
                self.assertEqual(poster.events, [("help", .6, "openwakeword")])

    def test_text_hint_alone_does_not_veto_independent_openwakeword_help(self):
        dispatcher, poster = self.dispatcher()
        dispatcher.note_vosk_text("tulong")  # Hint, not a published alert.
        dispatcher.submit("help", .6, "openwakeword")
        self.assertEqual(poster.events, [("help", .6, "openwakeword")])

    def test_genuine_vosk_tulong_preserves_pending_snowboy_help(self):
        dispatcher, poster = self.dispatcher()
        dispatcher.submit("help", .75, "snowboy")
        timer = dispatcher.pending_help_timer
        dispatcher.note_vosk_text("tulong")
        dispatcher.submit("tulong", .75, "vosk")
        timer.fire()
        self.assertEqual(poster.events, [("tulong", .75, "vosk"), ("help", .75, "snowboy")])

    def test_genuine_vosk_tulong_then_snowboy_help_remains_independent(self):
        dispatcher, poster = self.dispatcher()
        dispatcher.note_vosk_text("tulong")
        dispatcher.submit("tulong", .75, "vosk")
        dispatcher.submit("help", .75, "snowboy")
        self.assertIsNotNone(dispatcher.pending_help_timer)
        dispatcher.pending_help_timer.fire()
        self.assertEqual(poster.events, [("tulong", .75, "vosk"), ("help", .75, "snowboy")])

    def test_non_tulong_vosk_and_snowboy_both_remain_independent(self):
        dispatcher, poster = self.dispatcher()
        dispatcher.submit("help", .75, "snowboy")
        timer = dispatcher.pending_help_timer
        dispatcher.note_vosk_text("aray")
        dispatcher.submit("aray", .75, "vosk")
        timer.fire()
        self.assertEqual(poster.events, [("aray", .75, "vosk"), ("help", .75, "snowboy")])

    def test_same_keyword_overlapping_engines_preserve_shared_cooldown(self):
        dispatcher, poster = self.dispatcher()
        dispatcher.submit("help", .6, "openwakeword")
        dispatcher.submit("help", .75, "snowboy")
        dispatcher.pending_help_timer.fire()
        self.assertEqual(poster.events, [("help", .6, "openwakeword")])

    def test_repeated_detections_keep_existing_two_second_cooldown(self):
        dispatcher, poster = self.dispatcher()
        dispatcher.submit("sunog", .6, "openwakeword")
        self.now = 1001
        dispatcher.submit("sunog", .6, "openwakeword")
        self.now = 1002
        dispatcher.submit("sunog", .6, "openwakeword")
        self.assertEqual(poster.events, [("sunog", .6, "openwakeword")]*2)

    def test_partial_prefix_then_final_ordinary_word_emits_nothing(self):
        for word in ("tulog", "araw", "agad", "sunod"):
            with self.subTest(word=word):
                steps=[(False,word[:i]) for i in range(1,len(word)+1)]+[(True,word)]
                events, recognizer = self.run_worker(steps)
                self.assertEqual(events, [])
                self.assertEqual(recognizer.resets, 0)

    def test_partial_prefix_then_completed_distress_is_accepted(self):
        for word, keyword in (("tulong","tulong"),("aray","aray"),("masakit","ang sakit")):
            with self.subTest(word=word):
                events, recognizer = self.run_worker([(False,"tul"),(True,word)])
                self.assertEqual(events, [(keyword,.75,"vosk")])
                self.assertEqual(recognizer.resets, 1)

    def test_complete_exact_partial_distress_does_not_wait_for_final(self):
        # If speech-only input never yields a final, a final-only gate would miss this.
        for word, keyword in (("tulong","tulong"),("aray","aray"),("masakit","ang sakit")):
            with self.subTest(word=word):
                events, _ = self.run_worker([(False,word)])
                self.assertEqual(events, [(keyword,.75,"vosk")])

    def test_revision_of_an_exact_partial_remains_a_readiness_blocker(self):
        # Characterization, not a claim of correction: ASR may revise even an exact token.
        events, _ = self.run_worker([(False,"tulong"),(True,"tulog")])
        self.assertEqual(events, [("tulong",.75,"vosk")])


if __name__ == "__main__":
    unittest.main()
