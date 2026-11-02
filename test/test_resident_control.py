"""Synthetic control-plane tests: no devices, audio, network or production files."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from raspberry_pi.resident_control import ControlPlane, MuteFiles, KwsMuteGate, Settings, RecognitionPoster


class ResidentControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.root.chmod(0o700)
        self.now = 100.0
        self.clock = lambda: self.now
        self.env = {'PROJECT_PI_RESIDENT_TEST_MODE': '1',
                    'PROJECT_PI_REMOTE_MUTE_ENABLED': '1',
                    'PROJECT_PI_REMOTE_MUTE_MAX_SECONDS': '3',
                    'PROJECT_PI_REMOTE_MUTE_DIR': str(self.root)}
        credentials = self.root / 'credentials.json'
        credentials.write_text(json.dumps({'fixture-resident': hashlib.sha256(b'fixture-resident-secret-not-production').hexdigest()}))
        credentials.chmod(0o600)
        self.env['PROJECT_PI_RESIDENT_CREDENTIALS'] = str(credentials)
        self.files = MuteFiles(self.root)
        self.gate = KwsMuteGate(Settings.from_env(self.env), clock=self.clock)
        self.plane = ControlPlane(Settings.from_env(self.env), clock=self.clock)
        self.session = self.plane.connect('fixture-resident')['session_id']
        self.seq = 0

    def command(self, action, **extra):
        self.seq += 1
        return self.plane.command('fixture-resident', dict(
            session_id=self.session, sequence=self.seq,
            command_id=f'fixture-{self.seq}', action=action, **extra))

    def test_configuration_has_no_duration_default_and_fails_closed(self):
        for value in (None, '', '0', '-1', 'nan', 'inf', 'wrong', 'true'):
            env = dict(self.env)
            if value is None:
                env.pop('PROJECT_PI_REMOTE_MUTE_MAX_SECONDS')
            else:
                env['PROJECT_PI_REMOTE_MUTE_MAX_SECONDS'] = value
            self.assertFalse(Settings.from_env(env).mute_enabled)
        self.assertFalse(Settings.from_env({}).mute_enabled)
        self.assertFalse(Settings.from_env(dict(self.env, WEB_CONCURRENCY='2')).test_mode)
        malformed = Settings.from_env(dict(self.env, PROJECT_PI_REMOTE_MUTE_DIR='\0'))
        self.assertFalse(KwsMuteGate(malformed).poll())
        self.assertFalse(ControlPlane(malformed).snapshot()['remote_mute_available'])

    def test_acquisition_requires_worker_ack_and_release_resumes(self):
        self.gate.poll()
        result = self.command('mute_start')
        self.assertFalse(result['remote_microphone_muted'])
        self.assertTrue(self.gate.poll())
        self.assertTrue(self.plane.snapshot()['remote_microphone_muted'])
        self.command('mute_end', lease_id=result['lease_id'])
        self.assertFalse(self.gate.poll())
        self.assertFalse(self.plane.snapshot()['remote_microphone_muted'])

    def test_expiry_is_enforced_without_backend_poll(self):
        self.gate.poll()
        self.command('mute_start')
        self.assertTrue(self.gate.poll())
        self.now += 3.01
        self.assertFalse(self.gate.poll())

    def test_renewal_and_stale_hold_rejected(self):
        self.gate.poll()
        result = self.command('mute_start')
        self.now += 1
        self.command('mute_renew', lease_id=result['lease_id'])
        self.now += 2.1
        self.assertTrue(self.gate.poll())
        self.now += 1
        with self.assertRaises(ValueError):
            self.command('mute_renew', lease_id=result['lease_id'])
        self.assertFalse(self.gate.poll())

    def test_reconnect_revokes_old_session_and_hold(self):
        self.gate.poll()
        result = self.command('mute_start')
        self.gate.poll()
        self.plane.connect('fixture-resident')
        self.assertFalse(self.gate.poll())
        with self.assertRaises(ValueError):
            self.command('mute_renew', lease_id=result['lease_id'])

    def test_backend_and_worker_restarts_do_not_restore_mute(self):
        self.gate.poll()
        self.command('mute_start')
        self.assertTrue(self.gate.poll())
        restarted = KwsMuteGate(Settings.from_env(self.env), clock=self.clock)
        self.assertFalse(restarted.poll())
        self.assertFalse(self.plane.snapshot()['remote_microphone_muted'])
        ControlPlane(Settings.from_env(self.env), clock=self.clock)
        self.assertFalse(self.gate.poll())

    def test_local_override_revokes_lease(self):
        self.gate.poll()
        self.command('mute_start')
        self.gate.poll()
        (self.root / 'remote-mute.disabled').touch()
        self.assertFalse(self.gate.poll())
        self.assertFalse(self.plane.snapshot()['remote_mute_available'])

    def test_duplicates_are_idempotent_and_out_of_order_rejected(self):
        body = dict(session_id=self.session, sequence=1, command_id='same', action='keyword_test')
        a = self.plane.command('fixture-resident', body)
        b = self.plane.command('fixture-resident', body)
        self.assertEqual(a['event_id'], b['event_id'])
        self.assertEqual(len(self.plane.snapshot()['events']), 1)
        with self.assertRaises(ValueError):
            self.plane.command('fixture-resident', dict(body, command_id='different'))
        with self.assertRaises(ValueError):
            self.plane.command('fixture-resident', dict(body, action='full_test'))

    def test_main_presentation_is_separate_from_acceptance(self):
        event = self.command('full_test')
        self.assertEqual(event['delivery'], 'backend_accepted')
        self.plane.present(event['event_id'], 'presented')
        self.assertEqual(self.plane.snapshot()['events'][0]['delivery'], 'presented')
        self.assertTrue(self.plane.snapshot()['events'][0]['is_test'])

    def test_disabled_mode_and_invalid_auth_fail_closed(self):
        self.assertFalse(self.plane.authenticate('unknown', 'secret'))
        disabled = ControlPlane(Settings.from_env({}), clock=self.clock)
        with self.assertRaises(ValueError):
            disabled.connect('any')
        self.assertTrue(self.plane.authenticate('fixture-resident', 'fixture-resident-secret-not-production'))
        self.gate.poll()
        (self.root / 'credentials.json').unlink()
        self.assertFalse(self.plane.snapshot()['remote_mute_available'])

    def test_unknown_or_unsafe_ipc_files_do_not_mute(self):
        (self.root / 'request.json').write_text('{bad json')
        self.assertFalse(self.gate.poll())
        outside = self.root / 'outside'
        outside.write_text('untouched')
        path = self.root / 'request.json'
        path.unlink()
        try:
            path.symlink_to(outside)
        except OSError:
            self.skipTest('symlink creation unavailable')
        self.assertFalse(self.gate.poll())
        self.assertEqual(outside.read_text(), 'untouched')

    def test_release_tombstone_blocks_delayed_start(self):
        self.gate.poll()
        lease = self.command('mute_start')['lease_id']
        self.command('mute_end', lease_id=lease)
        with self.assertRaises(ValueError):
            self.command('mute_renew', lease_id=lease)
        self.assertFalse(self.gate.poll())

    def test_old_candidate_cannot_publish_after_resume_but_outbox_is_untouched(self):
        from unittest.mock import Mock
        poster = Mock()
        fenced = RecognitionPoster(poster, self.gate)
        fenced.publish('help', .9, 'fixture', extra={})
        poster.publish.assert_not_called()
        fenced.publish('help', .9, 'fixture', extra={'recognition_epoch': 0})
        self.assertEqual(poster.publish.call_count, 1)
        self.gate.poll()
        lease = self.command('mute_start')['lease_id']
        self.gate.poll()
        fenced.publish('help', .9, 'fixture', extra={'recognition_epoch': 0})
        self.command('mute_end', lease_id=lease)
        self.gate.poll()
        fenced.publish('help', .9, 'fixture', extra={'recognition_epoch': 0})
        self.assertEqual(poster.publish.call_count, 1)
        fenced.publish('help', .9, 'fixture', extra={'recognition_epoch': self.gate.epoch})
        self.assertEqual(poster.publish.call_count, 2)
        poster.stop_worker.assert_not_called()

    def test_capture_boundary_drains_queues_before_acknowledging_mute(self):
        import queue
        from unittest.mock import Mock
        queues = [queue.Queue(), queue.Queue()]
        for fallback in queues:
            fallback.put({'recognition_epoch': 0})
        reset, cancel = Mock(), Mock()
        self.gate.poll()
        lease = self.command('mute_start')['lease_id']
        self.assertTrue(self.gate.capture_boundary(queues, reset, cancel))
        self.assertTrue(all(q.empty() for q in queues))
        self.assertEqual(reset.call_count, 1)
        self.assertEqual(cancel.call_count, 1)
        self.assertTrue(self.plane.snapshot()['remote_microphone_muted'])
        self.command('mute_end', lease_id=lease)
        self.assertTrue(self.gate.capture_boundary(queues, reset, cancel))
        self.assertFalse(self.gate.muted)
        self.assertEqual(reset.call_count, 2)
        self.assertFalse(self.gate.capture_boundary(queues, reset, cancel))

    def test_disconnect_and_missing_heartbeat_release_lease(self):
        self.gate.poll()
        self.command('mute_start')
        self.gate.poll()
        self.command('disconnect')
        self.assertFalse(self.gate.poll())
        with self.assertRaises(ValueError):
            self.command('mute_start')

    def test_main_presence_is_independent_and_expires(self):
        self.assertFalse(self.plane.snapshot()['main_connected'])
        self.plane.main_snapshot()
        self.assertTrue(self.plane.snapshot()['main_connected'])
        self.now += 5.01
        state = self.plane.snapshot()
        self.assertFalse(state['resident_connected'])
        self.assertFalse(state['main_connected'])


try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None


@unittest.skipIf(TestClient is None, 'optional ASGI test dependencies unavailable')
class ResidentRoutesTests(unittest.TestCase):
    def setUp(self):
        import json
        from test.test_backend_alert_smoke import load_backend_module, restore_modules
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.module, previous = load_backend_module(self.tmp.name, real_http=True)
        self.addCleanup(restore_modules, previous)
        self.module.API_AUTH_MODE = 'required'
        self.module.API_TOKEN = 'fixture-only-main-token'
        self.token = 'fixture-only-resident-secret-123456789'
        path = Path(self.tmp.name) / 'pairing.json'
        path.write_text(json.dumps({'phone2': hashlib.sha256(self.token.encode()).hexdigest()}))
        path.chmod(0o600)
        self.module.resident_controls = ControlPlane(Settings(test_mode=True, credentials=path))
        self.client = TestClient(self.module.app)
        self.addCleanup(self.client.close)
        self.headers = {'Authorization': 'Bearer ' + self.token, 'X-Resident-Id': 'phone2'}

    def test_scoped_auth_test_delivery_and_real_history_separation(self):
        self.assertEqual(self.client.post('/api/resident/control', json={'action': 'connect'}).status_code, 401)
        result = self.client.post('/api/resident/control', headers=self.headers, json={'action': 'connect'})
        self.assertEqual(result.status_code, 200)
        session = result.json()['session_id']
        body = dict(action='full_test', session_id=session, command_id='fixture-1', sequence=1)
        event = self.client.post('/api/resident/control', headers=self.headers, json=body).json()
        main = {'Authorization': 'Bearer fixture-only-main-token'}
        self.assertEqual(self.client.get('/api/resident/main', headers=self.headers).status_code, 401)
        state = self.client.get('/api/resident/main', headers=main).json()
        self.assertEqual(state['events'][0]['event_id'], event['event_id'])
        self.assertEqual(state['events'][0]['delivery'], 'backend_accepted')
        ack = self.client.post('/api/resident/main', headers=main,
            json=dict(event_id=event['event_id'], disposition='presented'))
        self.assertEqual(ack.status_code, 200)
        self.assertEqual(self.client.post('/api/resident/control', headers=self.headers,
            json=dict(action='heartbeat', session_id=session)).json()['events'][0]['delivery'], 'presented')
        self.assertEqual(len(self.module.alert_store.list_recent()), 0)
        self.assertEqual(self.client.post('/api/alerts/manual', headers=self.headers, json={}).status_code, 401)
        self.assertEqual(self.client.get('/api/audio/status', headers=main).status_code, 200)
        self.assertEqual(self.client.get('/api/status', headers=main).status_code, 200)

    def test_open_mode_never_exposes_test_controls(self):
        self.module.API_AUTH_MODE = 'open'
        self.module.OPEN_MODE_ACK = self.module.OPEN_MODE_ACK_VALUE
        self.assertEqual(self.client.post('/api/resident/control', headers=self.headers,
            json={'action': 'connect'}).status_code, 401)
        self.assertEqual(self.client.get('/api/resident/main').status_code, 401)

    def test_muting_acoustic_input_does_not_block_thermal_or_real_alert_delivery(self):
        root = Path(self.tmp.name).resolve()
        root.chmod(0o700)
        settings = Settings(test_mode=True, mute_enabled=True, max_seconds=3,
                            directory=root, credentials=self.module.resident_controls.settings.credentials)
        plane = self.module.resident_controls = ControlPlane(settings)
        gate = KwsMuteGate(settings)
        gate.poll()
        session = plane.connect('phone2')['session_id']
        plane.command('phone2', dict(action='mute_start', session_id=session,
            sequence=1, command_id='fixture-mute'))
        self.assertTrue(gate.poll())
        main = {'Authorization': 'Bearer fixture-only-main-token'}
        with self.client.websocket_connect('/ws/thermal', headers=main) as ws:
            self.assertIn('timestamp', ws.receive_json())
        response = self.client.post('/api/alerts', headers=main, json=dict(
            event_id='fixture-real-emergency', keyword='manual', confidence=1,
            source='manual_button'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['event']['decision_state'], 'critical')
        self.assertEqual(len(self.module.alert_store.list_recent()), 1)
        self.assertTrue(gate.poll())


if __name__ == '__main__':
    unittest.main()
