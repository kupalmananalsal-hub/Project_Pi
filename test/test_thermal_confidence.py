import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "raspberry_pi" / "thermal"))

from thermal_confidence import (
    ThermalConfidenceScorer,
    SHAPE_CLASS_NAMES,
    SHAPE_HUMAN_CLASS_IDS,
)


def _make_frame(bg: float = 24.0, blob_temp: float = 34.2,
                blob_rows=(8, 16), blob_cols=(12, 20)) -> np.ndarray:
    """Return a 24x32 frame with a temperature blob inserted."""
    frame = np.full((24, 32), bg, dtype=np.float32)
    frame[blob_rows[0]:blob_rows[1], blob_cols[0]:blob_cols[1]] = blob_temp
    return frame


def _make_scorer_with_shape_mock(probs: list[float]) -> ThermalConfidenceScorer:
    """Create a scorer whose shape model returns the given softmax probabilities."""
    scorer = ThermalConfidenceScorer()

    mock_interp = MagicMock()
    mock_interp.get_input_details.return_value = [{
        "index": 0, "shape": [1, 24, 32, 1], "dtype": np.float32,
    }]
    mock_interp.get_output_details.return_value = [{
        "index": 0, "shape": [1, 9], "dtype": np.float32,
    }]
    mock_interp.get_tensor.return_value = np.array([probs], dtype=np.float32)

    scorer._shape_interpreter = mock_interp
    scorer._shape_input_details = mock_interp.get_input_details()
    scorer._shape_output_details = mock_interp.get_output_details()
    scorer._shape_threshold = 0.65
    return scorer


def _make_scorer_with_temp_model_mock(
    model_conf: float = 0.90,
    temporal_required: bool = False,
) -> ThermalConfidenceScorer:
    """Create a scorer with a mocked TFLite temperature model (no real hardware needed)."""
    scorer = ThermalConfidenceScorer()
    scorer.temporal_required = temporal_required
    scorer.model_threshold = 0.55

    mock_interp = MagicMock()
    mock_interp.get_input_details.return_value = [
        {"index": 0, "shape": [1, 24, 32, 1], "dtype": np.float32}
    ]
    mock_interp.get_output_details.return_value = [
        {"index": 1, "shape": [1, 1], "dtype": np.float32}
    ]
    # Return a scalar confidence regardless of which tensor index is requested.
    mock_interp.get_tensor.return_value = np.array([[model_conf]], dtype=np.float32)

    scorer._interpreter = mock_interp
    scorer._input_details = [{"index": 0, "shape": [1, 24, 32, 1], "dtype": np.float32}]
    scorer._output_details = [{"index": 1, "shape": [1, 1], "dtype": np.float32}]
    return scorer


class ThermalConfidenceTest(unittest.TestCase):
    # ── Original tests (backward-compat) ──────────────────────────────────────

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

    # ── Shape model: FP suppression ──────────────────────────────────────────

    def test_hot_object_suppresses_human_detection(self):
        """hot_object prediction with high confidence must force human_detected=False."""
        # Frame has a warm blob that would normally trigger heuristic detection
        frame = _make_frame(bg=24.0, blob_temp=34.2)
        # hot_object = class index 6
        probs = [0.01] * 9
        probs[6] = 0.92  # hot_object dominant
        scorer = _make_scorer_with_shape_mock(probs)

        result = scorer.analyze(frame)

        self.assertFalse(result["human_detected"], "hot_object must suppress human_detected")
        self.assertTrue(result["thermal_shape_hot_object"])
        self.assertFalse(result["thermal_shape_human"])
        self.assertTrue(result["details"].get("shape_suppressed", False))

    def test_background_suppresses_human_detection(self):
        """background prediction with high confidence must force human_detected=False."""
        frame = _make_frame(bg=24.0, blob_temp=34.2)
        probs = [0.01] * 9
        probs[7] = 0.88  # background dominant
        scorer = _make_scorer_with_shape_mock(probs)

        result = scorer.analyze(frame)

        self.assertFalse(result["human_detected"])
        self.assertTrue(result["thermal_shape_background"])
        self.assertTrue(result["details"].get("shape_suppressed", False))

    def test_human_torso_detected_correctly(self):
        """human_torso class must set thermal_shape_human=True and body_part=torso."""
        frame = _make_frame(bg=24.0, blob_temp=34.2)
        probs = [0.0] * 9
        probs[3] = 0.91  # human_torso at index 3
        scorer = _make_scorer_with_shape_mock(probs)

        result = scorer.analyze(frame)

        self.assertTrue(result["thermal_shape_human"])
        self.assertEqual(result["thermal_shape_body_part"], "torso")
        self.assertFalse(result["thermal_shape_hot_object"])
        self.assertFalse(result["thermal_shape_background"])
        self.assertTrue(result["human_detected"])

    def test_human_classes_all_identified(self):
        """Each of the 6 human classes should produce thermal_shape_human=True."""
        frame = _make_frame(bg=24.0, blob_temp=34.2)
        human_classes = [
            (0, "full"), (1, "partial"), (2, "head"),
            (3, "torso"), (4, "hands"), (5, "feet"),
        ]
        for idx, expected_part in human_classes:
            probs = [0.01] * 9
            probs[idx] = 0.90
            scorer = _make_scorer_with_shape_mock(probs)
            result = scorer.analyze(frame)
            with self.subTest(class_idx=idx, label=SHAPE_CLASS_NAMES[idx]):
                self.assertTrue(result["thermal_shape_human"],
                                f"class {SHAPE_CLASS_NAMES[idx]} should be human")
                self.assertEqual(result["thermal_shape_body_part"], expected_part)

    def test_ambiguous_does_not_suppress_or_boost(self):
        """ambiguous class must leave the temp-model/heuristic result unchanged."""
        frame = _make_frame(bg=24.0, blob_temp=34.2)
        probs = [0.0] * 9
        probs[8] = 0.95  # ambiguous
        scorer = _make_scorer_with_shape_mock(probs)

        result = scorer.analyze(frame)

        # Heuristic should still detect human (warm blob present)
        self.assertTrue(result["human_detected"])
        # Shape model must not have suppressed or added shape_suppressed flag
        self.assertFalse(result["details"].get("shape_suppressed", False))
        # thermal_shape_human is False because ambiguous is not a human class
        self.assertFalse(result["thermal_shape_human"])

    # ── Shape model: missing model falls back gracefully ──────────────────────

    def test_missing_shape_model_does_not_break_detection(self):
        """When shape model is absent the scorer must still work via heuristic."""
        frame = _make_frame(bg=24.0, blob_temp=34.2)
        scorer = ThermalConfidenceScorer()
        # Ensure shape model is definitely not loaded
        self.assertIsNone(scorer._shape_interpreter)

        result = scorer.analyze(frame)

        # Heuristic detection still works
        self.assertTrue(result["human_detected"])
        # Shape fields are present but show unavailable
        self.assertFalse(result["thermal_shape_available"])
        self.assertFalse(result["thermal_shape_human"])

    # ── Backward compatibility ────────────────────────────────────────────────

    def test_backward_compat_fields_always_present(self):
        """Original fields must always be present regardless of shape model state."""
        required = [
            "human_detected", "confidence_boost", "body_coverage",
            "detected_part", "human_pixel_count",
        ]
        frame = _make_frame(bg=24.0, blob_temp=34.2)
        scorer = ThermalConfidenceScorer()
        result = scorer.analyze(frame)

        for field in required:
            self.assertIn(field, result, f"Missing backward-compat field: {field}")

    # ── Status API ────────────────────────────────────────────────────────────

    def test_status_includes_shape_model_fields(self):
        """status() must expose shape model availability and path."""
        scorer = ThermalConfidenceScorer()
        s = scorer.status()
        self.assertIn("thermal_shape_model_available", s)
        self.assertIn("thermal_shape_model_path", s)
        self.assertIn("thermal_shape_threshold", s)

    # ── Both models run without conflict ──────────────────────────────────────

    def test_both_models_run_without_conflict(self):
        """Running with a mocked shape model must not affect existing output keys."""
        frame = _make_frame(bg=24.0, blob_temp=34.2)
        # human_full at high confidence
        probs = [0.0] * 9
        probs[0] = 0.95
        scorer = _make_scorer_with_shape_mock(probs)

        result = scorer.analyze(frame)

        # Both sets of keys must coexist
        for key in ("human_detected", "confidence_boost", "body_coverage", "detected_part"):
            self.assertIn(key, result, f"Original key missing: {key}")
        for key in ("thermal_shape_human", "thermal_shape_body_part",
                    "thermal_shape_hot_object", "thermal_shape_background",
                    "thermal_shape_confidence", "thermal_shape_label"):
            self.assertIn(key, result, f"Shape key missing: {key}")

    # ── False-positive: aspect ratio ─────────────────────────────────────────

    def test_wide_flat_blob_rejected_by_aspect_ratio(self):
        """A wide, flat warm blob (laptop / heater surface) must not be human."""
        frame = np.full((24, 32), 24.0, dtype=np.float32)
        # 2 rows × 20 cols → aspect_ratio = 2/20 = 0.10  (below MIN 0.3)
        frame[11:13, 6:26] = 34.2
        scorer = ThermalConfidenceScorer()

        result = scorer.analyze(frame)

        self.assertFalse(result["human_detected"],
                         "Wide flat blob must not be detected as human")
        self.assertIn("aspect_ratio_rejected", result["details"].get("reason", ""))

    # ── False-positive: max coverage ─────────────────────────────────────────

    def test_oversized_blob_rejected_by_max_coverage(self):
        """A warm blob covering more than MAX_BODY_COVERAGE must not be human."""
        # Entire 24×32 frame at body temperature — clearly a warm environment,
        # not a person.
        frame = np.full((24, 32), 34.2, dtype=np.float32)
        scorer = ThermalConfidenceScorer()

        result = scorer.analyze(frame)

        self.assertFalse(result["human_detected"],
                         "Full-frame warm blob must be rejected as non-human")

    # ── Temporal consistency in TFLite model path ─────────────────────────────

    def test_temporal_consistency_blocks_model_on_first_frame(self):
        """TFLite model must not report human on the first frame when temporal_required=True."""
        frame = _make_frame(bg=24.0, blob_temp=34.2)
        scorer = _make_scorer_with_temp_model_mock(model_conf=0.90, temporal_required=True)

        result = scorer.analyze(frame)

        self.assertFalse(result["human_detected"],
                         "First frame must not detect with temporal_required=True")

    def test_temporal_consistency_allows_model_after_consecutive_frames(self):
        """After REQUIRED_CONSECUTIVE_FRAMES the TFLite model may confirm detection."""
        frame = _make_frame(bg=24.0, blob_temp=34.2)
        scorer = _make_scorer_with_temp_model_mock(model_conf=0.90, temporal_required=True)

        # Warm-up: frames 1 and 2 must not detect.
        for _ in range(ThermalConfidenceScorer.REQUIRED_CONSECUTIVE_FRAMES - 1):
            scorer.analyze(frame)
        # Frame 3 (or REQUIRED_CONSECUTIVE_FRAMES) must now detect.
        result = scorer.analyze(frame)

        self.assertTrue(result["human_detected"],
                        "Must detect after REQUIRED_CONSECUTIVE_FRAMES consecutive frames")

    # ── Temporal consistency in shape-model promotion ─────────────────────────

    def test_shape_promotion_blocked_by_temporal_gate_first_frame(self):
        """Shape model must not promote human_detected=True on the first frame
        when temporal_required=True — even at very high confidence."""
        frame = _make_frame(bg=24.0, blob_temp=34.2)
        probs = [0.0] * 9
        probs[0] = 0.95   # human_full — maximum confidence shape hit
        scorer = _make_scorer_with_shape_mock(probs)
        scorer.temporal_required = True

        result = scorer.analyze(frame)

        self.assertFalse(result["human_detected"],
                         "Shape promotion must be blocked by temporal gate on frame 1")

    def test_shape_promotion_allowed_after_temporal_gate_satisfied(self):
        """Shape model may promote human_detected after temporal requirements are met."""
        frame = _make_frame(bg=24.0, blob_temp=34.2)
        probs = [0.0] * 9
        probs[0] = 0.95   # human_full
        scorer = _make_scorer_with_shape_mock(probs)
        scorer.temporal_required = True

        for _ in range(ThermalConfidenceScorer.REQUIRED_CONSECUTIVE_FRAMES - 1):
            scorer.analyze(frame)
        result = scorer.analyze(frame)

        self.assertTrue(result["human_detected"],
                        "Shape promotion must succeed once temporal gate is satisfied")


if __name__ == "__main__":
    unittest.main()
