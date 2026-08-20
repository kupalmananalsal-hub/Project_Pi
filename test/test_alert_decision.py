import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "raspberry_pi"))

from alert_decision import AlertDecisionEngine, AlertPolicy


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class AlertDecisionEngineTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.policy = AlertPolicy(
            policy_version="test-policy",
            advisory_threshold=0.70,
            critical_threshold=0.85,
            thermal_freshness_seconds=1.25,
            repeat_window_seconds=5.0,
            repeat_required_count=2,
            repeat_escalates_to_critical=True,
        )
        self.engine = AlertDecisionEngine(policy=self.policy, clock=self.clock)

    def evaluate(self, confidence, thermal=None, keyword="help", **extra):
        event = {
            "keyword": keyword,
            "confidence": confidence,
            "noise_level_db": -45.0,
            "signal_level_db": -15.0,
            "snr_db": 25.0,
        }
        event.update(extra)
        return self.engine.evaluate(event, thermal)

    def positive_thermal(self, **extra):
        thermal = {
            "thermal_state": "positive",
            "human_detected": True,
            "body_coverage": 0.18,
            "detected_part": "torso_or_full_face",
            "confidence_boost": 0.15,
            "thermal_model_confidence": 0.91,
            "thermal_model_threshold": 0.55,
            "frame_age_seconds": 0.2,
            "frame_valid": True,
            "timestamp": "2026-08-20T00:00:00Z",
            "details": {
                "heuristic_human_detected": True,
                "heuristic_confidence_boost": 0.15,
            },
        }
        thermal.update(extra)
        return thermal

    def negative_thermal(self, **extra):
        thermal = {
            "thermal_state": "negative",
            "human_detected": False,
            "body_coverage": 0.0,
            "detected_part": "none",
            "confidence_boost": 0.0,
            "frame_age_seconds": 0.2,
            "frame_valid": True,
        }
        thermal.update(extra)
        return thermal

    def assert_decision(self, result, state, reason, modality, alert_level):
        self.assertEqual(result["decision_state"], state)
        self.assertEqual(result["decision_reason"], reason)
        self.assertEqual(result["alert_modality"], modality)
        self.assertEqual(result["alert_level"], alert_level)

    def test_low_voice_no_thermal_is_suppressed(self):
        result = self.evaluate(0.20, None)

        self.assert_decision(
            result,
            "suppressed",
            "voice_below_threshold",
            "voice_only",
            "none",
        )
        self.assertFalse(result["should_alert"])
        self.assertEqual(result["thermal_state"], "unavailable")

    def test_medium_voice_positive_thermal_is_confirmed(self):
        result = self.evaluate(0.75, self.positive_thermal())

        self.assert_decision(
            result,
            "confirmed",
            "voice_confirmed_by_thermal",
            "voice_thermal",
            "full_alert",
        )
        self.assertTrue(result["should_alert"])

    def test_medium_voice_negative_thermal_is_advisory(self):
        result = self.evaluate(0.75, self.negative_thermal())

        self.assert_decision(
            result,
            "advisory",
            "thermal_negative",
            "voice_only",
            "visual_only",
        )
        self.assertEqual(result["thermal_state"], "negative")

    def test_medium_voice_unavailable_thermal_is_advisory(self):
        result = self.evaluate(0.75, {"thermal_state": "unavailable"})

        self.assert_decision(
            result,
            "advisory",
            "thermal_unavailable",
            "voice_only",
            "visual_only",
        )
        self.assertEqual(result["thermal_state"], "unavailable")

    def test_medium_voice_stale_thermal_is_advisory_without_stale_boost(self):
        result = self.evaluate(
            0.75,
            self.positive_thermal(frame_age_seconds=2.0),
        )

        self.assert_decision(
            result,
            "advisory",
            "thermal_stale",
            "voice_only",
            "visual_only",
        )
        self.assertEqual(result["thermal_state"], "stale")
        self.assertEqual(result["decision_factors"]["thermal_boost"], 0.0)
        self.assertEqual(result["decision_factors"]["raw_thermal_boost"], 0.15)

    def test_medium_voice_invalid_thermal_is_advisory(self):
        result = self.evaluate(
            0.75,
            self.positive_thermal(frame_valid=False),
        )

        self.assert_decision(
            result,
            "advisory",
            "thermal_invalid",
            "voice_only",
            "visual_only",
        )
        self.assertEqual(result["thermal_state"], "invalid")

    def test_high_voice_no_thermal_is_critical(self):
        result = self.evaluate(0.95, None)

        self.assert_decision(
            result,
            "critical",
            "voice_high_confidence",
            "voice_only",
            "full_alert",
        )

    def test_high_voice_negative_thermal_is_critical(self):
        result = self.evaluate(0.95, self.negative_thermal())

        self.assert_decision(
            result,
            "critical",
            "voice_high_confidence",
            "voice_only",
            "full_alert",
        )

    def test_high_voice_positive_thermal_is_critical_voice_thermal(self):
        result = self.evaluate(0.95, self.positive_thermal())

        self.assert_decision(
            result,
            "critical",
            "voice_confirmed_by_thermal",
            "voice_thermal",
            "full_alert",
        )

    def test_repeated_medium_voice_escalates(self):
        first = self.evaluate(0.75, self.negative_thermal())
        self.clock.advance(2.0)
        second = self.evaluate(0.76, self.negative_thermal())

        self.assertEqual(first["decision_state"], "advisory")
        self.assert_decision(
            second,
            "critical",
            "repeated_distress_escalation",
            "voice_only",
            "full_alert",
        )
        self.assertEqual(second["decision_factors"]["repeat_count"], 2)

    def test_repeat_window_expiry_prevents_escalation(self):
        first = self.evaluate(0.75, self.negative_thermal())
        self.clock.advance(6.0)
        second = self.evaluate(0.76, self.negative_thermal())

        self.assertEqual(first["decision_state"], "advisory")
        self.assert_decision(
            second,
            "advisory",
            "thermal_negative",
            "voice_only",
            "visual_only",
        )
        self.assertEqual(second["decision_factors"]["repeat_count"], 1)

    def test_different_phrases_do_not_share_repeat_state(self):
        first = self.evaluate(0.75, self.negative_thermal(), keyword="help")
        self.clock.advance(2.0)
        second = self.evaluate(0.76, self.negative_thermal(), keyword="tulong")

        self.assertEqual(first["decision_state"], "advisory")
        self.assertEqual(second["decision_state"], "advisory")
        self.assertEqual(second["decision_factors"]["repeat_count"], 1)

    def test_exact_advisory_threshold(self):
        result = self.evaluate(0.70, self.negative_thermal())

        self.assert_decision(
            result,
            "advisory",
            "thermal_negative",
            "voice_only",
            "visual_only",
        )

    def test_exact_critical_threshold(self):
        result = self.evaluate(0.85, self.negative_thermal())

        self.assert_decision(
            result,
            "critical",
            "voice_high_confidence",
            "voice_only",
            "full_alert",
        )

    def test_missing_optional_thermal_fields_do_not_crash(self):
        result = self.evaluate(0.75, {})

        self.assertEqual(result["decision_state"], "advisory")
        self.assertEqual(result["decision_reason"], "thermal_unavailable")
        self.assertEqual(result["thermal_state"], "unavailable")

    def test_missing_optional_engine_scores_do_not_crash(self):
        result = self.engine.evaluate({"keyword": "help"}, None)

        self.assert_decision(
            result,
            "suppressed",
            "voice_below_threshold",
            "voice_only",
            "none",
        )
        self.assertEqual(result["keyword_confidence"], 0.0)

    def test_backward_compatible_legacy_fields(self):
        result = self.evaluate(0.95, self.positive_thermal())

        self.assertEqual(result["alert_level"], "full_alert")
        self.assertTrue(result["should_alert"])
        self.assertEqual(result["keyword_confidence"], 0.95)
        self.assertIn("final_confidence", result)
        self.assertIn("decision_factors", result)

    def test_suppressed_legacy_mapping_stays_none(self):
        result = self.evaluate(0.10, self.negative_thermal())

        self.assertEqual(result["decision_state"], "suppressed")
        self.assertEqual(result["alert_level"], "none")
        self.assertFalse(result["should_alert"])


if __name__ == "__main__":
    unittest.main()
