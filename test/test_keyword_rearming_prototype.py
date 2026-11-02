"""C1.43 synthetic score fixtures only; never import a real engine or read audio.

Without the prototype module, the same expectations exercise the existing
CooldownGate. That red mode makes the sustained-score defect reproducible.
"""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test.test_kws_event_id import load_kws_module, restore_modules

try:
    from tools.keyword_rearming_prototype import KeywordRearmingPrototype
except ModuleNotFoundError as exc:
    if exc.name != "tools.keyword_rearming_prototype":
        raise
    KeywordRearmingPrototype = None


class RearmingTest(unittest.TestCase):
    def setUp(self):
        self.kws, previous = load_kws_module()
        self.addCleanup(restore_modules, previous)

    def gate(self):
        if KeywordRearmingPrototype is not None:
            return KeywordRearmingPrototype(release_seconds=0.25,
                max_gap_seconds=0.125, critical_threshold=0.85)
        # Baseline adapter: real existing gate, no proposed rearming behavior.
        cooldown = self.kws.CooldownGate(2.0)
        class ExistingGate:
            def observe(inner, keyword, score, threshold, now, available=True):
                if not available or score is None or score < threshold:
                    return None
                with patch.object(self.kws.time, "monotonic", return_value=now):
                    return "episode_start" if cooldown.allow(keyword) else None
        return ExistingGate()

    def feed(self, gate, fixture, keyword="sunog"):
        return [(t, reason) for t, score in fixture
                if (reason := gate.observe(keyword, score, 0.30, 1000 + t))]

    def test_sustained_match_emits_once_even_after_cooldown(self):
        self.assertEqual(self.feed(self.gate(), [(0, .6), (2, .6), (4, .6), (8, .6)]),
                         [(0, "episode_start")])

    def test_separate_episode_is_immediate_after_observed_release(self):
        self.assertEqual(self.feed(self.gate(), [(0, .6), (.125, .1), (.25, .1),
                         (.375, .1), (.5, .6)]),
                         [(0, "episode_start"), (.5, "episode_start")])

    def test_one_low_frame_does_not_release(self):
        self.assertEqual(self.feed(self.gate(), [(0, .6), (2, .1), (2.125, .6)]),
                         [(0, "episode_start")])

    def test_missing_scores_do_not_release(self):
        self.assertEqual(self.feed(self.gate(), [(0, .6), (2, None), (4, None), (6, .6)]),
                         [(0, "episode_start")])

    def test_unavailable_prediction_does_not_release(self):
        gate = self.gate()
        self.assertEqual(gate.observe("sunog", .6, .3, 1000), "episode_start")
        for t in (1002, 1002.125, 1002.25):
            self.assertIsNone(gate.observe("sunog", .1, .3, t, available=False))
        self.assertIsNone(gate.observe("sunog", .6, .3, 1004))

    def test_sparse_low_observations_do_not_prove_continuous_release(self):
        self.assertEqual(self.feed(self.gate(), [(0, .6), (2, .1), (4, .1), (6, .6)]),
                         [(0, "episode_start")])

    def test_critical_upgrade_is_not_lost_or_repeated(self):
        self.assertEqual(self.feed(self.gate(), [(0, .4), (.125, .85), (2, .95),
                         (4, .4), (6, .95)]),
                         [(0, "episode_start"), (.125, "critical_upgrade")])

    def test_first_critical_and_exact_threshold_are_accepted(self):
        self.assertEqual(self.feed(self.gate(), [(0, .95)]), [(0, "episode_start")])
        self.assertEqual(self.feed(self.gate(), [(0, .30)]), [(0, "episode_start")])

    def test_threshold_equality_does_not_release(self):
        self.assertEqual(self.feed(self.gate(), [(0, .6), (2, .30), (4, .6)]),
                         [(0, "episode_start")])

    def test_distinct_overlapping_keywords_are_not_arbitrated_away(self):
        gate = self.gate()
        self.assertEqual(gate.observe("sunog", .6, .3, 1000), "episode_start")
        self.assertEqual(gate.observe("saklolo", .5, .3, 1000), "episode_start")
        self.assertIsNone(gate.observe("sunog", .6, .3, 1002))
        self.assertIsNone(gate.observe("saklolo", .5, .3, 1002))

    def test_low_sequence_for_one_keyword_cannot_release_another(self):
        gate = self.gate()
        gate.observe("sunog", .6, .3, 1000)
        for t in (1002, 1002.125, 1002.25):
            gate.observe("saklolo", .1, .3, t)
        self.assertIsNone(gate.observe("sunog", .6, .3, 1004))

    def test_invalid_scores_break_release_evidence(self):
        for invalid in (float("nan"), float("inf"), -1.0, 1.1, None):
            with self.subTest(score=invalid):
                gate = self.gate()
                gate.observe("sunog", .6, .3, 1000)
                gate.observe("sunog", .1, .3, 1002)
                gate.observe("sunog", invalid, .3, 1002.125)
                gate.observe("sunog", .1, .3, 1002.25)
                self.assertIsNone(gate.observe("sunog", .6, .3, 1002.375))

    def test_unknown_observation_interrupts_low_sequence(self):
        gate = self.gate()
        gate.observe("sunog", .6, .3, 1000)
        for t, score in ((1002, .1), (1002.125, None), (1002.25, .1)):
            gate.observe("sunog", score, .3, t)
        self.assertIsNone(gate.observe("sunog", .6, .3, 1002.375))

    def test_high_observation_interrupts_low_sequence(self):
        self.assertEqual(self.feed(self.gate(), [(0, .6), (2, .1), (2.125, .6),
                         (2.25, .1), (2.375, .1), (2.5, .6)]),
                         [(0, "episode_start")])

    def test_released_episode_can_be_critical_immediately(self):
        self.assertEqual(self.feed(self.gate(), [(0, .95), (.125, .1), (.25, .1),
                         (.375, .1), (.5, .95), (.625, .95)]),
                         [(0, "episode_start"), (.5, "episode_start")])

    def test_thermal_change_is_a_live_integration_blocker(self):
        # This deliberately pins the unresolved hazard rather than claiming safety:
        # identical voice scores can acquire a critical decision with new thermal evidence.
        engine = self.kws.AlertDecisionEngine(policy=self.kws.AlertPolicy(
            repeat_escalates_to_critical=False))
        event = {"keyword": "sunog", "confidence": .4, "source": "openwakeword"}
        negative = {"thermal_state": "negative", "human_detected": False,
                    "frame_valid": True, "frame_age_seconds": .1}
        positive = {**negative, "thermal_state": "positive", "human_detected": True}
        self.assertEqual(engine.evaluate(event, negative)["decision_state"], "advisory")
        gate = self.gate()
        gate.observe("sunog", .4, .3, 1000)
        self.assertIsNone(gate.observe("sunog", .4, .3, 1000.125))
        self.assertEqual(engine.evaluate(event, positive)["decision_state"], "critical")

    def test_existing_dispatcher_creates_distinct_ids_for_sustained_matches(self):
        # Real publisher/id generation and dispatcher, fake HTTP; temporary outbox only.
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            poster = self.kws.AlertPoster("http://unused.invalid", Path(tmp) / "alerts.jsonl")
            dispatcher = self.kws.DetectionDispatcher(poster, self.kws.CooldownGate(2), 1.2, 2.2)
            for t in (1000, 1002, 1004):
                with patch.object(self.kws.time, "monotonic", return_value=t):
                    dispatcher.submit("sunog", .6, "openwakeword")
            self.assertEqual(len(poster.pending), 3)
            self.assertEqual(len({event["event_id"] for event in poster.pending}), 3)
            identity = poster.pending[0]["event_id"]
            poster.flush()
            self.assertEqual(poster.pending[0]["event_id"], identity)


if __name__ == "__main__":
    unittest.main()
