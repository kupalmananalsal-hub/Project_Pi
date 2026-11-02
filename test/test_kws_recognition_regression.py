"""C1.45 offline matcher/fusion regression guards.

The four original expected failures were reproduced before correction. Their
markers were removed only after the text/dispatcher assertions passed. masakit
was moved from the contradictory negative list to the positive alias fixtures.
Synthetic results are not acoustic recall evidence; deployment remains blocked.
"""
import time
import unittest

from test.test_kws_event_id import load_kws_module, restore_modules

# Non-alias negative fixtures; legitimate configured masakit stays positive.
ORDINARY_WORDS = {
    "tulog": "sleep", "tuloy": "continue", "tulo": "drip",
    "araw": "day", "aral": "study", "aga": "early", "agad": "immediately",
    "sunod": "next", "sundo": "pick up",
}
REQUESTED_NEGATIVES = ("hi", "hello", "kamusta", "kumusta")
DISTRESS_PHRASES = {
    "tulong": "tulong", "tulungan mo ako": "tulong", "kailangan ko ng tulong": "tulong",
    "saklolo": "saklolo", "aray": "aray", "aray ko": "aray", "agai": "agai",
    "sunog": "sunog", "may sunog": "sunog", "ang sakit": "ang sakit",
    "masakit": "ang sakit",
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

    def test_genuine_tulong_preserves_independent_snowboy_help(self):
        dispatcher, poster = self.dispatcher()
        dispatcher.submit("tulong", 0.8, "openwakeword")
        dispatcher.submit("help", 0.75, "snowboy")
        time.sleep(0.15)
        self.assertEqual(poster.published, [("tulong", "openwakeword"), ("help", "snowboy")])

    # --- corrected text/dispatcher defects; acoustic validation is separate ---

    def test_ordinary_words_are_not_distress_keywords(self):
        matched = {w: self.kws.detect_tagalog_keyword(w) for w in ORDINARY_WORDS}
        self.assertEqual({w: k for w, k in matched.items() if k}, {})

    def test_partial_prefix_does_not_match_while_word_is_spoken(self):
        self.assertIsNone(self.kws.detect_tagalog_keyword("tul"))

    def test_non_tulong_vosk_hint_does_not_cancel_snowboy_help(self):
        dispatcher, poster = self.dispatcher()
        dispatcher.submit("help", 0.75, "snowboy")
        dispatcher.note_vosk_text("araw")
        time.sleep(0.15)
        self.assertEqual(poster.published, [("help", "snowboy")])

    def test_vosk_hint_does_not_suppress_openwakeword_help(self):
        dispatcher, poster = self.dispatcher()
        dispatcher.note_vosk_text("tulog")
        dispatcher.submit("help", 0.6, "openwakeword")
        self.assertEqual(poster.published, [("help", "openwakeword")])


if __name__ == "__main__":
    unittest.main()
