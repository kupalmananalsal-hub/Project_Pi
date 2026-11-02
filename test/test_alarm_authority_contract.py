"""C1.47 synthetic contract checks; authority/association/boundaries are fixtures.

These catch evidence loss, cross-source cancellation, duplicate transitions and
identity mutation in the disconnected reference, not acoustic mistakes in Vosk.
"""
from copy import deepcopy
from datetime import datetime, timezone
import tempfile
from pathlib import Path
import unittest

from test.test_episode_rearming_review import classify, thermal, fingerprint_function
from test.test_alert_delivery import store_class, Conflict
from alert_delivery import replay_eligible
from test.vosk_hypothesis_reference import HypothesisReference
from test.test_vosk_hypothesis_revision import observation

try:
    from test.alarm_authority_contract_reference import AuthorityContractReference
except ModuleNotFoundError as exc:
    if exc.name != 'test.alarm_authority_contract_reference':
        raise
    AuthorityContractReference = None


def evidence(seq=1, *, source='vosk', session='s1', status='final',
             keyword='tulong', score=.4):
    return dict(observation_id=f'{source}:{session}:{seq}', sequence=seq,
                source=source, session=session, status=status, keyword=keyword,
                confidence=score, snr_db=25.0,
                timestamp='2026-11-02T00:00:00+00:00')


class AuthorityContractTest(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(AuthorityContractReference,
                             'C1.47 test-only contract reference is absent')
        self.model = AuthorityContractReference(classify)

    def review(self, episode='one', state='negative', *, authority='FIXTURE_AUTHORIZED',
               valid=True):
        return self.model.review(episode, thermal(state), association_valid=valid,
                                 authority=authority)

    def test_partial_tulong_revised_to_tulog_keeps_history_but_no_current_distress(self):
        ledger = HypothesisReference(lambda text: 'tulong' if text == 'tulong' else None)
        ledger.ingest(observation(1))
        first = evidence(status='provisional')
        first['original'] = ledger.journal()[0]
        self.model.ingest('one', first)
        self.assertEqual(self.review(authority='UNRESOLVED')['candidate_decision']['decision_state'], 'advisory')
        ledger.ingest(observation(2, 'final', 'tulog'))
        corrected = evidence(2, keyword=None, score=None)
        corrected['original'] = ledger.journal()[1]
        self.model.ingest('one', corrected)
        self.assertIsNone(self.review(state='positive')['candidate_decision'])
        self.assertEqual(self.model.journal(), [first, corrected])
        self.assertEqual(self.model.events(), [])

    def test_partial_only_distress_retained_without_invented_siren_authority(self):
        self.model.ingest('one', evidence(status='provisional'))
        for state in ('negative', 'positive', 'unavailable'):
            result = self.review(state=state, authority='UNRESOLVED')
            self.assertIsNotNone(result['candidate_decision'])
            self.assertEqual(result['authority'], 'UNRESOLVED')
            self.assertIsNone(result['event'])
        self.assertEqual(len(self.model.journal()), 1)
        self.assertEqual(self.model.events(), [])

    def test_finalized_distress_classified_without_automatic_authority(self):
        self.model.ingest('one', evidence(score=.9))
        unresolved = self.review(authority='UNRESOLVED')
        self.assertEqual(unresolved['candidate_decision']['decision_state'], 'critical')
        self.assertIsNone(unresolved['event'])
        authorized = self.review()['event']
        self.assertEqual(authorized['decision_state'], 'critical')

    def test_thermal_escalation_uses_new_event_and_same_voice_without_new_ingestion(self):
        self.model.ingest('one', evidence())
        notice = self.review()['event']
        critical = self.review(state='positive')['event']
        self.assertEqual([notice['decision_state'], critical['decision_state']], ['advisory', 'critical'])
        self.assertNotEqual(notice['event_id'], critical['event_id'])
        self.assertEqual(notice['observation_id'], critical['observation_id'])
        self.assertEqual(notice['episode_id'], critical['episode_id'])
        self.assertEqual(self.model.voice_episode_count(), 1)
        self.assertEqual(len(self.model.journal()), 1)

    def test_identical_thermal_updates_and_flapping_do_not_rearm_critical(self):
        self.model.ingest('one', evidence())
        self.review()
        self.review(state='positive')
        for state in ('positive', 'positive', 'negative', 'unavailable', 'positive'):
            self.assertIsNone(self.review(state=state)['event'])
        self.assertEqual([e['decision_state'] for e in self.model.events()], ['advisory', 'critical'])

    def test_independent_snowboy_and_openwakeword_survive_unresolved_vosk(self):
        self.model.ingest('vosk-episode', evidence(status='provisional'))
        self.review('vosk-episode', 'positive', authority='UNRESOLVED')
        for source in ('snowboy', 'openwakeword'):
            self.model.ingest(source, evidence(source=source, keyword='help', status='score', score=.9))
            self.assertEqual(self.review(source)['event']['source'], source)
        self.assertEqual(len(self.model.events()), 2)
        self.assertTrue(all(e['keyword'] == 'help' for e in self.model.events()))

    def test_engine_failure_visible_does_not_erase_unresolved_evidence(self):
        self.model.ingest('one', evidence(status='provisional'))
        self.model.ingest('one', evidence(2, status='failure', score=None, keyword=None))
        result = self.review(state='positive', authority='UNRESOLVED')
        self.assertEqual(result['health'], 'failed')
        self.assertEqual(result['candidate_decision']['decision_state'], 'critical')
        self.assertIsNone(result['event'])
        self.assertEqual(len(self.model.journal()), 2)

    def test_failure_does_not_veto_valid_associated_thermal_upgrade(self):
        self.model.ingest('one', evidence())
        self.review()
        self.model.ingest('one', evidence(2, status='failure', score=None, keyword=None))
        self.assertEqual(self.review(state='positive')['event']['decision_state'], 'critical')

    def test_invalid_association_prevents_stale_voice_thermal_pairing(self):
        self.model.ingest('one', evidence())
        result = self.review(state='positive', valid=False)
        self.assertIsNone(result['event'])
        self.assertIsNone(result['candidate_decision'])
        self.assertEqual(len(self.model.journal()), 1)

    def test_unavailable_stale_invalid_thermal_do_not_supply_positive_evidence(self):
        self.model.ingest('one', evidence())
        for state in ('unavailable', 'stale', 'invalid'):
            result = self.review(state=state, authority='UNRESOLVED')
            self.assertEqual(result['candidate_decision']['decision_state'], 'advisory')
            self.assertEqual(result['candidate_decision']['thermal_state'], state)

    def test_high_voice_only_candidate_does_not_require_positive_thermal(self):
        self.model.ingest('one', evidence(source='openwakeword', status='score', score=.9))
        self.assertEqual(self.review(state='unavailable')['event']['decision_reason'], 'voice_high_confidence')

    def test_separate_fixture_distress_episodes_get_independent_events(self):
        for seq, episode in enumerate(('one', 'two'), 1):
            self.model.ingest(episode, evidence(seq, score=.9))
            self.review(episode)
        outputs = self.model.events()
        self.assertEqual(len(outputs), 2)
        self.assertNotEqual(outputs[0]['event_id'], outputs[1]['event_id'])
        self.assertEqual(self.model.voice_episode_count(), 2)

    def test_repeated_sustained_scores_are_not_new_voice_episodes(self):
        for seq in range(1, 5):
            self.model.ingest('one', evidence(seq, source='openwakeword', status='score', score=.9))
            self.review()
        self.assertEqual(len(self.model.events()), 1)
        self.assertEqual(len(self.model.journal()), 4)
        self.assertEqual(self.model.voice_episode_count(), 1)

    def test_polling_never_increments_voice_episode_or_observation_count(self):
        self.model.ingest('one', evidence(score=.75))
        for _ in range(4):
            result = self.review()
            self.assertEqual(result['candidate_decision']['decision_state'], 'advisory')
            self.assertEqual(result['candidate_decision']['decision_factors']['repeat_count'], 1)
        self.assertEqual(self.model.voice_episode_count(), 1)
        self.assertEqual(len(self.model.journal()), 1)

    def test_missing_score_cannot_be_disguised_as_an_ordinary_score_revision(self):
        self.model.ingest('one', evidence(source='openwakeword', status='score', score=.9))
        with self.assertRaises(ValueError):
            self.model.ingest('one', evidence(2, source='openwakeword', status='score',
                                               keyword=None, score=None))
        self.assertEqual(len(self.model.journal()), 1)
        self.assertEqual(self.review()['event']['decision_state'], 'critical')

    def test_default_authority_does_not_publish_even_a_critical_candidate(self):
        self.model.ingest('one', evidence(score=.9))
        result = self.model.review('one', thermal('positive'), association_valid=True)
        self.assertEqual(result['authority'], 'UNRESOLVED')
        self.assertEqual(result['candidate_decision']['decision_state'], 'critical')
        self.assertEqual(self.model.events(), [])

    def test_missing_score_is_unknown_and_not_release_or_silence(self):
        self.model.ingest('one', evidence(source='openwakeword', status='score', score=.9))
        first = self.review()['event']
        self.model.ingest('one', evidence(2, source='openwakeword', status='missing', score=None, keyword=None))
        result = self.review()
        self.assertEqual(result['health'], 'unknown')
        self.assertEqual(result['candidate_decision']['decision_state'], 'critical')
        self.assertIsNone(result['event'])
        self.assertEqual(self.model.events(), [first])

    def test_retry_does_not_rewind_revision_and_conflicting_identity_is_rejected(self):
        first = evidence(status='provisional')
        self.model.ingest('one', first)
        self.model.ingest('one', evidence(2, keyword=None, score=None))
        self.model.ingest('one', first)
        self.assertIsNone(self.review()['candidate_decision'])
        with self.assertRaises(ValueError):
            self.model.ingest('one', {**first, 'confidence': .9})
        self.assertEqual(len(self.model.journal()), 2)

    def test_retry_cannot_reassign_observation_to_another_episode(self):
        first = evidence()
        self.model.ingest('one', first)
        with self.assertRaises(ValueError):
            self.model.ingest('two', first)
        self.assertEqual(self.model.voice_episode_count(), 1)

    def test_episode_cannot_merge_independent_sources_or_keywords(self):
        self.model.ingest('one', evidence())
        for changed in (evidence(source='snowboy'), evidence(2, keyword='aray')):
            with self.assertRaises(ValueError):
                self.model.ingest('one', changed)
        self.assertEqual(len(self.model.journal()), 1)

    def test_old_session_cannot_resume_after_failure_new_session_stays_separate(self):
        self.model.ingest('one', evidence(status='provisional'))
        self.model.ingest('one', evidence(2, status='failure', score=None, keyword=None))
        with self.assertRaises(ValueError):
            self.model.ingest('one', evidence(3))
        self.model.ingest('new', evidence(session='s2', score=.9))
        self.assertEqual(self.review('new')['health'], 'ok')
        self.assertEqual(self.review('one', authority='UNRESOLVED')['health'], 'failed')

    def test_revision_cannot_rewrite_or_auto_confirm_an_existing_critical(self):
        self.model.ingest('one', evidence(status='provisional', score=.9))
        # Deliberately permissive fixture demonstrates irreversible-alert risk.
        first = self.review()['event']
        self.model.ingest('one', evidence(2, keyword=None, score=None))
        self.assertIsNone(self.review()['event'])
        self.assertEqual(self.model.events(), [first])
        self.assertNotIn('user_confirmed', first)

    def test_export_mutation_cannot_change_history_or_frozen_event(self):
        first = evidence(score=.9)
        self.model.ingest('one', first)
        event = self.review()['event']
        first['confidence'] = .1
        event['confidence'] = .1
        self.model.journal()[0]['confidence'] = .1
        self.assertEqual(self.model.journal()[0]['confidence'], .9)
        self.assertEqual(self.model.events()[0]['confidence'], .9)

    def test_reconnection_replays_existing_uuid_and_advisory_ack_does_not_ack_critical(self):
        self.model.ingest('one', evidence())
        notice = self.review()['event']
        critical = self.review(state='positive')['event']
        fingerprint = fingerprint_function()
        Store = store_class()  # AST extraction only; no backend startup.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'synthetic.db'
            store = Store(path)
            for event in (notice, critical):
                store.insert({**event, '_request_fingerprint': fingerprint(event)})
            reopened = Store(path)
            _, high = reopened.delivery_boundary()
            rows = reopened.replay(0, high)
            self.assertEqual([r['event_id'] for r in rows], [notice['event_id'], critical['event_id']])
            reopened.insert({**critical, '_request_fingerprint': fingerprint(critical)})
            self.assertEqual(len(reopened.replay(0, high)), 2)
            with self.assertRaises(Conflict):
                reopened.lookup(critical['event_id'], fingerprint({**critical, 'confidence': .1}))
            reopened.offer('fixture-phone', notice['event_id'])
            reopened.acknowledge('fixture-phone', notice['event_id'], rows[0]['sequence'], 'ack_user_confirmed')
            delivery = reopened.offer('fixture-phone', critical['event_id'])
            reopened.acknowledge('fixture-phone', critical['event_id'], rows[1]['sequence'], 'ack_presented')
            delivery = reopened.offer('fixture-phone', critical['event_id'])
            self.assertIsNone(delivery['user_confirmed_at'])
            self.assertTrue(replay_eligible(rows[1], delivery, datetime.now(timezone.utc)))
            self.assertEqual(reopened.recovery_cursor('fixture-phone', high, datetime.now(timezone.utc)), rows[1]['sequence'] - 1)


if __name__ == '__main__':
    unittest.main()
