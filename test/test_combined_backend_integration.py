"""Combined Pi reliability and Windows TEST-control contract over real ASGI.

Hardware/ML imports are stubbed by the existing backend fixture; all credentials,
SQLite, IPC, clocks and alerts are synthetic. No lifespan or external server runs.
"""
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from test import test_resident_control as resident
from raspberry_pi.resident_control import ControlPlane, KwsMuteGate, Settings


@unittest.skipIf(resident.TestClient is None, 'optional ASGI test dependencies unavailable')
class CombinedBackendIntegrationTest(unittest.TestCase):
    setUp = resident.ResidentRoutesTests.setUp

    def control(self, body, headers=None):
        return self.client.post('/api/resident/control', headers=self.headers if headers is None else headers, json=body)

    @property
    def main(self):
        return {'Authorization': 'Bearer fixture-only-main-token'}

    def connect(self):
        response = self.control({'action': 'connect'})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['session_id']

    def body(self, session, action, sequence=1, **fields):
        return dict(session_id=session, action=action, sequence=sequence,
                    command_id='fixture-command-' + str(sequence), **fields)

    def muting(self):
        self.now = 100.0
        root = Path(self.tmp.name).resolve()
        root.chmod(0o700)
        settings = Settings(test_mode=True, mute_enabled=True, max_seconds=3,
                            directory=root, credentials=self.module.resident_controls.settings.credentials)
        self.module.resident_controls = ControlPlane(settings, clock=lambda: self.now)
        gate = KwsMuteGate(settings, clock=lambda: self.now)
        gate.poll()
        return gate

    def test_main_resident_and_caregiver_secrets_cannot_cross_roles(self):
        for headers in ({}, self.main, {'Authorization': 'Bearer wrong', 'X-Resident-Id': 'phone2'},
                        {'Authorization': 'Bearer ' + self.token, 'X-Resident-Id': 'unknown'}):
            self.assertEqual(self.control({'action': 'connect'}, headers).status_code, 401)
        self.connect()
        for method, path in [('post', '/api/alerts/manual'), ('post', '/api/alerts'),
                             ('get', '/api/resident/main'), ('get', '/api/alerts'), ('get', '/api/audio/status')]:
            response = getattr(self.client, method)(path, headers=self.headers,
                       **({'json': {'keyword': 'help'}} if method == 'post' else {}))
            self.assertEqual(response.status_code, 401, path)
        self.assertEqual(self.client.get('/api/resident/main', headers=self.main).status_code, 200)
        self.assertEqual(self.module.alert_store.list_recent(), [])

    def test_keyword_and_full_tests_have_explicit_identity_ack_and_no_real_rows(self):
        session = self.connect()
        identities = []
        for sequence, action in enumerate(('keyword_test', 'full_test'), 1):
            body = self.body(session, action, sequence)
            first = self.control(body)
            duplicate = self.control(body)
            self.assertEqual(first.status_code, 200, first.text)
            event = first.json()
            self.assertEqual(event['event_id'], duplicate.json()['event_id'])
            self.assertTrue(event['event_id'].startswith('test-'))
            self.assertTrue(event['is_test'])
            self.assertEqual(event['source'], 'resident_test')
            self.assertEqual(event['kind'], action)
            self.assertEqual(event['delivery'], 'backend_accepted')
            identities.append(event['event_id'])
            for disposition in ('presented', 'user_acknowledged'):
                ack = self.client.post('/api/resident/main', headers=self.main,
                           json=dict(event_id=event['event_id'], disposition=disposition))
                self.assertEqual(ack.status_code, 200, ack.text)
        state = self.control(dict(action='heartbeat', session_id=session)).json()
        self.assertEqual([e['event_id'] for e in state['events']], identities)
        self.assertEqual([e['delivery'] for e in state['events']], ['user_acknowledged'] * 2)
        self.assertEqual(self.module.alert_store.list_recent(), [])
        self.assertEqual(self.module.alert_store.delivery_boundary()[1], 0)

    def test_command_conflicts_reordering_and_old_session_have_no_effect(self):
        session = self.connect()
        accepted = self.body(session, 'full_test', 2)
        self.assertEqual(self.control(accepted).status_code, 200)
        for body in (self.body(session, 'keyword_test', 1), dict(accepted, action='keyword_test')):
            self.assertEqual(self.control(body).status_code, 409)
        replacement = self.connect()
        self.assertNotEqual(replacement, session)
        self.assertEqual(self.control(self.body(session, 'full_test', 3)).status_code, 409)
        self.assertEqual(len(self.module.resident_controls.events), 1)
        self.assertEqual(self.module.alert_store.list_recent(), [])

    def test_disabled_or_invalid_gate_never_changes_recognition(self):
        session = self.connect()
        self.assertFalse(self.module.resident_controls.snapshot()['remote_mute_available'])
        self.assertEqual(self.control(self.body(session, 'mute_start')).status_code, 409)
        self.module.resident_controls = ControlPlane(Settings())
        self.assertEqual(self.control({'action': 'connect'}).status_code, 401)
        self.assertEqual(self.client.get('/api/resident/main', headers=self.main).status_code, 404)
        self.assertEqual(self.module.alert_store.list_recent(), [])

    def test_malformed_control_bodies_are_bounded_and_rejected(self):
        for content, expected in [('[]', 400), ('{bad', 400), ('x' * 4097, 413),
                                  ('{"nested":' + '[' * 1100 + '0' + ']' * 1100 + '}', 400)]:
            response = self.client.post('/api/resident/control', headers=self.headers, content=content)
            self.assertEqual(response.status_code, expected)
        self.assertEqual(self.module.resident_controls.events, [])

    def test_mute_ack_release_disconnect_and_expiry_use_worker_state(self):
        gate = self.muting()
        session = self.connect()
        body = self.body(session, 'mute_start')
        first = self.control(body).json()
        self.assertFalse(first['remote_microphone_muted'])
        self.assertTrue(gate.poll())
        duplicate = self.control(body).json()
        self.assertEqual(duplicate['lease_id'], first['lease_id'])
        self.assertTrue(duplicate['remote_microphone_muted'])
        self.assertEqual(self.control(self.body(session, 'mute_renew', 2, lease_id='foreign')).status_code, 409)
        self.assertEqual(self.control(self.body(session, 'mute_end', 3, lease_id=first['lease_id'])).status_code, 200)
        self.assertFalse(gate.poll())
        self.assertEqual(self.control(self.body(session, 'mute_renew', 4, lease_id=first['lease_id'])).status_code, 409)
        second = self.control(self.body(session, 'mute_start', 5)).json()
        self.assertTrue(gate.poll())
        self.assertNotEqual(second['lease_id'], first['lease_id'])
        self.now += 3.01  # Fixture-only bound; no backend/Resident request triggers release.
        self.assertFalse(gate.poll())
        self.assertEqual(self.control(self.body(session, 'mute_renew', 6, lease_id=second['lease_id'])).status_code, 409)
        gate.poll()
        self.assertEqual(self.control(self.body(session, 'mute_start', 7)).status_code, 200)
        self.assertTrue(gate.poll())
        self.assertEqual(self.control(self.body(session, 'disconnect', 8)).status_code, 200)
        self.assertFalse(gate.poll())

    def test_restart_clears_test_sessions_and_does_not_restore_mute(self):
        gate = self.muting()
        session = self.connect()
        lease = self.control(self.body(session, 'mute_start')).json()['lease_id']
        self.control(self.body(session, 'full_test', 2))
        self.assertTrue(gate.poll())
        settings = self.module.resident_controls.settings
        restarted_worker = KwsMuteGate(settings, clock=lambda: self.now)
        self.assertFalse(restarted_worker.poll())
        old_boot = self.module.resident_controls.boot
        self.module.resident_controls = ControlPlane(settings, clock=lambda: self.now)
        self.assertNotEqual(self.module.resident_controls.boot, old_boot)
        self.assertEqual(self.module.resident_controls.events, [])
        self.assertFalse(gate.poll())
        self.assertEqual(self.control(self.body(session, 'mute_renew', 3, lease_id=lease)).status_code, 409)

    def test_genuine_critical_retains_durability_and_independent_replay_while_muted(self):
        gate = self.muting()
        session = self.connect()
        self.control(self.body(session, 'mute_start'))
        self.assertTrue(gate.poll())
        self.control(self.body(session, 'full_test', 2))
        with self.client.websocket_connect('/ws/thermal', headers=self.main) as thermal:
            self.assertIn('timestamp', thermal.receive_json())
        real = dict(event_id='fixture-real-critical', keyword='manual', confidence=1, source='manual_button')
        first = self.client.post('/api/alerts', headers=self.main, json=real)
        again = self.client.post('/api/alerts', headers=self.main, json=real)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()['event']['decision_state'], 'critical')
        self.assertTrue(again.json()['duplicate_event'])
        self.assertEqual(len(self.module.alert_store.list_recent()), 1)
        # Restart both durable store and in-memory idempotency cache, then retry.
        self.module.alert_store = type(self.module.alert_store)(self.module.alert_store.path)
        self.module.alert_idempotency = self.module.AlertIdempotencyRegistry(ttl_seconds=60, max_entries=32)
        self.assertTrue(self.client.post('/api/alerts', headers=self.main, json=real).json()['duplicate_event'])
        secret = 'fixture-caregiver-secret-for-both-phones'
        credentials = Path(self.tmp.name) / 'caregiver-fixture.json'
        credentials.write_text(json.dumps({i: hashlib.sha256(secret.encode()).hexdigest() for i in ('a', 'b')}))
        with patch.dict(os.environ, PROJECT_PI_CAREGIVER_CREDENTIALS=str(credentials)):
            for identity, confirmation in [('a', True), ('b', False)]:
                with self.client.websocket_connect('/ws/alerts?protocol=2') as ws:
                    ws.send_json(dict(protocol_version=2, type='authenticate', installation_id=identity, token=secret))
                    connected = ws.receive_json()
                    ws.send_json(dict(protocol_version=2, type='replay_request', cursor=0, instance=connected['instance']))
                    delivered = ws.receive_json()
                    self.assertEqual(delivered['event_id'], real['event_id'])
                    self.assertTrue(delivered['present'])
                    self.assertEqual(ws.receive_json()['type'], 'replay_complete')
                    if confirmation:
                        ws.send_json(dict(protocol_version=2, type='ack_user_confirmed',
                                          event_id=real['event_id'], sequence=delivered['sequence']))
                        self.assertEqual(ws.receive_json()['type'], 'ack_committed')
        self.assertIsNone(self.module.alert_store.offer('b', real['event_id'])['user_confirmed_at'])
        self.assertEqual(len(self.module.alert_store.list_recent()), 1)
        self.assertTrue(gate.poll())
