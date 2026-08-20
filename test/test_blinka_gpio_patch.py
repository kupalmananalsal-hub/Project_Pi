import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace

from raspberry_pi.scripts import patch_blinka_lgpio_pin as patcher


class FakeGPIOFilesystem:
    def __init__(self, root: Path):
        self.sysfs = root / "sys" / "bus" / "gpio" / "devices"
        self.dev = root / "dev"
        self.sysfs.mkdir(parents=True)
        self.dev.mkdir(parents=True)
        self._rdev_by_path: dict[str, tuple[int, int]] = {}

    def add_dev_node(self, name: str, major: int, minor: int) -> Path:
        path = self.dev / name
        path.touch()
        self._rdev_by_path[str(path)] = (major, minor)
        return path

    def add_sysfs_chip(
        self,
        name: str,
        label: str,
        major: int | None = None,
        minor: int | None = None,
    ) -> Path:
        path = self.sysfs / name
        path.mkdir()
        (path / "label").write_text(label, encoding="utf-8")
        if major is not None and minor is not None:
            (path / "dev").write_text(f"{major}:{minor}", encoding="utf-8")
        return path

    def add_chip(
        self,
        sysfs_name: str,
        label: str,
        dev_name: str,
        major: int,
        minor: int,
    ) -> None:
        self.add_dev_node(dev_name, major, minor)
        self.add_sysfs_chip(sysfs_name, label, major, minor)

    def stat(self, path: Path) -> SimpleNamespace:
        rdev = self._rdev_by_path.get(str(Path(path)))
        if rdev is None:
            raise FileNotFoundError(path)
        return SimpleNamespace(st_rdev=rdev)


class GPIODiscoveryTest(unittest.TestCase):
    def discover(self, fs: FakeGPIOFilesystem) -> int | None:
        return patcher.discover_rp1_gpiochip(
            fs.sysfs,
            fs.dev,
            stat_func=fs.stat,
            use_gpiodetect=False,
        )

    def test_single_digit_chip(self):
        with tempfile.TemporaryDirectory() as tmp:
            fs = FakeGPIOFilesystem(Path(tmp))
            fs.add_chip("gpiochip4", "pinctrl-rp1", "gpiochip4", 254, 4)

            self.assertEqual(self.discover(fs), 4)

    def test_multi_digit_chip(self):
        with tempfile.TemporaryDirectory() as tmp:
            fs = FakeGPIOFilesystem(Path(tmp))
            fs.add_chip("gpiochip15", "pinctrl-rp1", "gpiochip15", 254, 15)

            self.assertEqual(self.discover(fs), 15)

    def test_larger_multi_digit_chip(self):
        with tempfile.TemporaryDirectory() as tmp:
            fs = FakeGPIOFilesystem(Path(tmp))
            fs.add_chip("gpiochip123", "pinctrl-rp1", "gpiochip123", 254, 123)

            self.assertEqual(self.discover(fs), 123)

    def test_multiple_gpio_chips_selects_rp1(self):
        with tempfile.TemporaryDirectory() as tmp:
            fs = FakeGPIOFilesystem(Path(tmp))
            fs.add_chip("gpiochip11", "gpio-brcmstb@107d517c00", "gpiochip11", 254, 11)
            fs.add_chip("gpiochip12", "gpio-brcmstb@107d517c20", "gpiochip12", 254, 12)
            fs.add_chip("gpiochip15", "pinctrl-rp1", "gpiochip15", 254, 15)

            self.assertEqual(self.discover(fs), 15)

    def test_sysfs_index_differs_from_device_node_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            fs = FakeGPIOFilesystem(Path(tmp))
            fs.add_chip("gpiochip569", "pinctrl-rp1", "gpiochip15", 254, 15)

            self.assertEqual(self.discover(fs), 15)

    def test_no_rp1_controller_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            fs = FakeGPIOFilesystem(Path(tmp))
            fs.add_chip("gpiochip11", "gpio-brcmstb@107d517c00", "gpiochip11", 254, 11)

            self.assertIsNone(self.discover(fs))

    def test_missing_sysfs_fails_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fs = FakeGPIOFilesystem(root)

            self.assertIsNone(
                patcher.discover_rp1_gpiochip(
                    root / "missing-sysfs",
                    fs.dev,
                    stat_func=fs.stat,
                    use_gpiodetect=False,
                )
            )

    def test_malformed_dev_content_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            fs = FakeGPIOFilesystem(Path(tmp))
            fs.add_dev_node("gpiochip15", 254, 15)
            chip = fs.add_sysfs_chip("gpiochip569", "pinctrl-rp1")
            (chip / "dev").write_text("not-a-dev-id", encoding="utf-8")

            self.assertIsNone(self.discover(fs))

    def test_missing_device_node_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            fs = FakeGPIOFilesystem(Path(tmp))
            fs.add_sysfs_chip("gpiochip569", "pinctrl-rp1", 254, 15)

            self.assertIsNone(self.discover(fs))

    def test_explicit_valid_override_is_first_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            fs = FakeGPIOFilesystem(Path(tmp))
            fs.add_dev_node("gpiochip4", 254, 4)
            fs.add_chip("gpiochip569", "pinctrl-rp1", "gpiochip15", 254, 15)

            plan = patcher.gpiochip_candidates(
                override_value="4",
                sysfs_root=fs.sysfs,
                dev_root=fs.dev,
                stat_func=fs.stat,
                use_gpiodetect=False,
            )

            self.assertEqual(plan.candidates[:2], [4, 15])
            self.assertEqual(plan.override_chip, 4)
            self.assertEqual(plan.discovered_rp1, 15)

    def test_invalid_override_falls_back_to_dynamic_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            fs = FakeGPIOFilesystem(Path(tmp))
            fs.add_chip("gpiochip569", "pinctrl-rp1", "gpiochip15", 254, 15)

            plan = patcher.gpiochip_candidates(
                override_value="5",
                sysfs_root=fs.sysfs,
                dev_root=fs.dev,
                stat_func=fs.stat,
                use_gpiodetect=False,
            )

            self.assertEqual(plan.candidates[0], 15)
            self.assertIn("falling back", " ".join(plan.warnings))

    def test_full_number_parser_does_not_truncate(self):
        self.assertEqual(patcher.parse_gpiochip_number("gpiochip15"), 15)
        self.assertNotEqual(patcher.parse_gpiochip_number("gpiochip15"), 5)

    def test_gpiodetect_parser_uses_full_number(self):
        output = textwrap.dedent(
            """
            gpiochip11 [gpio-brcmstb@107d517c00]
            gpiochip15 [pinctrl-rp1]
            """
        )

        self.assertEqual(patcher.parse_gpiodetect_output(output), 15)


class BlinkaPatchTest(unittest.TestCase):
    BUGGY_SOURCE = textwrap.dedent(
        """
        import lgpio


        def _get_gpiochip():
            for dev in []:
                return lgpio.gpiochip_open(int(dev.name[-1]))
            raise RuntimeError("missing")


        def unrelated_function():
            return "keep me"
        """
    ).lstrip()

    def test_patcher_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lgpio_pin.py"
            path.write_text(self.BUGGY_SOURCE, encoding="utf-8")

            first = patcher.patch_file(path)
            first_text = path.read_text(encoding="utf-8")
            second = patcher.patch_file(path)
            second_text = path.read_text(encoding="utf-8")

            self.assertEqual(first, "patched")
            self.assertEqual(second, "already patched")
            self.assertEqual(first_text, second_text)

    def test_patcher_replaces_final_character_bug_with_dynamic_discovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lgpio_pin.py"
            path.write_text(self.BUGGY_SOURCE, encoding="utf-8")

            patcher.patch_file(path)
            patched = path.read_text(encoding="utf-8")

            self.assertNotIn("name[-1]", patched)
            self.assertIn("pinctrl-rp1", patched)
            self.assertIn("_project_pi_discover_rp1_gpiochip_from_sysfs", patched)
            self.assertIn("unrelated_function", patched)
            compile(patched, str(path), "exec")


if __name__ == "__main__":
    unittest.main()
