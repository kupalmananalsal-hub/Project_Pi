import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "raspberry_pi" / "thermal"))

from thermal_confidence import ThermalConfidenceScorer


class ThermalConfidenceTest(unittest.TestCase):
    def test_detects_partial_human_heat_signature(self):
        pixels = [24.0] * (32 * 24)
        for y in range(5, 21):
            for x in range(11, 21):
                pixels[(y * 32) + x] = 34.2

        scorer = ThermalConfidenceScorer(pixels)
        result = scorer.analyze()

        self.assertTrue(result["human_detected"])
        self.assertGreater(result["body_coverage"], 0.10)
        self.assertEqual(result["detected_part"], "torso_or_full_face")
        self.assertEqual(result["confidence_boost"], 0.15)

    def test_returns_zero_boost_for_cold_frame(self):
        scorer = ThermalConfidenceScorer([22.0] * (32 * 24))
        boost, label = scorer.get_confidence_boost()

        self.assertEqual(boost, 0.0)
        self.assertEqual(label, "no_human")


if __name__ == "__main__":
    unittest.main()
