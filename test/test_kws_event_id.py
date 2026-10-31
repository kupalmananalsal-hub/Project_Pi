import importlib.util
import json
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KWS_MODULE = PROJECT_ROOT / "raspberry_pi" / "kws" / "kws_alert_dual.py"
KWS_ROOT = PROJECT_ROOT / "raspberry_pi" / "kws"


class FakeSession:
    def __init__(self):
        self.posts = []
        self.fail = True

    def post(self, url, json, timeout):
        del url, timeout
        self.posts.append(dict(json))
        if self.fail:
            raise RuntimeError("backend offline")
        return types.SimpleNamespace(raise_for_status=lambda: None)


def install_kws_stubs():
    stubs = {
        "numpy": types.ModuleType("numpy"),
        "pyaudio": types.ModuleType("pyaudio"),
        "requests": types.ModuleType("requests"),
        "vosk": types.ModuleType("vosk"),
        "audio_preprocessor": types.ModuleType("audio_preprocessor"),
        "noise_suppressor": types.ModuleType("noise_suppressor"),
        "wav2vec2_verifier": types.ModuleType("wav2vec2_verifier"),
    }
    stubs["numpy"].float32 = float
    stubs["numpy"].int16 = int
    stubs["numpy"].clip = lambda value, lower, upper: max(lower, min(upper, value))
    stubs["requests"].Session = FakeSession
    stubs["vosk"].KaldiRecognizer = object
    stubs["vosk"].Model = object
    stubs["audio_preprocessor"].AudioPreprocessor = object
    stubs["noise_suppressor"].DEFAULT_CONFIG_PATH = Path("noise.json")
    stubs["noise_suppressor"].NoiseSuppressionConfigStore = object
    stubs["noise_suppressor"].NoiseSuppressor = object
    stubs["wav2vec2_verifier"].Wav2Vec2Verifier = object

    previous = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    if str(KWS_ROOT) not in sys.path:
        sys.path.insert(0, str(KWS_ROOT))
    return previous


def restore_modules(previous):
    for name, module in previous.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def load_kws_module():
    previous = install_kws_stubs()
    try:
        spec = importlib.util.spec_from_file_location(
            "project_pi_kws_event_id_test",
            KWS_MODULE,
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module, previous
    except Exception:
        restore_modules(previous)
        raise


class KwsEventIdTest(unittest.TestCase):
    def make_poster(self, module, queue_path):
        poster = module.AlertPoster("http://backend/api/alerts", queue_path)
        poster.session = FakeSession()
        return poster

    def test_new_event_receives_event_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                poster = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                poster.publish("help", 0.9, "openwakeword")

                self.assertEqual(len(poster.pending), 1)
                self.assertIsInstance(poster.pending[0]["event_id"], str)
                self.assertTrue(poster.pending[0]["event_id"])
            finally:
                restore_modules(previous)

    def test_event_id_remains_unchanged_across_retries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                poster = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                poster.publish("help", 0.9, "openwakeword")
                event_id = poster.pending[0]["event_id"]
                poster.flush()

                posted_ids = [post["event_id"] for post in poster.session.posts]
                self.assertGreaterEqual(len(posted_ids), 2)
                self.assertEqual(set(posted_ids), {event_id})
                self.assertEqual(poster.pending[0]["event_id"], event_id)
            finally:
                restore_modules(previous)

    def test_serialization_and_deserialization_preserve_event_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                queue_path = Path(temp_dir) / "alerts.jsonl"
                poster = self.make_poster(module, queue_path)
                poster.publish("help", 0.9, "openwakeword")
                event_id = poster.pending[0]["event_id"]

                reloaded = self.make_poster(module, queue_path)
                self.assertEqual(reloaded.pending[0]["event_id"], event_id)
            finally:
                restore_modules(previous)

    def test_legacy_queued_event_gets_one_persistent_event_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                queue_path = Path(temp_dir) / "alerts.jsonl"
                queue_path.write_text(
                    json.dumps(
                        {
                            "event": "keyword_detected",
                            "keyword": "help",
                            "confidence": 0.9,
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )

                first_load = self.make_poster(module, queue_path)
                event_id = first_load.pending[0]["event_id"]
                second_load = self.make_poster(module, queue_path)

                self.assertTrue(event_id)
                self.assertEqual(second_load.pending[0]["event_id"], event_id)
            finally:
                restore_modules(previous)

    def test_two_independent_detections_receive_different_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                poster = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                poster.publish("help", 0.9, "openwakeword")
                poster.publish("tulong", 0.91, "openwakeword")

                ids = {event["event_id"] for event in poster.pending}
                self.assertEqual(len(ids), 2)
            finally:
                restore_modules(previous)

    def test_failed_posting_does_not_regenerate_event_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                poster = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                poster.publish("help", 0.9, "openwakeword")
                event_id = poster.pending[0]["event_id"]

                for _ in range(3):
                    poster.flush()

                self.assertEqual(poster.pending[0]["event_id"], event_id)
                self.assertEqual(
                    {post["event_id"] for post in poster.session.posts},
                    {event_id},
                )
            finally:
                restore_modules(previous)

    class StatusSession(FakeSession):
        def __init__(self, codes):
            super().__init__()
            self.codes = list(codes)

        def post(self, url, json, timeout):
            self.posts.append(dict(json))
            code = self.codes.pop(0)

            def raise_for_status():
                if code >= 400:
                    raise RuntimeError(f"HTTP {code}")
            return types.SimpleNamespace(status_code=code, text=f"detail {code}",
                                         raise_for_status=raise_for_status)

    def test_non_retryable_rejection_is_quarantined_so_queue_keeps_moving(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                poster = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                # 409 conflict is quarantined; 503 and 401 stay queued for retry.
                poster.session = self.StatusSession([409, 503, 401])
                poster.publish("help", 0.9, "openwakeword")
                poster.publish("tulong", 0.9, "openwakeword")
                poster.flush()
                poster.flush()
                self.assertEqual([event["keyword"] for event in poster.pending], ["tulong"])
                self.assertEqual([event["keyword"] for event in poster.quarantined], ["help"])
            finally:
                restore_modules(previous)

    def test_permanent_rejections_are_quarantined_once_and_never_silently_lost(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                queue_path = Path(temp_dir) / "alerts.jsonl"
                poster = self.make_poster(module, queue_path)
                poster.flush = lambda: None
                poster.publish("crit", 0.95, "vosk")   # certain_critical
                poster.publish("poss", 0.50, "vosk")   # possible_critical
                poster.publish("low", 0.10, "vosk")    # certain_suppressed
                poster.publish("ok", 0.95, "vosk")
                del poster.flush
                traces = []
                module.trace_alert = lambda *args, **kwargs: traces.append((args, kwargs))
                poster.session = self.StatusSession([409, 422, 400, 200])
                for _ in range(3):  # repeated flushes must not re-post rejected events
                    poster.flush()

                self.assertEqual(len(poster.session.posts), 4)
                self.assertEqual(poster.pending, [])  # later alert was not blocked
                rejected = [json.loads(line) for line in
                            (Path(temp_dir) / "alerts.rejected.jsonl").read_text(
                                encoding="utf-8").splitlines()]
                self.assertEqual([(r["keyword"], r["rejected_status"], r["retention_tier"])
                                  for r in rejected],
                                 [("crit", 409, 3), ("poss", 422, 2), ("low", 400, 1)])
                self.assertTrue(all(r["rejected_at"] and r["event_id"] for r in rejected))
                status = poster.outbox_status()
                self.assertEqual((status["quarantined"], status["quarantined_possibly_critical"]),
                                 (3, 2))
                outcomes = [(args[2], kwargs.get("status_code")) for args, kwargs in traces
                            if args[0] == "http_post"]
                self.assertEqual(outcomes, [("quarantined", 409), ("quarantined", 422),
                                            ("quarantined", 400), ("succeeded", 200)])

                # Survives a KWS restart, so the health fault persists until reviewed.
                restarted = self.make_poster(module, queue_path)
                self.assertEqual(restarted.outbox_status()["quarantined_possibly_critical"], 2)
            finally:
                restore_modules(previous)

    def test_quarantine_is_bounded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                module.MAX_QUARANTINED_ALERTS = 2
                poster = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                poster.session = self.StatusSession([422] * 6)
                for keyword, confidence in (("low1", 0.1), ("crit1", 0.9), ("poss1", 0.5),
                                            ("low2", 0.1)):
                    poster.publish(keyword, confidence, "vosk")
                # Soft limit: only certain_suppressed records go; possibly-critical ones stay.
                self.assertEqual([e["keyword"] for e in poster.quarantined], ["crit1", "poss1"])
                self.assertEqual(poster.outbox_status()["quarantine_critical_evictions"], 0)
                # Hard limit: lowest tier, oldest first, counted for the health fault.
                module.HARD_MAX_PENDING_ALERTS = 2
                poster.publish("crit2", 0.9, "vosk")
                self.assertEqual([e["keyword"] for e in poster.quarantined], ["crit1", "crit2"])
                poster.publish("crit3", 0.9, "vosk")
                self.assertEqual([e["keyword"] for e in poster.quarantined], ["crit2", "crit3"])
                self.assertEqual(poster.outbox_status()["quarantine_critical_evictions"], 2)

                # The loss indicator survives a KWS restart (and power cut: fsynced file),
                # even when the quarantine no longer holds any trace of the lost events.
                (Path(temp_dir) / "alerts.rejected.jsonl").unlink()
                restarted = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                self.assertEqual(restarted.quarantined, [])
                self.assertEqual(restarted.outbox_status()["quarantine_critical_evictions"], 2)
                ledger = json.loads((Path(temp_dir) / "alerts.losses.json").read_text(encoding="utf-8"))
                self.assertEqual([r["keyword"] for r in ledger["recent"]], ["poss1", "crit1"])
                # Only the operator's explicit resolution (moving the ledger away) clears it.
                (Path(temp_dir) / "alerts.losses.json").rename(Path(temp_dir) / "reviewed.json")
                cleared = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                self.assertEqual(cleared.outbox_status()["quarantine_critical_evictions"], 0)
            finally:
                restore_modules(previous)

    def bounded_poster(self, module, temp_dir, soft=3, hard=6, hard_bytes=10**6):
        module.MAX_PENDING_ALERTS = soft
        module.HARD_MAX_PENDING_ALERTS = hard
        module.HARD_MAX_PENDING_BYTES = hard_bytes
        poster = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
        poster.flush = lambda: None
        return poster

    def test_retention_tier_at_each_policy_boundary(self):
        module, previous = load_kws_module()
        try:
            policy = module.AlertPolicy(advisory_threshold=0.30, critical_threshold=0.85)

            def tier(**event):
                return module.retention_tier(event, policy)

            self.assertEqual(tier(confidence=0.85, source="vosk"), 3)
            self.assertEqual(tier(confidence=0.8499, source="vosk"), 2)
            self.assertEqual(tier(confidence=0.30, source="vosk"), 2)
            self.assertEqual(tier(confidence=0.2999, source="vosk"), 1)
            self.assertEqual(tier(confidence=0.0, source="manual_button"), 3)
            self.assertEqual(tier(confidence=0.0, source="manual_button_single"), 2)
            self.assertEqual(tier(confidence=0.0, source="health_monitor"), 2)
            self.assertEqual(tier(confidence=0.0, event="system_fault"), 2)
            self.assertEqual(tier(confidence="not-a-number"), 1)  # backend reads it as 0.0
            self.assertEqual(tier(confidence=float("nan")), 2)
        finally:
            restore_modules(previous)

    def test_retention_tier_agrees_with_backend_classification(self):
        """Tier 3 is CRITICAL and tier 1 SUPPRESSED whatever the thermal state."""
        module, previous = load_kws_module()
        try:
            policy = module.AlertPolicy()
            positive = {"thermal_state": "positive", "human_detected": True,
                        "body_coverage": 0.18, "frame_age_seconds": 0.2, "frame_valid": True,
                        "confidence_boost": 0.15}
            for source in ("vosk", "manual_button", "manual_button_single"):
                for confidence in (0.0, 0.2999, 0.30, 0.5, 0.8499, 0.85, 1.0):
                    event = {"keyword": "help", "confidence": confidence, "source": source,
                             "snr_db": 25.0}
                    states = {
                        module.AlertDecisionEngine(policy=policy).evaluate(dict(event), thermal)[
                            "decision_state"]
                        for thermal in (None, positive)
                    }
                    tier = module.retention_tier(event, policy)
                    if tier == 3:
                        self.assertEqual(states, {"critical"}, event)
                    elif tier == 1:
                        self.assertEqual(states, {"suppressed"}, event)
                    else:
                        self.assertNotIn("suppressed", states, event)
        finally:
            restore_modules(previous)

    def test_soft_limit_evicts_suppressed_then_possible_never_certain_critical(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                poster = self.bounded_poster(module, temp_dir)
                poster.publish("crit1", 0.9, "vosk")
                poster.publish("poss1", 0.5, "vosk")
                poster.publish("low1", 0.1, "vosk")
                poster.publish("poss2", 0.5, "vosk")
                self.assertEqual([e["keyword"] for e in poster.pending], ["crit1", "poss1", "poss2"])
                poster.publish("crit2", 0.9, "vosk")
                self.assertEqual([e["keyword"] for e in poster.pending], ["crit1", "poss2", "crit2"])
                poster.publish("crit3", 0.9, "vosk")
                poster.publish("crit4", 0.9, "vosk")
                # Over the soft limit, certain_critical events are kept, with pressure published.
                self.assertEqual([e["keyword"] for e in poster.pending],
                                 ["crit1", "crit2", "crit3", "crit4"])
                status = poster.outbox_status()
                self.assertTrue(status["pressure"])
                self.assertEqual(status["evictions"], 3)
                self.assertEqual(status["critical_evictions"], 0)
                self.assertEqual(
                    [json.loads(line)["keyword"] for line in
                     (Path(temp_dir) / "alerts.jsonl").read_text(encoding="utf-8").splitlines()],
                    ["crit1", "crit2", "crit3", "crit4"])
            finally:
                restore_modules(previous)

    def test_hard_count_limit_evicts_oldest_certain_critical_and_counts_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                poster = self.bounded_poster(module, temp_dir, soft=2, hard=3)
                for index in range(5):
                    poster.publish(f"crit{index}", 0.95, "vosk")
                self.assertEqual([e["keyword"] for e in poster.pending], ["crit2", "crit3", "crit4"])
                self.assertEqual(poster.outbox_status()["critical_evictions"], 2)
                restarted = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                self.assertEqual(restarted.outbox_status()["critical_evictions"], 2)
            finally:
                restore_modules(previous)

    def test_unreadable_loss_ledger_is_kept_aside_and_still_reported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                (Path(temp_dir) / "alerts.losses.json").write_text("{not json", encoding="utf-8")
                poster = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                self.assertEqual(poster.outbox_status()["loss_ledger_unreadable"], 1)
                asides = list(Path(temp_dir).glob("alerts.losses.json.unreadable-*"))
                self.assertEqual(len(asides), 1)
                self.assertEqual(asides[0].read_text(encoding="utf-8"), "{not json")  # unmodified
                # Still a fault after more restarts, with no ledger file left in place.
                for _ in range(2):
                    restarted = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                    self.assertEqual(restarted.outbox_status()["loss_ledger_unreadable"], 1)
                # Acknowledged by moving the evidence out of the state directory.
                reviewed = Path(temp_dir) / "reviewed"
                reviewed.mkdir()
                asides[0].rename(reviewed / asides[0].name)
                restarted = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                self.assertEqual(restarted.outbox_status()["loss_ledger_unreadable"], 0)
            finally:
                restore_modules(previous)

    def test_operator_acknowledgment_is_picked_up_without_a_restart(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                state = Path(temp_dir)
                module.MAX_QUARANTINED_ALERTS = 1
                module.HARD_MAX_PENDING_ALERTS = 1
                poster = self.make_poster(module, state / "alerts.jsonl")
                poster.session = self.StatusSession([422] * 2)
                poster.publish("crit1", 0.9, "vosk")
                poster.publish("crit2", 0.9, "vosk")
                status = poster.outbox_status()
                self.assertEqual(status["quarantined_possibly_critical"], 1)
                self.assertEqual(status["quarantine_critical_evictions"], 1)
                # KWS's own writes never count as an acknowledgment.
                poster.reload_reviewed_state()
                self.assertEqual(poster.outbox_status()["quarantine_critical_evictions"], 1)
                (state / "reviewed").mkdir()
                for name in ("alerts.losses.json", "alerts.rejected.jsonl"):
                    (state / name).rename(state / "reviewed" / name)
                poster.reload_reviewed_state()
                status = poster.outbox_status()
                self.assertEqual(status["quarantined_possibly_critical"], 0)
                self.assertEqual(status["quarantine_critical_evictions"], 0)
                # outbox_status itself notices within REVIEW_CHECK_SECONDS.
                (state / "alerts.losses.json").write_text("{bad", encoding="utf-8")
                poster._next_review_check = 0
                self.assertEqual(poster.outbox_status()["loss_ledger_unreadable"], 1)
            finally:
                restore_modules(previous)

    def test_hard_byte_limit_evicts_lowest_tier_first(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                poster = self.bounded_poster(module, temp_dir, soft=100, hard=100, hard_bytes=1)
                poster.publish("crit", 0.95, "vosk")
                self.assertEqual(poster.pending, [])  # one event already exceeds 1 byte
                self.assertEqual(poster.outbox_status()["critical_evictions"], 1)

                module.HARD_MAX_PENDING_BYTES = 10**6
                poster.publish("crit", 0.95, "vosk")
                one_event = len(json.dumps(poster.pending[0])) + 1
                module.HARD_MAX_PENDING_BYTES = 2 * one_event + 10  # room for two events
                poster.publish("low", 0.1, "vosk")
                poster.publish("poss", 0.5, "vosk")
                self.assertEqual([e["keyword"] for e in poster.pending], ["crit", "poss"])
                self.assertEqual(poster.outbox_status()["critical_evictions"], 1)
            finally:
                restore_modules(previous)

    def test_legacy_outbox_is_merged_deduplicated_and_renamed_not_deleted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                queue_path = Path(temp_dir) / "state" / "alerts.jsonl"
                queue_path.parent.mkdir()
                legacy_path = Path(temp_dir) / "project_pi_alerts.jsonl"
                queue_path.write_text(json.dumps(
                    {"event_id": "shared", "keyword": "outbox-copy", "confidence": 0.9}) + "\n",
                    encoding="utf-8")
                legacy_path.write_text("".join(json.dumps(e) + "\n" for e in [
                    {"event_id": "shared", "keyword": "legacy-copy", "confidence": 0.9},
                    {"event_id": "legacy-1", "keyword": "tulong", "confidence": 0.5},
                    {"event_id": "legacy-1", "keyword": "tulong-dup", "confidence": 0.5},
                    {"keyword": "no-id", "confidence": 0.2},
                ]) + "not json\n", encoding="utf-8")
                traces = []
                module.trace_alert = lambda *args, **kwargs: traces.append((args, kwargs))

                poster = module.AlertPoster("http://backend/api/alerts", queue_path,
                                            legacy_queue_path=legacy_path)

                self.assertEqual([e["keyword"] for e in poster.pending],
                                 ["outbox-copy", "tulong", "no-id"])
                self.assertEqual([e["retention_tier"] for e in poster.pending], [3, 2, 1])
                self.assertFalse(legacy_path.exists())
                migrated = Path(f"{legacy_path}.migrated")
                self.assertIn("legacy-copy", migrated.read_text(encoding="utf-8"))
                persisted = [json.loads(line)["keyword"] for line in
                             queue_path.read_text(encoding="utf-8").splitlines()]
                self.assertEqual(persisted, ["outbox-copy", "tulong", "no-id"])
                self.assertEqual(
                    sum(1 for args, _ in traces if args[0] == "outbox" and args[2] == "migrated"), 2)

                # A second start finds nothing new to migrate and changes nothing.
                again = module.AlertPoster("http://backend/api/alerts", queue_path,
                                           legacy_queue_path=legacy_path)
                self.assertEqual([e["event_id"] for e in again.pending],
                                 [e["event_id"] for e in poster.pending])
            finally:
                restore_modules(previous)

    def test_retention_tier_is_not_sent_to_backend(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                poster = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                poster.publish("help", 0.9, "openwakeword")
                self.assertEqual(poster.pending[0]["retention_tier"], 3)
                self.assertNotIn("retention_tier", poster.session.posts[0])
            finally:
                restore_modules(previous)

    def test_worker_publish_does_not_wait_for_slow_network_post(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            module, previous = load_kws_module()
            try:
                poster = self.make_poster(module, Path(temp_dir) / "alerts.jsonl")
                started = threading.Event()
                release = threading.Event()

                class SlowSession(FakeSession):
                    def post(self, url, json, timeout):
                        started.set()
                        release.wait(timeout=2.0)
                        return super().post(url, json, timeout)

                poster.session = SlowSession()
                poster.start_worker()
                poster.publish("help", 0.9, "openwakeword")
                self.assertTrue(started.wait(timeout=1.0))

                start = time.perf_counter()
                poster.publish("tulong", 0.91, "openwakeword")
                elapsed = time.perf_counter() - start

                self.assertLess(elapsed, 0.1)
                release.set()
                poster.stop_worker()
            finally:
                restore_modules(previous)


if __name__ == "__main__":
    unittest.main()
