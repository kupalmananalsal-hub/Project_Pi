import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "raspberry_pi" / "thermal" / "collect_thermal_dataset.py"


def load_module():
    spec = importlib.util.spec_from_file_location("collect_thermal_dataset", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ThermalDatasetCollectorTests(unittest.TestCase):
    def test_append_frame_creates_schema_and_preserves_raw_values(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "thermal_backgrounds.csv"
            frame = [float(index) for index in range(768)]

            module.append_frame(
                path,
                frame,
                label="laptop",
                scene_type="office",
                notes="warm keyboard",
                session_id="session-1",
                timestamp="2026-08-26T00:00:00+00:00",
            )

            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["label"], "laptop")
            self.assertEqual(rows[0]["scene_type"], "office")
            self.assertEqual(rows[0]["temperature_0"], "0.0")
            self.assertEqual(rows[0]["temperature_767"], "767.0")

    def test_append_frame_appends_without_rewriting_previous_session(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "thermal_backgrounds.csv"
            module.append_frame(path, [1.0] * 768, "hot_room", "bedroom", "first", "a", "t1")
            module.append_frame(path, [2.0] * 768, "sunlight", "living_room", "second", "b", "t2")

            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual([row["session_id"] for row in rows], ["a", "b"])
            self.assertEqual(rows[0]["temperature_0"], "1.0")
            self.assertEqual(rows[1]["temperature_0"], "2.0")


if __name__ == "__main__":
    unittest.main()
