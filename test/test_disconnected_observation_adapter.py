"""C1.51 synthetic, disconnected contract tests; no audio/model/device access."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

try:
    from test.disconnected_observation_reference import ObservationAdapter, EpisodeContract
except ModuleNotFoundError as exc:
    if exc.name != 'test.disconnected_observation_reference':
        raise
    ObservationAdapter = EpisodeContract = None


def observation(identity='v1', *, engine='vosk', generation='g1', candidate='call',
                sequence=1, revision=1, kind='partial', text='tulong',
                keyword='tulong', confidence=.4):
    control = kind in {'missing', 'gap', 'failure'}
    payload = ({'partial' if kind == 'partial' else 'text': text,
                'fixture_extra': {'keep': [1, 2]}} if engine == 'vosk' and not control
               else {'fixture': kind})
    return dict(schema_version=1, observation_id=identity, engine=engine,
                generation=generation, candidate_id=candidate, sequence=sequence,
                revision=None if control else revision, kind=kind,
                observed_at='2026-11-02T02:00:00+00:00', original_payload=payload,
                keyword=None if control else keyword,
                confidence=None if control else confidence,
                score_state=('missing' if kind == 'missing' else 'not_applicable')
                    if control else ('missing' if confidence is None else 'present'))


def frame(identity='t1', state='negative'):
    return dict(thermal_id=identity, observed_at='2026-11-02T02:00:01+00:00',
                payload={'thermal_state': state, 'human_detected': state == 'positive',
                         'frame_valid': True, 'frame_age_seconds': 0.0})


class Fixtures:
    def setUp(self):
        self.assertIsNotNone(ObservationAdapter, 'C1.51 reference adapter is absent')
        self.adapter = ObservationAdapter(lambda text: 'tulong' if text.strip().lower() == 'tulong' else None)
        for engine in ('vosk', 'snowboy', 'openwakeword'):
            self.adapter.begin_generation(engine, 'g1')
        self.key = ('vosk', 'g1', 'call')

    def help(self, engine):
        return observation(engine+'1', engine=engine, kind='score', keyword='help')

    def receipt(self, outcome='rejected'):
        return dict(receipt_id='receipt1', observation_id='v1', outcome=outcome,
                    observed_at='2026-11-02T02:00:02+00:00', reason='fixture decision')

    def snapshot(self):
        return (self.adapter.journal(), self.adapter.candidates(), self.adapter.receipts())


class ObservationTests(Fixtures, unittest.TestCase):
    def test_original_payload_timestamp_and_finality_are_preserved(self):
        first = observation()
        self.adapter.ingest(first)
        self.adapter.ingest(observation('v2', sequence=2, revision=2, kind='final'))
        self.assertEqual(self.adapter.journal()[0], first)
        self.assertEqual([o['kind'] for o in self.adapter.journal()], ['partial', 'final'])
        view = self.adapter.candidate(self.key)
        self.assertEqual(view['evidence_status'], 'final')
        self.assertEqual(view['revision'], 2)

    def test_partial_tulong_revision_stays_same_candidate_and_trace(self):
        self.adapter.ingest(observation())
        self.adapter.ingest(observation('v2', sequence=2, revision=2, kind='final', text='tulog', keyword=None))
        self.assertEqual(len(self.adapter.candidates()), 1)
        self.assertIsNone(self.adapter.candidate(self.key)['keyword'])
        self.assertEqual([o['candidate_id'] for o in self.adapter.journal()], ['call', 'call'])
        self.assertEqual([o['keyword'] for o in self.adapter.journal()], ['tulong', None])

    def test_partial_only_is_retained_without_invented_final(self):
        self.adapter.ingest(observation())
        self.assertEqual(self.adapter.candidate(self.key)['evidence_status'], 'partial')
        self.assertEqual(len(self.adapter.journal()), 1)
        self.assertEqual(self.adapter.receipts(), [])

    def test_both_help_engines_survive_vosk_ordinary_revision(self):
        for engine in ('snowboy', 'openwakeword'):
            self.adapter.ingest(self.help(engine))
        self.adapter.ingest(observation())
        self.adapter.ingest(observation('v2', sequence=2, revision=2, kind='final', text='tulog', keyword=None))
        for engine in ('snowboy', 'openwakeword'):
            self.assertEqual(self.adapter.candidate((engine, 'g1', 'call'))['keyword'], 'help')

    def test_help_before_between_and_after_vosk_ordinary_revision_is_retained(self):
        for engine in ('snowboy', 'openwakeword'):
            for arrival in ('before', 'between', 'after'):
                with self.subTest(engine=engine, arrival=arrival):
                    adapter = ObservationAdapter(lambda text: 'tulong' if text == 'tulong' else None)
                    adapter.begin_generation('vosk', 'g1'); adapter.begin_generation(engine, 'g1')
                    if arrival == 'before': adapter.ingest(self.help(engine))
                    adapter.ingest(observation())
                    if arrival == 'between': adapter.ingest(self.help(engine))
                    adapter.ingest(observation('v2', sequence=2, revision=2, kind='final', text='tulog', keyword=None))
                    if arrival == 'after': adapter.ingest(self.help(engine))
                    self.assertEqual(adapter.candidate((engine, 'g1', 'call'))['keyword'], 'help')
                    self.assertIsNone(adapter.candidate(self.key)['keyword'])
                    self.assertEqual(len(adapter.journal()), 3)

    def test_rejected_submission_before_help_cannot_change_evidence(self):
        self.adapter.ingest(observation())
        before = self.adapter.candidates()
        self.adapter.record_receipt(self.receipt())
        self.assertEqual(self.adapter.candidates(), before)
        for engine in ('snowboy', 'openwakeword'):
            self.adapter.ingest(self.help(engine))
            self.assertEqual(self.adapter.candidate((engine, 'g1', 'call'))['keyword'], 'help')
        self.assertEqual(self.adapter.receipts()[0]['outcome'], 'rejected')

    def test_receipt_retry_is_idempotent_and_conflict_is_atomic(self):
        self.adapter.ingest(observation())
        self.adapter.record_receipt(self.receipt())
        self.adapter.record_receipt(self.receipt())
        before = self.snapshot()
        with self.assertRaises(ValueError): self.adapter.record_receipt(self.receipt('accepted'))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(len(self.adapter.receipts()), 1)

    def test_missing_score_is_not_zero_or_silence_or_evidence_erasure(self):
        self.adapter.ingest(observation('o1', engine='openwakeword', kind='score'))
        self.adapter.ingest(observation('o2', engine='openwakeword', sequence=2, kind='missing'))
        view = self.adapter.candidate(('openwakeword', 'g1', 'call'))
        self.assertEqual(view['confidence'], .4)
        self.assertEqual(view['evidence_observation_id'], 'o1')
        self.assertEqual(view['latest_kind'], 'missing')
        self.assertEqual(self.adapter.journal()[-1]['score_state'], 'missing')
        self.assertIsNone(self.adapter.journal()[-1]['confidence'])

    def test_failure_retains_evidence_and_requires_new_generation(self):
        self.adapter.ingest(observation())
        self.adapter.ingest(observation('f1', sequence=2, kind='failure'))
        before = self.snapshot()
        with self.assertRaises(ValueError): self.adapter.ingest(observation('v2', sequence=3, revision=2))
        self.assertEqual(self.snapshot(), before)
        self.adapter.begin_generation('vosk', 'g2')
        self.adapter.ingest(observation('v3', generation='g2'))
        self.assertEqual(self.adapter.candidate(self.key)['health'], 'failed')
        self.assertEqual(self.adapter.candidate(self.key)['keyword'], 'tulong')
        self.assertEqual(self.adapter.candidate(('vosk', 'g2', 'call'))['health'], 'ok')

    def test_retired_generation_cannot_resume_or_be_reactivated(self):
        self.adapter.ingest(observation())
        self.adapter.begin_generation('vosk', 'g2')
        before = self.snapshot()
        with self.assertRaises(ValueError): self.adapter.ingest(observation('v2', sequence=2, revision=2))
        with self.assertRaises(ValueError): self.adapter.begin_generation('vosk', 'g1')
        self.assertEqual(self.snapshot(), before)

    def test_duplicate_old_observation_does_not_rewind_revision(self):
        first = observation()
        self.adapter.ingest(first)
        self.adapter.ingest(observation('v2', sequence=2, revision=2, kind='final', text='tulog', keyword=None))
        before = self.snapshot()
        self.adapter.ingest(first)
        self.assertEqual(self.snapshot(), before)

    def test_conflicting_observation_id_is_atomic(self):
        self.adapter.ingest(observation())
        before = self.snapshot()
        changed = observation(); changed['original_payload']['fixture_extra'] = 'changed'
        with self.assertRaises(ValueError): self.adapter.ingest(changed)
        self.assertEqual(self.snapshot(), before)

    def test_retry_identity_distinguishes_json_boolean_integer_and_float(self):
        first = observation(); first['original_payload']['nested'] = [True, 1]
        self.adapter.ingest(first)
        before = self.snapshot()
        for replacement in ([1, 1], [True, 1.0]):
            item = deepcopy(first); item['original_payload']['nested'] = replacement
            with self.subTest(replacement=replacement):
                with self.assertRaises(ValueError): self.adapter.ingest(item)
                self.assertEqual(self.snapshot(), before)

    def test_out_of_order_sequence_and_revision_jump_are_atomic(self):
        self.adapter.ingest(observation())
        before = self.snapshot()
        for item in (observation('v2', sequence=1, revision=2), observation('v2', sequence=2, revision=3)):
            with self.assertRaises(ValueError): self.adapter.ingest(item)
            self.assertEqual(self.snapshot(), before)

    def test_final_candidate_cannot_be_reopened_by_later_partial(self):
        self.adapter.ingest(observation(kind='final'))
        with self.assertRaises(ValueError): self.adapter.ingest(observation('v2', sequence=2, revision=2))

    def test_failure_does_not_relabel_final_evidence_as_provisional(self):
        self.adapter.ingest(observation(kind='final'))
        self.adapter.ingest(observation('f1', sequence=2, kind='failure'))
        view = self.adapter.candidate(self.key)
        self.assertEqual(view['evidence_status'], 'final')
        self.assertEqual(view['health'], 'failed')

    def test_sequence_gap_is_unknown_continuity_not_release(self):
        self.adapter.ingest(observation())
        self.adapter.ingest(observation('v3', sequence=3, revision=2))
        view = self.adapter.candidate(self.key)
        self.assertFalse(view['continuous'])
        self.assertEqual(view['keyword'], 'tulong')

    def test_invalid_metadata_payload_and_scores_are_rejected_atomically(self):
        cases = [dict(sequence=True), dict(revision=True), dict(schema_version=True),
                 dict(confidence=True), dict(confidence=float('nan')), dict(confidence=1.1),
                 dict(score_state='missing'), dict(observed_at='2026-11-02T02:00:00'),
                 dict(kind='silence'), dict(engine='unknown'), dict(extra='unknown field')]
        for update in cases:
            item = observation(); item.update(update)
            with self.subTest(update=repr(update)):
                before = self.snapshot()
                with self.assertRaises(ValueError): self.adapter.ingest(item)
                self.assertEqual(self.snapshot(), before)
        item = observation(); item['original_payload'] = {1: 'non-string key'}
        with self.assertRaises(ValueError): self.adapter.ingest(item)

    def test_vosk_raw_payload_and_fixture_keyword_must_agree(self):
        with self.assertRaises(ValueError): self.adapter.ingest(observation(text='tulog'))
        item = observation(); item['original_payload']['partial'] = 12
        with self.assertRaises(ValueError): self.adapter.ingest(item)

    def test_inputs_and_exports_cannot_mutate_retained_evidence(self):
        item = observation(); self.adapter.ingest(item)
        item['original_payload']['fixture_extra']['keep'].append(3)
        exported = self.adapter.journal(); exported[0]['keyword'] = 'changed'
        views = self.adapter.candidates(); views[0]['keyword'] = 'changed'
        self.assertEqual(self.adapter.journal()[0], observation())
        self.assertEqual(self.adapter.candidate(self.key)['keyword'], 'tulong')


class EpisodeTests(Fixtures, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.assertIsNotNone(EpisodeContract)
        self.calls = []
        # Existing classifier in a fresh fixture evaluator; no new thresholds.
        from test.test_episode_rearming_review import classify
        def classify_snapshot(voice, thermal):
            self.calls.append(deepcopy(voice))
            return classify(voice, thermal)
        self.contract = EpisodeContract(self.adapter, classify_snapshot)
        self.adapter.ingest(observation(kind='final'))
        self.contract.bind_episode('episode1', self.key)

    def review(self, thermal=None, *, episode='episode1', association=True, eligible=True):
        return self.contract.reevaluate(episode, thermal or frame(),
            association_valid=association, classification_eligible=eligible)

    def test_advisory_and_later_critical_have_distinct_immutable_event_ids(self):
        advisory = self.review()['event']
        critical = self.review(frame('t2', 'positive'))['event']
        self.assertEqual([advisory['decision_state'], critical['decision_state']], ['advisory', 'critical'])
        self.assertNotEqual(advisory['event_id'], critical['event_id'])
        self.assertEqual(advisory['episode_id'], critical['episode_id'])
        self.assertEqual(advisory['observation_id'], critical['observation_id'])
        self.assertEqual(self.contract.events()[0], advisory)
        self.assertEqual(critical['audible_authority'], 'UNRESOLVED')
        self.assertEqual(critical['event_kind'], 'fixture_classification_transition')

    def test_repeated_same_or_equivalent_thermal_cannot_duplicate_critical(self):
        self.review(); self.review(frame('t2', 'positive'))
        for thermal in (frame('t2', 'positive'), frame('t3', 'positive'), frame('t4'), frame('t5', 'positive')):
            self.assertIsNone(self.review(thermal)['event'])
        self.assertEqual(len(self.contract.events()), 2)
        self.assertEqual(len(self.adapter.journal()), 1)

    def test_rejected_receipt_cannot_block_independent_episode(self):
        self.adapter.record_receipt(self.receipt())
        for engine in ('snowboy', 'openwakeword'):
            self.adapter.ingest(self.help(engine))
            self.contract.bind_episode(engine, (engine, 'g1', 'call'))
            result = self.review(frame('positive', 'positive'), episode=engine)
            self.assertEqual(result['event']['keyword'], 'help')

    def test_accepted_receipt_does_not_supply_classification_or_audible_authority(self):
        self.adapter.record_receipt(self.receipt('accepted'))
        self.assertEqual(self.contract.events(), [])
        result = self.review(frame('t2', 'positive'), eligible=False)
        self.assertIsNone(result['classification'])
        self.assertEqual(result['audible_authority'], 'UNRESOLVED')

    def test_duplicate_observation_and_binding_cannot_fabricate_new_episode(self):
        self.adapter.ingest(observation(kind='final'))
        self.contract.bind_episode('episode1', self.key)
        with self.assertRaises(ValueError): self.contract.bind_episode('duplicate-episode', self.key)
        self.assertEqual(len(self.contract.bindings()), 1)

    def test_two_independent_episodes_remain_eligible(self):
        first = self.review(frame('t2', 'positive'))['event']
        self.adapter.ingest(observation('v2', candidate='new-call', sequence=2, kind='final'))
        self.contract.bind_episode('episode2', ('vosk', 'g1', 'new-call'))
        second = self.review(frame('t2', 'positive'), episode='episode2')['event']
        self.assertNotEqual(first['event_id'], second['event_id'])
        self.assertEqual(len(self.contract.bindings()), 2)

    def test_cross_engine_rebinding_and_unknown_candidate_are_rejected(self):
        self.adapter.ingest(self.help('snowboy'))
        with self.assertRaises(ValueError): self.contract.bind_episode('episode1', ('snowboy', 'g1', 'call'))
        with self.assertRaises(ValueError): self.contract.bind_episode('missing', ('vosk', 'g1', 'absent'))

    def test_no_implicit_association_or_classification_eligibility(self):
        self.assertIsNone(self.review(frame('t2', 'positive'), association=False)['event'])
        self.assertIsNone(self.review(frame('t2', 'positive'), eligible=False)['event'])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.contract.events(), [])
        with self.assertRaises(ValueError): self.review(association='yes')
        with self.assertRaises(ValueError): self.review(eligible=1)

    def test_revised_ordinary_candidate_cannot_borrow_old_voice(self):
        adapter = ObservationAdapter(lambda text: 'tulong' if text == 'tulong' else None)
        adapter.begin_generation('vosk', 'g1'); adapter.ingest(observation())
        contract = EpisodeContract(adapter, self.contract.classify)
        contract.bind_episode('one', self.key)
        adapter.ingest(observation('v2', sequence=2, revision=2, kind='final', text='tulog', keyword=None))
        result = contract.reevaluate('one', frame('t2', 'positive'), association_valid=True, classification_eligible=True)
        self.assertIsNone(result['classification'])
        self.assertEqual(contract.events(), [])

    def test_failure_retained_evidence_requires_explicit_fixture_eligibility(self):
        self.adapter.ingest(observation('f1', sequence=2, kind='failure'))
        self.assertIsNone(self.review(frame('t2', 'positive'), eligible=False)['event'])
        result = self.review(frame('t2', 'positive'))
        self.assertEqual(result['health'], 'failed')
        self.assertEqual(result['event']['audible_authority'], 'UNRESOLVED')

    def test_missing_initial_confidence_does_not_invent_classification(self):
        self.adapter.ingest(observation('o1', engine='openwakeword', kind='score', confidence=None))
        self.contract.bind_episode('missing-score', ('openwakeword', 'g1', 'call'))
        self.assertIsNone(self.review(frame('t2', 'positive'), episode='missing-score')['event'])

    def test_thermal_identity_conflict_and_classifier_failure_are_atomic(self):
        self.review()
        before = (self.contract.events(), self.contract.thermal_journal())
        with self.assertRaises(ValueError): self.review(frame('t1', 'positive'))
        self.assertEqual((self.contract.events(), self.contract.thermal_journal()), before)
        def failing(voice, thermal): raise RuntimeError('synthetic callback failure')
        self.contract.classify = failing
        with self.assertRaises(RuntimeError): self.review(frame('t2', 'positive'))
        self.assertEqual((self.contract.events(), self.contract.thermal_journal()), before)

    def test_thermal_identity_distinguishes_json_types_before_classification(self):
        first = frame(); first['payload']['nested'] = [True, 1]
        self.review(first)
        before = (self.contract.events(), self.contract.thermal_journal(), deepcopy(self.calls))
        for replacement in ([1, 1], [True, 1.0]):
            item = deepcopy(first); item['payload']['nested'] = replacement
            with self.subTest(replacement=replacement):
                with self.assertRaises(ValueError): self.review(item)
                self.assertEqual((self.contract.events(), self.contract.thermal_journal(), self.calls), before)

    def test_callback_and_export_mutation_cannot_rewrite_events_or_evidence(self):
        def mutating(voice, thermal):
            voice['keyword'] = 'changed'; thermal['thermal_state'] = 'changed'
            return {'decision_state': 'advisory', 'event_id': 'forged'}
        self.contract.classify = mutating
        result = self.review()
        self.assertEqual(result['event']['keyword'], 'tulong')
        self.assertNotEqual(result['event']['event_id'], 'forged')
        result['event']['keyword'] = 'changed'
        self.assertEqual(self.contract.events()[0]['keyword'], 'tulong')
        self.assertEqual(self.adapter.candidate(self.key)['keyword'], 'tulong')

    def test_synthetic_backend_retry_and_replay_keep_transition_ids(self):
        from test.test_alert_delivery import store_class, Conflict
        from test.test_episode_rearming_review import fingerprint_function
        from alert_delivery import replay_eligible
        advisory = self.review()['event']
        critical = self.review(frame('t2', 'positive'))['event']
        fingerprint = fingerprint_function()
        with tempfile.TemporaryDirectory(prefix='C1_51_store_', dir=Path(__file__).resolve().parents[1]) as tmp:
            path = Path(tmp)/'synthetic.db'; Store = store_class(); store = Store(path)
            for item in (advisory, critical, critical):
                store.insert({**item, '_request_fingerprint': fingerprint(item)})
            reopened = Store(path); _, high = reopened.delivery_boundary()
            replay = reopened.replay(0, high)
            self.assertEqual([e['event_id'] for e in replay], [advisory['event_id'], critical['event_id']])
            reopened.offer('fixture-phone', advisory['event_id'])
            reopened.acknowledge('fixture-phone', advisory['event_id'], replay[0]['sequence'], 'ack_user_confirmed')
            self.assertTrue(replay_eligible(replay[1], reopened.offer('fixture-phone', critical['event_id']), datetime.now(timezone.utc)))
            with self.assertRaises(Conflict): reopened.lookup(critical['event_id'], 'changed payload')
        self.assertEqual(len(self.contract.bindings()), 1)
        self.assertEqual(len(self.adapter.journal()), 1)


if __name__ == '__main__':
    unittest.main()
