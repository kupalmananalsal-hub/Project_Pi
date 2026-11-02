"""C1.44 synthetic design experiments; no live backend import or real engine.

Real AlertDecisionEngine, AST-extracted AlertStore and fingerprint function are
used where stated. EpisodeReviewModel is a TEST-ONLY executable proposal, not a
completed implementation. All episode boundaries/voice association are fixtures.
"""
import ast
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from typing import Any

from test.test_alert_delivery import Conflict, store_class
from test.test_kws_event_id import load_kws_module, restore_modules
from test.episode_review_support import EpisodeReviewModel

ROOT = Path(__file__).resolve().parents[1]
from alert_decision import AlertDecisionEngine, AlertPolicy
from alert_delivery import replay_eligible

POLICY = AlertPolicy(repeat_escalates_to_critical=False)


def thermal(state, **extra):
    return {"thermal_state": state, "human_detected": state == "positive",
            "frame_valid": True, "frame_age_seconds": 0.0, **extra}


def voice(score=.4, keyword="sunog", source="openwakeword"):
    return {"keyword": keyword, "source": source, "confidence": score,
            "timestamp": "2026-11-02T00:00:00+00:00", "snr_db": 25.0}


def classify(event, evidence):
    # Fresh evaluator isolates this test model from bookkeeping side effects;
    # it is NOT an instruction to reset the live decision engine on each frame.
    return AlertDecisionEngine(policy=POLICY).evaluate(event, evidence)


def fingerprint_function():
    path = ROOT / "raspberry_pi/backend/main.py"
    node = next(n for n in ast.parse(path.read_text()).body
                if isinstance(n, ast.FunctionDef) and n.name == "alert_event_fingerprint")
    ns = {"json": json, "Any": Any}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
    return ns["alert_event_fingerprint"]


class EpisodeDesignReviewTest(unittest.TestCase):
    def setUp(self):
        self.outputs = []
        self.model = EpisodeReviewModel(classify, self.outputs.append)

    def test_identical_voice_then_positive_thermal_must_emit_critical(self):
        first = self.model.observe("one", voice(), thermal("negative"))
        escalated = self.model.thermal("one", thermal("positive"), association_valid=True)
        self.assertEqual(first["decision_state"], "advisory")
        self.assertEqual(escalated["decision_state"], "critical")
        self.assertEqual(escalated["decision_reason"], "voice_confirmed_by_thermal")
        self.assertEqual(first["confidence"], escalated["confidence"])
        self.assertEqual(first["episode_id"], escalated["episode_id"])
        self.assertNotEqual(first["event_id"], escalated["event_id"])

    def test_repeated_positive_thermal_does_not_create_more_critical_events(self):
        self.model.observe("one", voice(), thermal("negative"))
        for _ in range(12):
            self.model.thermal("one", thermal("positive"), association_valid=True)
        self.assertEqual([e["decision_state"] for e in self.outputs], ["advisory", "critical"])

    def test_continuous_scores_are_evaluated_but_do_not_duplicate_notice(self):
        evaluated = []
        def counting(event, evidence):
            evaluated.append(event["confidence"])
            return classify(event, evidence)
        model = EpisodeReviewModel(counting, self.outputs.append)
        for score in (.4, .5, .4, .6):
            model.observe("one", voice(score), thermal("negative"))
        self.assertEqual(evaluated, [.4, .5, .4, .6])
        self.assertEqual(len(self.outputs), 1)

    def test_critical_confidence_upgrade_is_immediate_without_release(self):
        self.model.observe("one", voice(.4), thermal("negative"))
        event = self.model.observe("one", voice(.85), thermal("negative"))
        self.assertEqual(event["decision_state"], "critical")
        self.assertEqual(event["decision_reason"], "voice_high_confidence")
        self.model.observe("one", voice(.95), thermal("positive"))
        self.assertEqual(len(self.outputs), 2)

    def test_positive_thermal_without_voice_never_creates_distress(self):
        self.assertIsNone(self.model.thermal("none", thermal("positive"), association_valid=True))
        self.assertEqual(self.outputs, [])

    def test_stale_invalid_unavailable_thermal_does_not_escalate(self):
        self.model.observe("one", voice(), thermal("negative"))
        for evidence in (thermal("positive", frame_age_seconds=POLICY.thermal_freshness_seconds+1),
                         thermal("positive", frame_valid=False), thermal("unavailable")):
            self.assertIsNone(self.model.thermal("one", evidence, association_valid=True))
        self.assertEqual(len(self.outputs), 1)
        self.assertEqual(self.model.thermal("one", thermal("positive"),
                         association_valid=True)["decision_state"], "critical")

    def test_expired_voice_association_is_not_reused_for_later_thermal(self):
        self.model.observe("one", voice(), thermal("negative"))
        self.assertIsNone(self.model.thermal("one", thermal("positive"), association_valid=False))
        self.assertEqual(len(self.outputs), 1)

    def test_missing_scores_do_not_release_or_erase_valid_voice_evidence(self):
        self.model.observe("one", voice(), thermal("negative"))
        for score in (None, float("nan"), -1, 1.1):
            self.model.observe("one", voice(score), thermal("negative"))
        self.assertNotIn("one", self.model.closed)
        self.assertEqual(self.model.thermal("one", thermal("positive"),
                         association_valid=True)["decision_state"], "critical")

    def test_engine_failure_does_not_block_escalation_of_still_valid_voice(self):
        self.model.observe("one", voice(), thermal("negative"))
        self.model.observe("one", None, thermal("negative"), available=False)
        self.assertIn("one", self.model.unknown)
        self.assertEqual(self.model.thermal("one", thermal("positive"),
                         association_valid=True)["decision_state"], "critical")

    def test_engine_failure_without_valid_voice_does_not_fabricate_critical(self):
        self.model.observe("none", None, thermal("positive"), available=False)
        self.assertIsNone(self.model.thermal("none", thermal("positive"), association_valid=True))
        self.assertEqual(self.outputs, [])

    def test_verified_release_allows_a_new_distress_episode(self):
        self.model.observe("one", voice(.9), thermal("negative"))
        self.model.release("one", verified=True)
        self.assertIsNone(self.model.thermal("one", thermal("positive"), association_valid=True))
        second = self.model.observe("two", voice(.9), thermal("negative"))
        self.assertEqual(second["decision_state"], "critical")
        self.assertNotEqual(self.outputs[0]["event_id"], second["event_id"])

    def test_insufficient_release_evidence_does_not_close_episode(self):
        self.model.observe("one", voice(), thermal("negative"))
        self.model.release("one", verified=False)
        self.assertEqual(self.model.thermal("one", thermal("positive"),
                         association_valid=True)["decision_state"], "critical")

    def test_distinct_overlapping_keywords_remain_independent(self):
        self.model.observe("fire", voice(.9, "sunog"), thermal("negative"))
        self.model.observe("rescue", voice(.9, "saklolo"), thermal("negative"))
        self.assertEqual([e["keyword"] for e in self.outputs], ["sunog", "saklolo"])
        with self.assertRaises(ValueError):
            self.model.observe("fire", voice(.9, "saklolo"), thermal("negative"))

    def test_thermal_flapping_after_critical_does_not_issue_another_alarm(self):
        self.model.observe("one", voice(), thermal("positive"))
        for state in ("negative", "positive", "unavailable", "positive"):
            self.model.thermal("one", thermal(state), association_valid=True)
        self.assertEqual(len(self.outputs), 1)

    def test_publication_failure_retries_same_frozen_event_and_id(self):
        attempts = []
        def unavailable(event):
            attempts.append(deepcopy(event))
            raise RuntimeError("synthetic ambiguous commit failure")
        self.model.observe("one", voice(), thermal("negative"))
        self.model.publish = unavailable
        with self.assertRaises(RuntimeError):
            self.model.thermal("one", thermal("positive"), association_valid=True)
        self.assertNotIn(("one", "critical"), self.model.sent)
        self.model.publish = self.outputs.append
        retried = self.model.retry_pending()[0]
        self.assertEqual(retried, attempts[0])
        self.assertEqual(len(self.outputs), 2)

    def test_current_evaluator_polling_can_inflate_repeat_history(self):
        engine = AlertDecisionEngine(policy=AlertPolicy(repeat_escalates_to_critical=True))
        event = voice(.75)
        self.assertEqual(engine.evaluate(event, thermal("negative"))["decision_state"], "advisory")
        result = engine.evaluate(event, thermal("negative"))
        self.assertEqual(result["decision_reason"], "repeated_distress_escalation")
        self.assertEqual(result["decision_factors"]["repeat_count"], 2)

    def test_real_store_retains_advisory_and_critical_as_distinct_immutable_events(self):
        fingerprint = fingerprint_function()
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            Store = store_class()
            store = Store(Path(tmp) / "synthetic.db")
            def persist(event):
                store.insert({**event, "_request_fingerprint": fingerprint(event)})
            model = EpisodeReviewModel(classify, persist)
            notice = model.observe("one", voice(), thermal("negative"))
            critical = model.thermal("one", thermal("positive"), association_valid=True)
            for _ in range(3):
                model.thermal("one", thermal("positive"), association_valid=True)
            store.insert({**critical, "_request_fingerprint": fingerprint(critical)})
            restarted = Store(Path(tmp) / "synthetic.db")
            rows = restarted.replay(0, 2)
            self.assertEqual([r["decision_state"] for r in rows], ["advisory", "critical"])
            self.assertEqual(restarted.lookup(notice["event_id"], fingerprint(notice))["decision_state"], "advisory")
            with self.assertRaises(Conflict):
                store.insert({**critical, "event_id": notice["event_id"],
                              "_request_fingerprint": fingerprint(critical)})
            now = datetime.now(timezone.utc)
            self.assertTrue(replay_eligible(rows[1], {}, now))
            self.assertFalse(replay_eligible(rows[1], {"user_confirmed_at": "fixture-confirmed"}, now))
            # Acknowledging the notice must not confirm its later critical event.
            store.offer("synthetic-phone", notice["event_id"])
            store.acknowledge("synthetic-phone", notice["event_id"], rows[0]["sequence"], "ack_user_confirmed")
            critical_delivery = store.offer("synthetic-phone", critical["event_id"])
            self.assertIsNone(critical_delivery["user_confirmed_at"])
            self.assertTrue(replay_eligible(rows[1], critical_delivery, now))
            self.assertEqual(store.recovery_cursor("synthetic-phone", 2, now), 1)
            store.acknowledge("synthetic-phone", critical["event_id"], rows[1]["sequence"], "ack_user_confirmed")
            self.assertEqual(store.recovery_cursor("synthetic-phone", 2, now), 2)


class RecognitionMechanismRegressionTest(unittest.TestCase):
    def setUp(self):
        self.kws, previous = load_kws_module()
        self.addCleanup(restore_modules, previous)

    def test_non_alias_words_are_rejected_but_masakit_is_preserved(self):
        words = ("tulog", "tuloy", "tulo", "araw", "aral", "aga", "agad", "sunod", "sundo")
        self.assertEqual({w:self.kws.detect_tagalog_keyword(w) for w in words},
                         {w:None for w in words})
        self.assertEqual(self.kws.detect_tagalog_keyword("masakit"), "ang sakit")

    def test_partial_prefix_is_not_promoted_to_a_keyword(self):
        self.assertIsNone(self.kws.detect_tagalog_keyword("tul"))
        self.assertIsNone(self.kws.detect_tagalog_keyword("tu"))
        self.assertEqual(self.kws.detect_tagalog_keyword("tulong"), "tulong")

    def dispatcher(self):
        class Poster:
            def __init__(self): self.events = []
            def publish(self, keyword, confidence, source, **kwargs):
                self.events.append((keyword, source))
        poster = Poster()
        return self.kws.DetectionDispatcher(poster, self.kws.CooldownGate(2), .05, .3), poster

    def test_non_tulong_hint_preserves_pending_snowboy_timer(self):
        # C1.45: a manual timer proves unrelated hints cannot cancel help.
        class Timer:
            def __init__(self, seconds, callback): self.cancelled = False
            def start(self): pass
            def cancel(self): self.cancelled = True
        with patch.object(self.kws.threading, "Timer", Timer), patch.object(self.kws.time, "monotonic", return_value=1000):
            dispatcher, poster = self.dispatcher()
            dispatcher.submit("help", .75, "snowboy")
            timer = dispatcher.pending_help_timer
            self.assertIsNone(self.kws.detect_tagalog_keyword("araw"))
            dispatcher.note_vosk_text("araw")
            dispatcher.note_vosk_text("aray")
            self.assertFalse(timer.cancelled)
            self.assertIsNotNone(dispatcher.pending_help_payload)
            self.assertEqual(poster.events, [])

    def test_false_vosk_hint_does_not_block_openwakeword_help(self):
        with patch.object(self.kws.time, "monotonic", return_value=1000):
            dispatcher, poster = self.dispatcher()
            dispatcher.note_vosk_text("tulog")
            self.assertEqual(dispatcher.last_tulong_at, 0)
            self.assertEqual(dispatcher.last_tulong_hint_at, 0)
            dispatcher.submit("help", .6, "openwakeword")
            self.assertEqual(poster.events, [("help", "openwakeword")])


if __name__ == "__main__":
    unittest.main()
