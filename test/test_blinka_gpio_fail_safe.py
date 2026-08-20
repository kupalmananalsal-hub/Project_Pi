from __future__ import annotations

import unittest
from unittest import mock

from raspberry_pi.scripts import patch_blinka_lgpio_pin as patcher

class FailSafeGPIOFallbackTest(unittest.TestCase):
    def test_default_does_not_guess(self):
        with mock.patch.object(patcher, 'discover_rp1_gpiochip', return_value=None):
            plan = patcher.gpiochip_candidates(override_value=None, use_gpiodetect=False)
        self.assertEqual(plan.candidates, [])

    def test_explicit_fallback_still_supported(self):
        with mock.patch.object(patcher, 'discover_rp1_gpiochip', return_value=None):
            plan = patcher.gpiochip_candidates(override_value=None, fallback_chips=(15, 11, 4, 0), use_gpiodetect=False)
        self.assertEqual(plan.candidates, [15, 11, 4, 0])

if __name__ == '__main__':
    unittest.main()
