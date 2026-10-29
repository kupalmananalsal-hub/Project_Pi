import contextlib
import io
import json
import unittest

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "raspberry_pi"))
from alert_trace import trace_alert


class AlertTraceTest(unittest.TestCase):
    def test_event_id_stage_and_failure_are_machine_readable(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            trace_alert("http_post", "trace-123", "failed",
                        error_type="Timeout", pending_count=1)
        record = json.loads(output.getvalue())
        self.assertEqual(record["kind"], "alert_trace")
        self.assertEqual(record["event_id"], "trace-123")
        self.assertEqual(record["stage"], "http_post")
        self.assertEqual(record["outcome"], "failed")
        self.assertEqual(record["error_type"], "Timeout")
        self.assertNotIn("raw_audio", record)


if __name__ == "__main__":
    unittest.main()
