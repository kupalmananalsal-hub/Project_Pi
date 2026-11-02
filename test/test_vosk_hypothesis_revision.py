"""C1.46 synthetic hypothesis lifecycle experiments; no engines or audio.

The initial read-result tests can fall back to the real C1.45 flattening helper
before the test-only reference module exists, reproducing metadata loss as RED.
"""
import contextlib
from copy import deepcopy
import io
import json
import queue
import types
import unittest
from unittest.mock import patch

from test.test_kws_event_id import load_kws_module, restore_modules
from test.test_recognition_defect_remediation import ManualTimer, Recorder
from test.test_kws_live_paths import Samples
from test.episode_review_support import EpisodeReviewModel
from test.test_episode_rearming_review import classify, thermal

try:
    from test import vosk_hypothesis_reference as reference
except ImportError as exc:
    if "vosk_hypothesis_reference" not in str(exc):
        raise
    reference = None


class ResultRecognizer:
    def __init__(self, final, payload):
        self.final = final
        self.raw = json.dumps(payload)
        self.calls = []
    def AcceptWaveform(self, data):
        self.calls.append("AcceptWaveform")
        return self.final
    def Result(self):
        self.calls.append("Result")
        return self.raw
    def PartialResult(self):
        self.calls.append("PartialResult")
        return self.raw


class StructuredResultTest(unittest.TestCase):
    def setUp(self):
        self.kws, previous = load_kws_module()
        self.addCleanup(restore_modules, previous)

    def read(self, recognizer):
        if reference is None:
            return self.kws.read_vosk_text(recognizer, b"synthetic-frame")
        return reference.read_hypothesis_result(recognizer, b"synthetic-frame")

    def test_partial_result_preserves_kind_and_entire_original_payload(self):
        payload = {"partial":"Tulong", "partial_result":[{"word":"Tulong", "start":1.0,
                   "end":1.1, "conf":.6}], "fixture_extra":{"keep":[1,2]}}
        recognizer = ResultRecognizer(False, payload)
        self.assertEqual(self.read(recognizer), {"kind":"partial", "text":"tulong",
                         "payload":payload, "raw_json":recognizer.raw})
        self.assertEqual(recognizer.calls, ["AcceptWaveform", "PartialResult"])

    def test_final_result_preserves_kind_and_entire_original_payload(self):
        payload = {"text":"Tulog", "result":[{"word":"Tulog", "conf":.7}]}
        recognizer = ResultRecognizer(True, payload)
        self.assertEqual(self.read(recognizer), {"kind":"final", "text":"tulog",
                         "payload":payload, "raw_json":recognizer.raw})
        self.assertEqual(recognizer.calls, ["AcceptWaveform", "Result"])

    def test_identical_text_partial_and_final_are_distinguishable(self):
        partial = self.read(ResultRecognizer(False, {"partial":"tulong"}))
        final = self.read(ResultRecognizer(True, {"text":"tulong"}))
        self.assertNotEqual(partial, final)


def observation(sequence, kind="partial", text="tulong", *, session="s1", utterance="u1"):
    if kind in {"partial", "final"}:
        field = "text" if kind == "final" else "partial"
        payload = {field:text, "fixture_words":[{"word":text, "score":.6}]}
        result = {"kind":kind, "text":text.lower().strip(), "payload":payload,
                  "raw_json":json.dumps(payload)}
    else:
        result = {"kind":kind, "text":"", "payload":{"reason":"synthetic-"+kind}}
    return {"observation_id":f"{session}:{sequence}", "session":session,
            "utterance":utterance, "sequence":sequence, "result":result,
            "context":{"confidence":.4, "snr_db":25.0, "capture_sequence":sequence,
                       "fixture_extra":{"untouched":[1,2]}}}


class HypothesisReferenceTest(unittest.TestCase):
    def setUp(self):
        self.kws, previous = load_kws_module()
        self.addCleanup(restore_modules, previous)
        model = getattr(reference, "HypothesisReference", None)
        self.assertIsNotNone(model, "test-only revision tracker not implemented yet")
        self.model = model(self.kws.detect_tagalog_keyword)
        self.key = ("s1", "u1")

    def test_partial_tulong_then_final_tulog_revises_candidate_without_erasing_evidence(self):
        first = observation(1)
        self.model.ingest(first)
        original_candidate = self.model.latest(self.key)["candidate_id"]
        self.assertTrue(self.model.for_classification(self.key, association_valid=True)["provisional"])
        self.model.ingest(observation(2, "final", "tulog"))
        self.assertIsNone(self.model.for_classification(self.key, association_valid=True))
        self.assertEqual(self.model.latest(self.key)["status"], "final")
        self.assertEqual(self.model.latest(self.key)["candidate_id"], original_candidate)
        self.assertEqual(self.model.journal()[0], first)

    def test_partial_tul_then_final_tulong_preserves_final_distress(self):
        self.model.ingest(observation(1, text="tul"))
        self.assertIsNone(self.model.for_classification(self.key, association_valid=True))
        self.model.ingest(observation(2, "final", "tulong"))
        candidate = self.model.for_classification(self.key, association_valid=True)
        self.assertEqual(candidate["keyword"], "tulong")
        self.assertFalse(candidate["provisional"])

    def test_genuine_final_tulong_is_immediately_available(self):
        self.model.ingest(observation(1, "final"))
        self.assertEqual(self.model.for_classification(self.key, association_valid=True)["keyword"], "tulong")

    def test_partial_distress_without_final_is_not_discarded(self):
        self.model.ingest(observation(1))
        candidate = self.model.for_classification(self.key, association_valid=True)
        self.assertEqual(candidate["keyword"], "tulong")
        self.assertTrue(candidate["provisional"])
        self.assertEqual(candidate["observation"], observation(1))

    def test_multiple_revisions_keep_one_candidate_identity_and_all_observations(self):
        ids = []
        for seq, text in enumerate(("tul", "tulong", "tulog", "tulong"), 1):
            self.model.ingest(observation(seq, text=text))
            ids.append(self.model.latest(self.key)["candidate_id"])
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(len(self.model.journal()), 4)
        self.assertEqual(self.model.for_classification(self.key, association_valid=True)["keyword"], "tulong")

    def test_identical_partial_updates_are_observations_not_new_emergency_ids(self):
        ids = []
        for seq in range(1, 9):
            self.model.ingest(observation(seq))
            ids.append(self.model.latest(self.key)["candidate_id"])
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(len(self.model.journal()), 8)
        self.assertTrue(all("event_id" not in record for record in self.model.journal()))

    def test_same_observation_retry_is_idempotent_and_conflicting_id_is_rejected(self):
        first = observation(1)
        self.model.ingest(first)
        self.model.ingest(deepcopy(first))
        self.assertEqual(len(self.model.journal()), 1)
        changed = deepcopy(first); changed["context"]["confidence"] = .9
        with self.assertRaises(ValueError): self.model.ingest(changed)
        self.assertEqual(self.model.journal(), [first])

    def test_old_retry_does_not_rewind_final_revision(self):
        first = observation(1)
        self.model.ingest(first)
        self.model.ingest(observation(2, "final", "tulog"))
        self.model.ingest(first)
        self.assertIsNone(self.model.for_classification(self.key, association_valid=True))
        self.assertEqual(self.model.latest(self.key)["status"], "final")

    def test_mutating_inputs_or_exports_does_not_change_original_observation(self):
        first = observation(1); expected = deepcopy(first)
        self.model.ingest(first)
        first["result"]["payload"]["partial"] = "tulog"
        first["context"]["fixture_extra"]["untouched"].append(3)
        exported = self.model.journal(); exported[0]["context"]["confidence"] = .99
        candidate = self.model.for_classification(self.key, association_valid=True)
        candidate["observation"]["context"]["confidence"] = .99
        self.assertEqual(self.model.journal(), [expected])

    def test_silence_gap_and_failure_are_not_fabricated_final_results(self):
        for kind in ("silence", "gap", "failure"):
            with self.subTest(kind=kind):
                model = reference.HypothesisReference(self.kws.detect_tagalog_keyword)
                model.ingest(observation(1))
                model.ingest(observation(2, kind))
                candidate = model.for_classification(self.key, association_valid=True)
                self.assertTrue(candidate["provisional"])
                self.assertNotEqual(model.latest(self.key)["status"], "final")
                self.assertEqual(model.journal()[0], observation(1))
                self.assertIsNone(model.for_classification(self.key, association_valid=False))

    def test_missing_sequence_marks_continuity_unknown_without_confirming(self):
        self.model.ingest(observation(1))
        self.model.ingest(observation(3))
        self.assertFalse(self.model.latest(self.key)["continuous"])
        self.assertTrue(self.model.for_classification(self.key, association_valid=True)["provisional"])

    def test_repeated_genuine_finals_use_distinct_utterance_identities(self):
        self.model.ingest(observation(1, "final"))
        self.model.ingest(observation(2, "final", utterance="u2"))
        first = self.model.for_classification(self.key, association_valid=True)
        second = self.model.for_classification(("s1", "u2"), association_valid=True)
        self.assertNotEqual(first["candidate_id"], second["candidate_id"])
        self.assertEqual(first["keyword"], second["keyword"])

    def test_new_hypothesis_cannot_reopen_a_finalized_utterance(self):
        self.model.ingest(observation(1, "final"))
        with self.assertRaises(ValueError): self.model.ingest(observation(2))
        self.assertEqual(len(self.model.journal()), 1)

    def test_engine_restart_requires_new_session_identity(self):
        self.model.ingest(observation(1))
        self.model.ingest(observation(2, "failure"))
        with self.assertRaises(ValueError): self.model.ingest(observation(3))
        self.model.ingest(observation(1, "final", session="s2"))
        self.assertEqual(self.model.for_classification(("s2", "u1"), association_valid=True)["keyword"], "tulong")

    def test_session_failure_marks_all_retained_utterances_unhealthy(self):
        self.model.ingest(observation(1, "final"))
        self.model.ingest(observation(2, utterance="u2"))
        self.model.ingest(observation(3, "failure", utterance="u2"))
        for key in (self.key, ("s1", "u2")):
            self.assertEqual(self.model.latest(key)["health"], "failed")
            self.assertEqual(self.model.for_classification(key, association_valid=True)["health"], "failed")
        self.assertEqual(self.model.latest(self.key)["status"], "final")

    def test_controls_after_final_do_not_reopen_or_unfinalize_segment(self):
        self.model.ingest(observation(1, "final"))
        try:
            self.model.ingest(observation(2, "gap"))
            self.model.ingest(observation(3, "failure"))
        except ValueError as error:
            self.fail("engine health controls must remain reportable after final: " + str(error))
        self.assertEqual(self.model.latest(self.key)["status"], "final")
        self.assertEqual(self.model.latest(self.key)["health"], "failed")
        with self.assertRaises(ValueError): self.model.ingest(observation(4))
        self.assertEqual(len(self.model.journal()), 3)

    def test_session_gap_marks_retained_candidates_continuity_uncertain(self):
        self.model.ingest(observation(1))
        self.model.ingest(observation(3, utterance="u2"))
        self.assertFalse(self.model.latest(self.key)["continuous"])
        self.assertFalse(self.model.for_classification(self.key, association_valid=True)["continuous"])
        self.assertFalse(self.model.latest(("s1", "u2"))["continuous"])

    def test_unavailable_engine_without_previous_voice_creates_no_distress_candidate(self):
        self.model.ingest(observation(1, "failure"))
        self.assertIsNone(self.model.for_classification(self.key, association_valid=True))

    def test_thermal_reevaluation_is_available_for_identical_partial_voice(self):
        self.model.ingest(observation(1))
        candidate = self.model.for_classification(self.key, association_valid=True)
        voice = {"keyword":candidate["keyword"], "source":"vosk",
                 **candidate["observation"]["context"]}
        self.assertEqual(classify(voice, thermal("negative"))["decision_state"], "advisory")
        self.assertEqual(classify(voice, thermal("positive"))["decision_state"], "critical")
        # This is available evidence, NOT authority to convert a partial into an alarm.
        self.assertTrue(candidate["provisional"])

    def test_thermal_assessment_cannot_resurrect_a_revised_away_keyword(self):
        self.model.ingest(observation(1))
        self.model.ingest(observation(2, "final", "tulog"))
        self.assertIsNone(self.model.for_classification(self.key, association_valid=True))

    def test_downstream_dedup_does_not_need_multiple_emergency_ids_for_partial_updates(self):
        outputs = []
        downstream = EpisodeReviewModel(classify, outputs.append)
        for seq in range(1, 5):
            self.model.ingest(observation(seq))
            candidate = self.model.for_classification(self.key, association_valid=True)
            downstream.observe(candidate["candidate_id"], {"keyword":candidate["keyword"],
                "source":"vosk", **candidate["observation"]["context"]}, thermal("negative"))
        candidate = self.model.for_classification(self.key, association_valid=True)
        downstream.thermal(candidate["candidate_id"], thermal("positive"), association_valid=True)
        downstream.thermal(candidate["candidate_id"], thermal("positive"), association_valid=True)
        self.assertEqual([e["decision_state"] for e in outputs], ["advisory", "critical"])
        self.assertNotEqual(outputs[0]["event_id"], outputs[1]["event_id"])
        self.assertTrue(candidate["provisional"])  # Permissive scenario, not a safe authority rule.

    def test_empty_final_closes_segment_without_inventing_a_keyword(self):
        self.model.ingest(observation(1))
        self.model.ingest(observation(2, "final", ""))
        self.assertEqual(self.model.latest(self.key)["status"], "final")
        self.assertIsNone(self.model.for_classification(self.key, association_valid=True))

    def test_invalid_or_out_of_order_observation_cannot_corrupt_saved_state(self):
        self.model.ingest(observation(2))
        for record in (observation(1), {**observation(3), "sequence":True},
                       {**observation(3), "session":""}):
            with self.subTest(record=record):
                with self.assertRaises(ValueError): self.model.ingest(record)
        self.assertEqual(self.model.journal(), [observation(2)])


class CurrentLifecycleCounterexampleTest(unittest.TestCase):
    def setUp(self):
        self.kws, previous = load_kws_module()
        self.addCleanup(restore_modules, previous)
        self.kws.np = types.SimpleNamespace(int16=int,
            asarray=lambda values, dtype=None: Samples(values))
        self.now = 1000.0
        clock = patch.object(self.kws.time, "monotonic", side_effect=lambda: self.now)
        clock.start(); self.addCleanup(clock.stop)
        timer = patch.object(self.kws.threading, "Timer", ManualTimer)
        timer.start(); self.addCleanup(timer.stop)

    def dispatcher(self):
        poster = Recorder()
        return self.kws.DetectionDispatcher(poster, self.kws.CooldownGate(2), 1.2, 2.2), poster

    def run_worker(self, steps, *, discard_on_reset=False):
        """steps are (clock, is_final, text); no audio/model or timer thread."""
        module = self.kws
        outer = self
        class Recognizer:
            def __init__(self):
                self.index = 0; self.current = None; self.resets = 0; self.reads = []
            def AcceptWaveform(self, data):
                self.current = steps[self.index]; self.index += 1
                outer.now = self.current[0]
                return self.current[1]
            def Result(self):
                self.reads.append("final")
                return json.dumps({"text":self.current[2]})
            def PartialResult(self):
                self.reads.append("partial")
                return json.dumps({"partial":self.current[2]})
            def Reset(self):
                self.resets += 1
                if discard_on_reset: self.index = len(steps)
        recognizer = Recognizer()
        class Packets:
            def get(inner, timeout):
                if recognizer.index >= len(steps):
                    module.RUNNING = False; raise queue.Empty
                return {"mono_samples":[0]*4, "mono_bytes":b"\0"*8}
        dispatcher, poster = self.dispatcher()
        config = {"sample_rate":16000,"debug":False,"confidence":.75,
                  "wav2vec2_verify_below_confidence":0.0,
                  "wav2vec2_context_seconds":1.0,"model_path":"stub"}
        module.RUNNING = True
        with contextlib.redirect_stdout(io.StringIO()):
            module.vosk_worker(Packets(),dispatcher,config,recognizer,None)
        return poster.events, recognizer

    def test_current_runtime_publishes_partial_before_later_scripted_revision(self):
        events, recognizer = self.run_worker([(1000,False,"tulong"),(1001,True,"tulog")])
        self.assertEqual(events, [("tulong",.75,"vosk")])
        self.assertEqual(recognizer.reads, ["partial","final"])
        self.assertEqual(recognizer.resets, 1)

    def test_reset_aware_fixture_discards_the_not_yet_delivered_revision(self):
        events, recognizer = self.run_worker([(1000,False,"tulong"),(1001,True,"tulog")], discard_on_reset=True)
        self.assertEqual(events, [("tulong",.75,"vosk")])
        self.assertEqual(recognizer.reads, ["partial"])

    def test_cooldown_rejection_still_resets_and_later_same_partial_can_republish(self):
        events, recognizer = self.run_worker([(1000,False,"tulong"),(1001,False,"tulong"),(1002,False,"tulong")])
        self.assertEqual(events, [("tulong",.75,"vosk")]*2)
        self.assertEqual(recognizer.resets, 3)

    def test_explicit_final_prefix_and_partial_only_current_behavior(self):
        for steps in ([(1000,False,"tul"),(1001,True,"tulong")],
                      [(1000,True,"tulong")],[(1000,False,"tulong")]):
            with self.subTest(steps=steps):
                events, _ = self.run_worker(steps)
                self.assertEqual(events, [("tulong",.75,"vosk")])

    def test_current_speech_gate_can_withhold_the_packet_that_would_endpoint_asr(self):
        seen = []
        recognizer = ResultRecognizer(True,{"text":"tulong"})
        allowed = self.kws.fallback_speech_active({"available":True,"is_speech":False}, [0]*4)
        if allowed: seen.append(self.kws.read_vosk_text(recognizer,b"synthetic-silence"))
        self.assertFalse(allowed)
        self.assertEqual(recognizer.calls, [])
        self.assertEqual(seen, [])

    def test_current_queue_overflow_discards_an_earlier_synthetic_packet(self):
        packets = queue.Queue(maxsize=1)
        self.kws.put_latest(packets,{"fixture_sequence":1})
        self.kws.put_latest(packets,{"fixture_sequence":2})
        self.assertEqual(packets.get_nowait(), {"fixture_sequence":2})

    def test_current_recognizer_failure_propagates_instead_of_manufacturing_final(self):
        recognizer = ResultRecognizer(False,{"partial":"tulong"})
        def unavailable(data): raise RuntimeError("synthetic engine failure")
        recognizer.AcceptWaveform = unavailable
        with self.assertRaises(RuntimeError): self.kws.read_vosk_text(recognizer,b"synthetic")
        self.assertEqual(recognizer.calls, [])

    def test_partial_tracking_does_not_cancel_snowboy_or_openwakeword_help(self):
        cls = getattr(reference,"HypothesisReference",None)
        self.assertIsNotNone(cls,"test-only revision tracker not implemented yet")
        tracker = cls(self.kws.detect_tagalog_keyword)
        dispatcher, poster = self.dispatcher()
        dispatcher.submit("help",.75,"snowboy"); pending = dispatcher.pending_help_timer
        tracker.ingest(observation(1))  # NEVER pass this unconfirmed text to note_vosk_text.
        self.assertFalse(pending.cancelled)
        pending.fire()
        self.assertEqual(poster.events, [("help",.75,"snowboy")])
        dispatcher, poster = self.dispatcher()
        tracker.ingest(observation(2,text="tulog"))
        dispatcher.submit("help",.9,"openwakeword")
        self.assertEqual(poster.events, [("help",.9,"openwakeword")])

    def test_simultaneous_independent_engine_detection_is_not_waiting_for_vosk_final(self):
        cls = getattr(reference,"HypothesisReference",None)
        self.assertIsNotNone(cls,"test-only revision tracker not implemented yet")
        tracker = cls(self.kws.detect_tagalog_keyword)
        tracker.ingest(observation(1))
        dispatcher, poster = self.dispatcher()
        dispatcher.submit("tulong",.9,"openwakeword")
        self.assertEqual(poster.events, [("tulong",.9,"openwakeword")])
        self.assertTrue(tracker.for_classification(("s1","u1"),association_valid=True)["provisional"])

    def test_indistinguishable_partial_prefix_cannot_prove_a_safe_publication_deadline(self):
        # Repetition counts here are counterexamples, NOT proposed confirmation thresholds.
        for repeats in (1,2,4,8):
            common = [(False,"tulong")]*repeats
            genuine_without_final = deepcopy(common)
            revised_later = deepcopy(common)+[(True,"tulog")]
            self.assertEqual(genuine_without_final, revised_later[:repeats])
            final_only_hits = [text for final,text in genuine_without_final
                               if final and self.kws.detect_tagalog_keyword(text)]
            self.assertEqual(final_only_hits, [])
            self.assertEqual(self.kws.detect_tagalog_keyword(common[-1][1]),"tulong")


if __name__ == "__main__":
    unittest.main()
