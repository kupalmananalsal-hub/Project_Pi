"""C1.53 plain synthetic data only; no application imports or database fixtures."""
import ast
from copy import deepcopy
import itertools
from pathlib import Path
import unittest

try:
    from experiments import recognition_observation_contract as contract
except (ModuleNotFoundError, ImportError) as exc:
    if not (getattr(exc, 'name', '') or '').startswith('experiments'):
        raise
    contract = None


def observation(identity='v1', *, engine='vosk', producer='fixture', generation='g1',
                candidate='call', sequence=1, revision=1, status='partial',
                keyword='tulong', confidence=.4):
    control = status in {'missing', 'gap', 'failure', 'no_detection'}
    return dict(schema_version=1, record_type='recognition_observation',
        observation_id=identity, engine=engine, producer_id=producer,
        generation_id=generation, candidate_id=candidate, sequence=sequence,
        revision=None if control else revision, status=status,
        observed_at='2026-11-02T03:00:00+00:00', clock_domain='fixture-clock',
        capture_range={'first': 10, 'last': 20},
        original_payload={'text' if status == 'final' else 'partial':
                          'tulog' if keyword is None else keyword,
                          'nested': {'retain': [True, 1, 1.0]}},
        keyword=None if control else keyword,
        confidence=None if control else confidence,
        score_state=('missing' if status == 'missing' else 'not_applicable')
                    if control else ('missing' if confidence is None else 'present'),
        health='failed' if status == 'failure' else 'healthy')


class PureContractTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(contract, 'C1.53 pure experimental contract is absent')
        self.ledger = contract.EvidenceLedger()
        for engine in ('vosk', 'snowboy', 'openwakeword'):
            self.ledger.begin_generation(engine, 'fixture', 'g1')
        self.key = ('vosk', 'fixture', 'g1', 'call')

    def help(self, engine):
        return observation(engine, engine=engine, status='score', keyword='help')

    def receipt(self, outcome='rejected'):
        return dict(receipt_id='r1', observation_id='v1', outcome=outcome,
                    observed_at='2026-11-02T03:00:01+00:00', clock_domain='fixture-clock',
                    reason='synthetic publication result')

    def test_validation_preserves_original_json_and_supplied_provenance(self):
        item = observation(); result = contract.validate_observation(item)
        self.assertEqual(result, item)
        self.assertIsNot(result, item)
        self.assertIsNot(result['original_payload'], item['original_payload'])

    def test_partial_tulong_revised_to_tulog_keeps_trace_and_candidate(self):
        self.ledger.ingest(observation())
        self.ledger.ingest(observation('v2', sequence=2, revision=2, status='final', keyword=None))
        view = self.ledger.candidate(self.key)
        self.assertEqual(view['revision_history'], ['v1', 'v2'])
        self.assertEqual(view['recognition_status'], 'final')
        self.assertIsNone(view['keyword'])
        self.assertEqual(len(self.ledger.snapshot()['candidates']), 1)
        self.assertEqual([o['keyword'] for o in self.ledger.snapshot()['observations']], ['tulong', None])

    def test_partial_without_final_remains_provisional_data(self):
        self.ledger.ingest(observation())
        view = self.ledger.candidate(self.key)
        self.assertEqual(view['recognition_status'], 'partial')
        self.assertEqual(view['revision_history'], ['v1'])
        self.assertNotIn('event_id', view)
        self.assertNotIn('decision_state', view)

    def test_both_help_engines_survive_before_between_after_vosk_revision(self):
        for engine in ('snowboy', 'openwakeword'):
            for position in ('before', 'between', 'after'):
                with self.subTest(engine=engine, position=position):
                    ledger = contract.EvidenceLedger()
                    ledger.begin_generation('vosk', 'fixture', 'g1')
                    ledger.begin_generation(engine, 'fixture', 'g1')
                    if position == 'before': ledger.ingest(self.help(engine))
                    ledger.ingest(observation())
                    if position == 'between': ledger.ingest(self.help(engine))
                    ledger.ingest(observation('v2', sequence=2, revision=2, status='final', keyword=None))
                    if position == 'after': ledger.ingest(self.help(engine))
                    self.assertEqual(ledger.candidate((engine, 'fixture', 'g1', 'call'))['keyword'], 'help')
                    self.assertEqual(len(ledger.snapshot()['observations']), 3)

    def test_rejected_receipt_cannot_change_any_engine_evidence(self):
        self.ledger.ingest(observation())
        for engine in ('snowboy', 'openwakeword'): self.ledger.ingest(self.help(engine))
        before = self.ledger.snapshot()
        self.ledger.record_publication_receipt(self.receipt())
        after = self.ledger.snapshot()
        self.assertEqual(after['observations'], before['observations'])
        self.assertEqual(after['candidates'], before['candidates'])
        self.assertEqual(after['generations'], before['generations'])
        self.assertEqual(after['publication_receipts'][0]['outcome'], 'rejected')

    def test_accepted_receipt_is_not_an_alarm_or_durable_ack(self):
        self.ledger.ingest(observation())
        self.ledger.record_publication_receipt(self.receipt('accepted'))
        self.assertEqual(set(self.ledger.snapshot()),
            {'observations', 'candidates', 'generations', 'publication_receipts'})
        self.assertNotIn('event_id', self.ledger.snapshot()['publication_receipts'][0])

    def test_generation_failure_retains_evidence_and_finality(self):
        self.ledger.ingest(observation(status='final'))
        self.ledger.ingest(observation('f1', sequence=2, status='failure', candidate=None))
        view = self.ledger.candidate(self.key)
        self.assertEqual(view['keyword'], 'tulong')
        self.assertEqual(view['recognition_status'], 'final')
        self.assertEqual(view['generation_health'], 'failed')

    def test_failed_generation_cannot_heal_through_redeclaration_or_no_detection(self):
        self.ledger.ingest(observation(status='failure', candidate=None))
        before = self.ledger.snapshot()
        self.ledger.begin_generation('vosk', 'fixture', 'g1')
        with self.assertRaises(ValueError):
            self.ledger.ingest(observation('v2', sequence=2, status='no_detection', candidate=None))
        self.assertEqual(self.ledger.snapshot(), before)

    def test_recovery_is_new_generation_not_implicit_new_episode(self):
        self.ledger.ingest(observation())
        self.ledger.ingest(observation('f1', sequence=2, status='failure'))
        self.ledger.begin_generation('vosk', 'fixture', 'g2')
        self.ledger.ingest(observation('v3', generation='g2'))
        self.assertFalse(self.ledger.candidate(self.key)['generation_active'])
        self.assertEqual(self.ledger.candidate(('vosk', 'fixture', 'g2', 'call'))['generation_health'], 'healthy')
        with self.assertRaises(ValueError): self.ledger.begin_generation('vosk', 'fixture', 'g1')
        self.assertNotIn('episodes', self.ledger.snapshot())

    def test_healthy_no_detection_is_distinct_from_failure(self):
        self.ledger.ingest(observation('none', engine='snowboy', status='no_detection', candidate=None))
        self.ledger.ingest(observation('fail', status='failure', candidate=None))
        health = {g['engine']: g['health'] for g in self.ledger.snapshot()['generations']}
        self.assertEqual(health['snowboy'], 'healthy')
        self.assertEqual(health['vosk'], 'failed')
        self.assertEqual(self.ledger.snapshot()['candidates'], [])

    def test_missing_scores_do_not_become_zero_or_erase_retained_evidence(self):
        self.ledger.ingest(self.help('openwakeword'))
        self.ledger.ingest(observation('missing', engine='openwakeword', sequence=2, status='missing'))
        view = self.ledger.candidate(('openwakeword', 'fixture', 'g1', 'call'))
        self.assertEqual(view['confidence'], .4)
        self.assertEqual(view['latest_status'], 'missing')
        self.assertEqual(view['evidence_observation_id'], 'openwakeword')
        missing = next(o for o in self.ledger.snapshot()['observations'] if o['observation_id'] == 'missing')
        self.assertIsNone(missing['confidence'])
        self.assertEqual(missing['score_state'], 'missing')

    def test_zero_score_remains_present_not_missing(self):
        self.ledger.ingest(observation(confidence=0))
        self.assertEqual(self.ledger.candidate(self.key)['confidence'], 0)
        self.assertEqual(self.ledger.snapshot()['observations'][0]['score_state'], 'present')

    def test_old_exact_retry_cannot_rewind_new_revision(self):
        self.ledger.ingest(observation())
        self.ledger.ingest(observation('v2', sequence=2, revision=2, status='final', keyword=None))
        before = self.ledger.snapshot()
        receipt = self.ledger.ingest(observation())
        self.assertEqual(receipt['outcome'], 'duplicate')
        self.assertEqual(self.ledger.snapshot(), before)

    def test_changed_identity_payload_is_rejected_atomically(self):
        self.ledger.ingest(observation()); before = self.ledger.snapshot()
        item = observation(); item['original_payload']['partial'] = 'changed'
        with self.assertRaises(ValueError): self.ledger.ingest(item)
        self.assertEqual(self.ledger.snapshot(), before)

    def test_json_identity_distinguishes_nested_booleans_integers_floats(self):
        first = observation(); self.ledger.ingest(first); before = self.ledger.snapshot()
        for values in ([1, 1, 1.0], [True, 1.0, 1.0], [True, 1, 1]):
            item = deepcopy(first); item['original_payload']['nested']['retain'] = values
            with self.subTest(values=values):
                self.assertNotEqual(contract.canonical_identity(first), contract.canonical_identity(item))
                with self.assertRaises(ValueError): self.ledger.ingest(item)
                self.assertEqual(self.ledger.snapshot(), before)

    def test_key_order_changes_do_not_change_json_value_identity(self):
        item = observation(); self.ledger.ingest(item)
        reordered = dict(reversed(list(item.items())))
        self.assertEqual(contract.canonical_identity(item), contract.canonical_identity(reordered))
        self.assertEqual(self.ledger.ingest(reordered)['outcome'], 'duplicate')

    def test_out_of_order_observations_are_rejected_without_rewind(self):
        self.ledger.ingest(observation()); before = self.ledger.snapshot()
        with self.assertRaises(ValueError): self.ledger.ingest(observation('v2', sequence=1, revision=2))
        self.assertEqual(self.ledger.snapshot(), before)

    def test_sequence_gap_marks_discontinuity_not_silence_or_release(self):
        self.ledger.ingest(observation())
        self.ledger.ingest(observation('v3', sequence=3, revision=2))
        self.assertFalse(self.ledger.candidate(self.key)['continuous'])
        self.assertEqual(self.ledger.candidate(self.key)['keyword'], 'tulong')

    def test_final_candidate_and_revision_order_are_enforced(self):
        self.ledger.ingest(observation(status='final')); before = self.ledger.snapshot()
        with self.assertRaises(ValueError): self.ledger.ingest(observation('v2', sequence=2, revision=2))
        self.assertEqual(self.ledger.snapshot(), before)
        item = observation('other', candidate='new', sequence=2, revision=3)
        with self.assertRaises(ValueError): self.ledger.ingest(item)

    def test_distinct_candidates_and_producers_are_not_merged(self):
        self.ledger.ingest(observation())
        self.ledger.ingest(observation('v2', candidate='call2', sequence=2))
        self.ledger.begin_generation('vosk', 'other', 'g1')
        self.ledger.ingest(observation('v3', producer='other'))
        self.assertEqual(len(self.ledger.snapshot()['candidates']), 3)
        self.assertEqual(self.ledger.candidate(self.key)['revision_history'], ['v1'])

    def test_all_valid_independent_interleavings_have_same_snapshot(self):
        inputs=[observation(), observation('v2', sequence=2, revision=2, status='final', keyword=None), self.help('snowboy'), self.help('openwakeword')]
        expected = None; schedules = 0
        for order in itertools.permutations(range(4)):
            if order.index(0) > order.index(1): continue
            ledger = contract.EvidenceLedger()
            for engine in ('vosk', 'snowboy', 'openwakeword'): ledger.begin_generation(engine, 'fixture', 'g1')
            for index in order: ledger.ingest(inputs[index])
            snapshot=ledger.snapshot(); schedules+=1
            if expected is None: expected=snapshot
            self.assertEqual(snapshot, expected)
        self.assertEqual(schedules, 12)

    def test_invalid_score_states_and_metadata_never_mutate_ledger(self):
        cases=[{'sequence':True},{'schema_version':True},{'revision':True},
               {'confidence':True},{'confidence':float('nan')},{'confidence':float('inf')},
               {'confidence':-.1},{'confidence':1.1},{'score_state':'missing'},
               {'health':'failed'},{'record_type':'critical_alert'},{'decision_state':'critical'},
               {'observed_at':'2026-11-02T03:00:00'},{'capture_range':{'first':20,'last':10}}]
        for updates in cases:
            with self.subTest(updates=repr(updates)):
                item=observation();item.update(updates);before=self.ledger.snapshot()
                with self.assertRaises(ValueError):self.ledger.ingest(item)
                self.assertEqual(self.ledger.snapshot(),before)

    def test_original_json_cannot_contain_cycles_or_lossy_key_types(self):
        for payload in ({1:'integer-key'}, {'tuple':(1,2)}):
            item=observation();item['original_payload']=payload
            with self.assertRaises(ValueError):self.ledger.ingest(item)
        item=observation();item['original_payload']['cycle']=item['original_payload']
        with self.assertRaises(ValueError):self.ledger.ingest(item)

    def test_input_and_returned_reference_mutations_cannot_change_state(self):
        item=observation();self.ledger.ingest(item)
        item['original_payload']['nested']['retain'].append('changed')
        item['capture_range']['last']=999
        snapshot=self.ledger.snapshot();snapshot['observations'][0]['keyword']='changed'
        snapshot['candidates'][0]['revision_history'].append('changed')
        view=self.ledger.candidate(self.key);view['keyword']='changed'
        self.assertEqual(self.ledger.snapshot()['observations'][0],observation())
        self.assertEqual(self.ledger.candidate(self.key)['revision_history'],['v1'])

    def test_publication_receipt_retry_conflict_unknown_identity_and_copying(self):
        self.ledger.ingest(observation());receipt=self.receipt()
        self.ledger.record_publication_receipt(receipt);self.ledger.record_publication_receipt(receipt)
        receipt['reason']='caller mutation';before=self.ledger.snapshot()
        with self.assertRaises(ValueError):self.ledger.record_publication_receipt(self.receipt('accepted'))
        unknown=self.receipt();unknown['receipt_id']='r2';unknown['observation_id']='absent'
        with self.assertRaises(ValueError):self.ledger.record_publication_receipt(unknown)
        exported=self.ledger.snapshot();exported['publication_receipts'][0]['reason']='changed'
        self.assertEqual(self.ledger.snapshot(),before)

    def test_missing_asr_confidence_is_allowed_without_fabricating_score(self):
        self.ledger.ingest(observation(confidence=None))
        self.assertIsNone(self.ledger.candidate(self.key)['confidence'])
        self.assertEqual(self.ledger.snapshot()['observations'][0]['score_state'],'missing')

    def test_detector_only_help_keeps_label_without_inventing_confidence(self):
        item=observation('snowboy',engine='snowboy',status='detection',keyword='help',confidence=None)
        item['original_payload']={'detector_index':1}
        try:
            self.ledger.ingest(item)
        except ValueError as exc:
            self.fail('known detector label with absent confidence must be representable: '+str(exc))
        view=self.ledger.candidate(('snowboy','fixture','g1','call'))
        self.assertEqual(view['keyword'],'help')
        self.assertIsNone(view['confidence'])
        self.assertEqual(view['recognition_status'],'detection')
        self.assertEqual(self.ledger.snapshot()['observations'][0]['score_state'],'missing')
        self.assertEqual(self.ledger.snapshot()['observations'][0]['original_payload'],{'detector_index':1})

    def test_pure_module_has_no_io_callbacks_thermal_or_alert_api(self):
        tree=ast.parse(Path(contract.__file__).read_text())
        imports=set()
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):imports.update(a.name for a in node.names)
            if isinstance(node,ast.ImportFrom):imports.add(node.module)
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
                self.assertNotIn(node.func.id,{'open','eval','exec','__import__','getattr','setattr'})
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                self.assertNotIn(node.func.attr,{'now','today','publish','post','connect','write_text','write_bytes','system','Popen'})
        self.assertLessEqual(imports,{'json','math','datetime'})
        self.assertEqual({n.name for n in tree.body if isinstance(n,ast.ClassDef)}, {'EvidenceLedger'})


if __name__=='__main__':unittest.main()
