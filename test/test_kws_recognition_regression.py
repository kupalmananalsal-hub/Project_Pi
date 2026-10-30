"""Regression targets for Milestone 3 recognition work (no behavior change yet).

Recall guards must keep passing through any fix. Tests marked expectedFailure pin
defects confirmed by a deterministic probe of the current code (PLAN.md, Milestone 3
item 4); a fix is only accepted together with replay evidence (replay_eval.py) that
recall holds, and it turns them into ordinary passing tests.
"""
import time
import unittest

from test.test_kws_event_id import load_kws_module, restore_modules

# Ordinary words the current Vosk matcher turns into distress keywords.
ORDINARY_WORDS = {
    "tulog": "sleep", "tuloy": "continue", "tulo": "drip",
    "araw": "day", "aral": "study", "aga": "early", "agad": "immediately",
    "sunod": "next", "sundo": "pick up", "masakit": "painful (no distress phrase)",
}
REQUESTED_NEGATIVES = ("hi", "hello", "kamusta", "kumusta")
DISTRESS_PHRASES = {
    "tulong": "tulong", "tulungan mo ako": "tulong", "kailangan ko ng tulong": "tulong",
    "saklolo": "saklolo", "aray": "aray", "aray ko": "aray", "agai": "agai",
    "sunog": "sunog", "may sunog": "sunog", "ang sakit": "ang sakit",
}


class Poster:
    def __init__(self):
        self.published = []

    def publish(self, keyword, confidence, source, **kwargs):
        self.published.append((keyword, source))


class RecognitionRegressionTest(unittest.TestCase):
    def setUp(self):
        self.kws, previous = load_kws_module()
        self.addCleanup(restore_modules, previous)

    def dispatcher(self):
        poster = Poster()
        dispatcher = self.kws.DetectionDispatcher(
            poster=poster, cooldown=self.kws.CooldownGate(2.0),
            help_confirm_seconds=0.05, help_suppress_after_tulong_seconds=0.3)
        return dispatcher, poster

    # --- recall guards: pass today, must keep passing ---------------------------

    def test_distress_phrases_still_match(self):
        for text, keyword in DISTRESS_PHRASES.items():
            self.assertEqual(self.kws.detect_tagalog_keyword(text), keyword, text)

    def test_requested_negatives_do_not_match_vosk_path(self):
        for word in REQUESTED_NEGATIVES:
            self.assertIsNone(self.kws.detect_tagalog_keyword(word), word)

    def test_genuine_tulong_still_suppresses_snowboy_help(self):
        dispatcher, poster = self.dispatcher()
        dispatcher.submit("tulong", 0.8, "openwakeword")
        dispatcher.submit("help", 0.75, "snowboy")
        time.sleep(0.15)
        self.assertEqual(poster.published, [("tulong", "openwakeword")])

    # --- confirmed defects (expected to fail until a measured fix lands) --------

    @unittest.expectedFailure
    def test_ordinary_words_are_not_distress_keywords(self):
        matched = {w: self.kws.detect_tagalog_keyword(w) for w in ORDINARY_WORDS}
        self.assertEqual({w: k for w, k in matched.items() if k}, {})

    @unittest.expectedFailure
    def test_partial_prefix_does_not_match_while_word_is_spoken(self):
        self.assertIsNone(self.kws.detect_tagalog_keyword("tul"))

    @unittest.expectedFailure
    def test_non_tulong_vosk_hint_does_not_cancel_snowboy_help(self):
        dispatcher, poster = self.dispatcher()
        dispatcher.submit("help", 0.75, "snowboy")
        dispatcher.note_vosk_text("araw")
        time.sleep(0.15)
        self.assertEqual(poster.published, [("help", "snowboy")])

    @unittest.expectedFailure
    def test_vosk_hint_does_not_suppress_openwakeword_help(self):
        dispatcher, poster = self.dispatcher()
        dispatcher.note_vosk_text("tulog")
        dispatcher.submit("help", 0.6, "openwakeword")
        self.assertEqual(poster.published, [("help", "openwakeword")])


if __name__ == "__main__":
    unittest.main()
