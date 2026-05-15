import sys
import unittest
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "raspberry_pi" / "kws"))

from noise_suppressor import NoiseSuppressor


class NoiseSuppressorTest(unittest.TestCase):
    def test_capture_noise_profile_and_metrics(self):
        suppressor = NoiseSuppressor(sample_rate=16000, noise_profile_seconds=0.25)
        silence = np.zeros(4000, dtype=np.int16)

        ready = suppressor.capture_noise_profile(silence)

        self.assertTrue(ready)
        self.assertTrue(suppressor.profile_ready)
        self.assertLessEqual(suppressor.last_metrics.noise_level_db, -80.0)

    def test_suppression_preserves_signal_shape(self):
        sample_rate = 16000
        t = np.arange(1600, dtype=np.float32) / sample_rate
        clean = np.sin(2 * np.pi * 700 * t) * 14000
        noise = np.random.default_rng(7).normal(0, 2000, size=t.size)
        noisy = (clean + noise).astype(np.int16)

        suppressor = NoiseSuppressor(sample_rate=sample_rate, noise_profile_seconds=0.1)
        suppressor.capture_noise_profile(noise.astype(np.int16))
        denoised = suppressor.suppress_noise(noisy)

        self.assertEqual(denoised.dtype, np.int16)
        self.assertEqual(denoised.shape, noisy.shape)
        self.assertGreater(np.max(np.abs(denoised)), 1000)


if __name__ == "__main__":
    unittest.main()
