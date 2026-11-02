"""C1.50 counterexamples; C1.58 converts corrected fusion cases to acceptance tests.

All clocks, ASR packets, recognizers and classification inputs are synthetic.
Backend methods are AST-extracted without importing backend startup/hardware.
Only temporary synthetic SQLite stores are opened. No engine/model is created.
Numeric fixture values are NOT proposed timing, score or authority policies.
"""
import ast
import asyncio
from collections import OrderedDict
import contextlib
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import queue
import sys
import tempfile
import time
import types
from typing import Any, Callable
import unittest
from unittest.mock import patch
import uuid

from test.test_kws_event_id import load_kws_module, restore_modules
from test.test_kws_live_paths import Samples
from test.test_recognition_defect_remediation import ManualTimer, Recorder
from test.test_alert_delivery import Conflict, store_class
from test.test_episode_rearming_review import classify, thermal, voice
from test.test_alarm_authority_contract import evidence
from test.alarm_authority_contract_reference import AuthorityContractReference
from alert_decision import AlertDecisionEngine, AlertPolicy
from alert_delivery import replay_eligible

ROOT = Path(__file__).resolve().parents[1]


class RuntimeSafetyCounterexamples(unittest.TestCase):
    def setUp(self):
        self.kws, previous = load_kws_module()
        self.addCleanup(restore_modules, previous)
        self.addCleanup(setattr, self.kws, 'RUNNING', self.kws.RUNNING)
        self.now = 1000.0
        self.patches = [
            patch.object(self.kws.time, 'monotonic', side_effect=lambda: self.now),
            patch.object(self.kws.threading, 'Timer', ManualTimer),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.output = io.StringIO()
        capture = contextlib.redirect_stdout(self.output)
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)
        self.kws.np = types.SimpleNamespace(int16=int,
            asarray=lambda values, dtype=None: Samples(values))

    def dispatcher(self):
        poster = Recorder()
        dispatcher = self.kws.DetectionDispatcher(
            poster, self.kws.CooldownGate(2), 1.2, 2.2)
        return dispatcher, poster

    def run_worker(self, steps, dispatcher, before=None):
        outer = self

        class Recognizer:
            index = 0
            current = None
            resets = 0
            reads = None

            def AcceptWaveform(inner, data):
                inner.current = steps[inner.index]
                inner.index += 1
                if isinstance(inner.current[2], Exception):
                    raise inner.current[2]
                return inner.current[1]

            def Result(inner):
                inner.reads.append('final')
                return json.dumps({'text': inner.current[2]})

            def PartialResult(inner):
                inner.reads.append('partial')
                return json.dumps({'partial': inner.current[2]})

            def Reset(inner):
                inner.resets += 1

        recognizer = Recognizer()
        recognizer.reads = []

        class Packets:
            def get(inner, timeout):
                if recognizer.index == len(steps):
                    outer.kws.RUNNING = False
                    raise queue.Empty
                outer.now = steps[recognizer.index][0]
                if before:
                    before(recognizer.index)
                return {'mono_samples': [0]*4, 'mono_bytes': b'\0'*8}

        self.kws.RUNNING = True
        config = {'sample_rate': 16000, 'debug': False, 'confidence': .75,
                  'wav2vec2_verify_below_confidence': 0.0,
                  'wav2vec2_context_seconds': 1.0, 'model_path': 'synthetic'}
        self.kws.vosk_worker(Packets(), dispatcher, config, recognizer, None)
        return recognizer

    def test_exact_partial_revision_leaves_original_publication(self):
        dispatcher, poster = self.dispatcher()
        recognizer = self.run_worker(
            [(1000, False, 'tulong'), (1001, True, 'tulog')], dispatcher)
        self.assertEqual(recognizer.reads, ['partial', 'final'])
        self.assertEqual(recognizer.resets, 1)
        self.assertEqual(poster.events, [('tulong', .75, 'vosk')])

    def test_partial_only_and_later_revised_call_share_an_observed_prefix(self):
        dispatcher, poster = self.dispatcher()
        recognizer = self.run_worker([(1000, False, 'tulong')], dispatcher)
        self.assertEqual(recognizer.reads, ['partial'])
        self.assertEqual(poster.events, [('tulong', .75, 'vosk')])
        # A final-only rule would output nothing for this genuine-distress fixture.
        # The same first packet also occurs in the revised ordinary-speech fixture.
        self.assertEqual([(False, 'tulong')], [(False, 'tulong'), (True, 'tulog')][:1])

    def test_ordinary_speech_alone_preserves_both_independent_help_paths(self):
        for source in ('snowboy', 'openwakeword'):
            with self.subTest(source=source):
                self.now = 1000
                dispatcher, poster = self.dispatcher()
                dispatcher.submit('help', .9, source)
                recognizer = self.run_worker([(1000.1, True, 'tulog')], dispatcher)
                if dispatcher.pending_help_timer:
                    dispatcher.pending_help_timer.fire()
                self.assertEqual(recognizer.resets, 0)
                self.assertEqual(poster.events, [('help', .9, source)])

    def test_independent_help_before_between_and_after_vosk_revision(self):
        for source in ('snowboy', 'openwakeword'):
            for arrival in ('before', 'between', 'after'):
                with self.subTest(source=source, arrival=arrival):
                    self.now = 1000
                    dispatcher, poster = self.dispatcher()
                    if arrival == 'before':
                        dispatcher.submit('help', .9, source)

                    def inject(index):
                        if arrival == 'between' and index == 1:
                            dispatcher.submit('help', .9, source)

                    self.run_worker([(1000.1, False, 'tulong'),
                                     (1000.2, True, 'tulog')], dispatcher, inject)
                    if arrival == 'after':
                        self.now = 1000.3
                        dispatcher.submit('help', .9, source)
                    if dispatcher.pending_help_timer:
                        dispatcher.pending_help_timer.fire()
                    self.assertCountEqual(poster.events,
                        [('tulong', .75, 'vosk'), ('help', .9, source)])

    def test_hint_without_replacement_cannot_cancel_independent_help(self):
        for source in ('snowboy', 'openwakeword'):
            with self.subTest(source=source):
                dispatcher, poster = self.dispatcher()
                dispatcher.submit('help', .9, source)
                timer = dispatcher.pending_help_timer
                dispatcher.note_vosk_text('tulong')
                dispatcher.note_vosk_text('tulog')  # No undo of the previous hint.
                if timer:
                    timer.fire()
                    self.assertFalse(timer.cancelled)
                self.assertEqual(poster.events,
                    [('help', .9, source)])

    def test_rejected_tulong_does_not_refresh_veto(self):
        dispatcher, poster = self.dispatcher()
        dispatcher.submit('tulong', .75, 'vosk')
        self.now = 1001.9
        dispatcher.submit('tulong', .75, 'vosk')  # Rejected by 2-second fixture cooldown.
        self.now = 1002.3  # Outside first 2.2-second correlation; inside refreshed one.
        dispatcher.submit('help', .9, 'openwakeword')
        dispatcher.submit('help', .9, 'snowboy')
        self.assertIsNotNone(dispatcher.pending_help_timer)
        dispatcher.pending_help_timer.fire()
        self.assertEqual(poster.events, [('tulong', .75, 'vosk'), ('help', .9, 'openwakeword')])
        self.assertEqual(dispatcher.last_tulong_at, 1000)

    def test_engine_failure_after_partial_does_not_veto_independent_help(self):
        dispatcher, poster = self.dispatcher()
        with self.assertRaisesRegex(RuntimeError, 'synthetic engine failure'):
            self.run_worker([(1000, False, 'tulong'),
                             (1000.1, False, RuntimeError('synthetic engine failure'))],
                            dispatcher)
        dispatcher.submit('help', .9, 'openwakeword')
        self.assertEqual(poster.events, [('tulong', .75, 'vosk'), ('help', .9, 'openwakeword')])
        # Worker failure propagates; no claim that the supervising main loop keeps running.

    def test_sustained_scores_publish_again_without_release(self):
        dispatcher, poster = self.dispatcher()
        for at in (1000, 1001, 1002, 1004):
            self.now = at
            dispatcher.submit('sunog', .6, 'openwakeword')
        self.assertEqual(poster.events, [('sunog', .6, 'openwakeword')]*3)


def backend_namespace(path):
    """Real selected API/store/registry/enrichment functions; injected I/O only."""
    names = {'AlertIdempotencyRegistry', 'alert_to_dict', 'normalize_event_id',
             'alert_event_fingerprint', 'duplicate_response', 'first_not_none',
             'enrich_alert_payload', 'api_alerts'}
    tree = ast.parse((ROOT/'raspberry_pi/backend/main.py').read_text())
    nodes = [node for node in tree.body if getattr(node, 'name', None) in names]
    assert len(nodes) == len(names)
    for node in nodes:
        node.decorator_list = []  # No FastAPI app construction or route registration.
    ns = dict(asyncio=asyncio, Any=Any, Callable=Callable, OrderedDict=OrderedDict,
              time=time, sys=sys, json=json, uuid=uuid, AlertIn=object,
              HTTPException=Conflict, trace_alert=lambda *a, **kw: None)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'C1.50-backend-extract', 'exec'), ns)

    class ThermalFixture:
        state = 'negative'
        reads = 0
        def latest(self, max_age):
            self.reads += 1
            return thermal(self.state)

    class HubFixture:
        def __init__(self): self.events = []
        async def publish(self, event): self.events.append(deepcopy(event))

    ns.update(thermal=ThermalFixture(), alerts=HubFixture(),
              alert_store=store_class()(path),
              decision_engine=AlertDecisionEngine(policy=AlertPolicy(repeat_escalates_to_critical=False)),
              audio=types.SimpleNamespace(latest={}), read_shared_audio_status=lambda: {},
              thermal_evidence_for_decision=lambda payload, **kw: payload)
    ns['alert_idempotency'] = ns['AlertIdempotencyRegistry'](
        ttl_seconds=60, max_entries=32)
    return ns


class BackendSafetyCounterexamples(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='C1_50_synthetic_', dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'synthetic.db'
        self.ns = backend_namespace(self.path)

    def event(self, identity='c150-advisory'):
        return dict(voice(.4), event_id=identity,
                    timestamp=datetime.now(timezone.utc).isoformat())

    def test_positive_thermal_does_not_upgrade_retry_of_immutable_advisory(self):
        async def scenario():
            payload = self.event()
            event = types.SimpleNamespace(model_dump=lambda: dict(payload))
            first = await self.ns['api_alerts'](event)
            self.ns['thermal'].state = 'positive'
            self.assertEqual(self.ns['alert_store'].list_recent()[0]['decision_state'], 'advisory')
            duplicate = await self.ns['api_alerts'](event)
            self.assertTrue(duplicate['duplicate_event'])
            self.assertEqual(duplicate['event']['decision_state'], 'advisory')
            self.assertEqual(self.ns['thermal'].reads, 1)
            self.assertEqual(len(self.ns['alerts'].events), 1)
            # A genuinely NEW request can classify critical; retry is not that request.
            payload['event_id'] = 'c150-new-observation'
            critical = await self.ns['api_alerts'](event)
            self.assertEqual(critical['event']['decision_state'], 'critical')
            self.assertNotEqual(first['event']['event_id'], critical['event']['event_id'])
        asyncio.run(scenario())

    def test_reopen_and_replay_preserves_critical_after_advisory_confirmation(self):
        async def scenario():
            payload = self.event()
            event = types.SimpleNamespace(model_dump=lambda: dict(payload))
            first = (await self.ns['api_alerts'](event))['event']
            self.ns['thermal'].state = 'positive'
            payload['event_id'] = 'c150-critical'
            critical = (await self.ns['api_alerts'](event))['event']
            store = store_class()(self.path)  # Synthetic store reopened after disconnect.
            _, high = store.delivery_boundary()
            replayed = store.replay(0, high)
            self.assertEqual([e['event_id'] for e in replayed], [first['event_id'], critical['event_id']])
            self.assertEqual(len(store.list_recent()), 2)
            store.offer('synthetic-phone', first['event_id'])
            store.acknowledge('synthetic-phone', first['event_id'], first['sequence'], 'ack_user_confirmed')
            delivery = store.offer('synthetic-phone', critical['event_id'])
            self.assertTrue(replay_eligible(critical, delivery, datetime.now(timezone.utc)))
            changed = dict(payload, confidence=.5)
            with self.assertRaises(Conflict):
                await self.ns['api_alerts'](types.SimpleNamespace(model_dump=lambda: changed))
            self.assertEqual(store.replay(0, high), replayed)
        asyncio.run(scenario())

    def test_polling_same_voice_counts_as_more_speech(self):
        engine = AlertDecisionEngine(policy=AlertPolicy(repeat_escalates_to_critical=True))
        first = engine.evaluate(voice(.75), thermal('negative'))
        second = engine.evaluate(voice(.75), thermal('negative'))
        self.assertEqual(first['decision_state'], 'advisory')
        self.assertEqual(second['decision_reason'], 'repeated_distress_escalation')
        self.assertEqual(second['decision_factors']['repeat_count'], 2)

    def test_reference_missing_score_and_failure_do_not_release_or_invent_authority(self):
        # Disconnected reference evidence only; fixture association is not measured.
        model = AuthorityContractReference(classify)
        model.ingest('one', evidence(status='provisional'))
        model.ingest('one', evidence(2, status='missing', keyword=None, score=None))
        model.ingest('one', evidence(3, status='failure', keyword=None, score=None))
        result = model.review('one', thermal('positive'), association_valid=True)
        self.assertIsNotNone(result['candidate_decision'])
        self.assertEqual(result['authority'], 'UNRESOLVED')
        self.assertIsNone(result['event'])
        self.assertEqual(len(model.journal()), 3)


if __name__ == '__main__':
    unittest.main()
