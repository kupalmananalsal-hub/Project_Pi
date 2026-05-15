import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "raspberry_pi"))

from alert_decision import AlertDecisionEngine


class AlertDecisionEngineTest(unittest.TestCase):
    def test_full_alert_when_keyword_and_thermal_are_strong(self):
        engine = AlertDecisionEngine()
        result = engine.evaluate(
            {
                "keyword": "help",
                "confidence": 0.80,
                "noise_level_db": -40.0,
                "signal_level_db": -12.0,
                "snr_db": 18.0,
            },
            {
                "human_detected": True,
                "body_coverage": 0.20,
                "detected_part": "torso_or_full_face",
                "confidence_boost": 0.15,
            },
        )

        self.assertTrue(result["should_alert"])
        self.assertEqual(result["alert_level"], "full_alert")
        self.assertGreaterEqual(result["final_confidence"], 0.85)

    def test_suppresses_low_confidence_without_human_heat(self):
        engine = AlertDecisionEngine()
        result = engine.evaluate(
            {
                "keyword": "help",
                "confidence": 0.60,
                "noise_level_db": -25.0,
                "signal_level_db": -20.0,
                "snr_db": 5.0,
            },
            {
                "human_detected": False,
                "body_coverage": 0.0,
                "detected_part": "no_human",
                "confidence_boost": 0.0,
            },
        )

        self.assertFalse(result["should_alert"])
        self.assertEqual(result["alert_level"], "none")
        self.assertLess(result["final_confidence"], 0.70)


if __name__ == "__main__":
    unittest.main()
