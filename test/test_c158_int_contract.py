"""Actual Pi auth/API/delivery code, synthetic SQLite and in-memory WebSockets.

These tests characterize the available Pi contract, not the unavailable Windows
commit or its unimplemented mute/test-command behavior. No backend startup runs.
"""
import ast
import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'raspberry_pi')]
import alert_delivery
from test import test_runtime_safety_blockers as fixtures
from test.test_alert_delivery import Conflict
from test.test_backend_alert_smoke import FakeBaseModel


def extract(names, namespace):
    tree = ast.parse((ROOT / 'raspberry_pi/backend/main.py').read_text())
    nodes = [n for n in tree.body if getattr(n, 'name', None) in names]
    assert len(nodes) == len(names)
    for node in nodes:
        node.decorator_list = []
    prefix = ast.parse('from __future__ import annotations').body
    exec(compile(ast.Module(body=prefix + nodes, type_ignores=[]), 'actual-pi-backend-contract', 'exec'), namespace)
    return namespace


def auth_namespace():
    tree = ast.parse((ROOT / 'raspberry_pi/backend/main.py').read_text())
    constants = {'API_AUTH_MODES', 'OPEN_MODE_ACK_VALUE', 'LEGACY_DEFAULT_API_TOKEN', 'MIN_API_TOKEN_LENGTH'}
    ns = dict(hmac=hmac, API_AUTH_MODE='required', API_TOKEN='offline-fixture-api-token', OPEN_MODE_ACK='')
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in node.targets):
            exec(compile(ast.Module(body=[node], type_ignores=[]), 'actual-auth-constants', 'exec'), ns)
    return extract({'api_auth_fault', 'effective_auth_mode', 'api_auth_enabled', 'api_token_valid',
                    'api_token_required', 'ApiTokenMiddleware'}, ns)


class AuthenticationContractTest(unittest.TestCase):
    def request(self, ns, path, token=None, kind='http', query=b'', method='POST'):
        messages, reached = [], []
        async def app(scope, receive, send):
            reached.append(True)
        async def send(message):
            messages.append(message)
        async def receive():
            return {}
        headers = [] if token is None else [(b'authorization', token.encode())]
        asyncio.run(ns['ApiTokenMiddleware'](app)(dict(type=kind, method=method,
                    path=path, query_string=query, headers=headers), receive, send))
        return messages, reached

    def test_manual_and_alert_routes_require_bearer_in_required_mode(self):
        ns = auth_namespace()
        for path in ('/api/alerts/manual', '/api/alerts'):
            for token in (None, 'Bearer wrong-token', 'Bearer project-pi-local-token', 'Basic offline-fixture-api-token'):
                with self.subTest(path=path, token=token):
                    messages, reached = self.request(ns, path, token)
                    self.assertEqual(messages[0]['status'], 401)
                    self.assertFalse(reached)
            self.assertTrue(self.request(ns, path, 'Bearer offline-fixture-api-token')[1])

    def test_missing_invalid_short_and_default_auth_fail_closed(self):
        ns = auth_namespace()
        for mode, token in [('', 'offline-fixture-api-token'), ('other', 'offline-fixture-api-token'),
                            ('required', ''), ('required', 'short'), ('required', 'project-pi-local-token'),
                            ('open', '')]:
            with self.subTest(mode=mode, token=token):
                ns.update(API_AUTH_MODE=mode, API_TOKEN=token, OPEN_MODE_ACK='')
                self.assertEqual(ns['effective_auth_mode'](), 'locked')
                self.assertEqual(self.request(ns, '/api/alerts/manual', 'Bearer ' + token)[0][0]['status'], 401)

    def test_protocol_two_bypasses_shared_token_only_when_backend_unlocked(self):
        ns = auth_namespace()
        self.assertTrue(self.request(ns, '/ws/alerts', kind='websocket', query=b'protocol=2')[1])
        self.assertEqual(self.request(ns, '/ws/alerts', kind='websocket')[0][0]['code'], 1008)
        self.assertEqual(self.request(ns, '/ws/thermal', kind='websocket', query=b'protocol=2')[0][0]['code'], 1008)
        ns['API_AUTH_MODE'] = ''
        self.assertEqual(self.request(ns, '/ws/alerts', kind='websocket', query=b'protocol=2')[0][0]['code'], 1008)

    def test_acknowledged_open_mode_is_an_explicit_unauthenticated_exception(self):
        ns = auth_namespace()
        ns.update(API_AUTH_MODE='open', OPEN_MODE_ACK=ns['OPEN_MODE_ACK_VALUE'])
        self.assertEqual(ns['effective_auth_mode'](), 'open')
        self.assertTrue(self.request(ns, '/api/alerts/manual')[1])

    def test_caregiver_verifiers_are_per_installation_and_fail_without_provisioning(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'fixture-credentials.json'
            path.write_text(json.dumps({'a': hashlib.sha256(b'fixture-secret-a').hexdigest(),
                                        'b': hashlib.sha256(b'fixture-secret-b').hexdigest()}))
            with patch.dict(os.environ, PROJECT_PI_CAREGIVER_CREDENTIALS=str(path)):
                self.assertTrue(alert_delivery.authenticate('a', 'fixture-secret-a'))
                self.assertFalse(alert_delivery.authenticate('b', 'fixture-secret-a'))
                self.assertFalse(alert_delivery.authenticate('unknown', 'fixture-secret-a'))
                self.assertFalse(alert_delivery.authenticate('a', 'wrong'))
            with patch.dict(os.environ):
                os.environ.pop('PROJECT_PI_CAREGIVER_CREDENTIALS', None)
                self.assertFalse(alert_delivery.authenticate('a', 'fixture-secret-a'))


class MemoryWebSocket:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.outgoing = asyncio.Queue()
    async def accept(self):
        pass
    async def receive_text(self):
        item = await self.incoming.get()
        if isinstance(item, Exception):
            raise item
        return json.dumps(item)
    async def send_json(self, message):
        await self.outgoing.put(message)
    async def close(self, code=1000, reason=''):
        await self.outgoing.put(dict(type='closed', code=code, reason=reason))
        await self.incoming.put(ConnectionError('synthetic disconnect'))
    def control(self, kind, **fields):
        self.incoming.put_nowait(dict(protocol_version=2, type=kind, **fields))
    async def next(self, kind):
        message = await asyncio.wait_for(self.outgoing.get(), 3)
        if message['type'] != kind:
            raise AssertionError((kind, message))
        return message


class PiProtocolContractTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ns = fixtures.backend_namespace(Path(self.temp.name) / 'synthetic.db')
        self.ns.update(BaseModel=FakeBaseModel)
        extract({'AlertIn', 'ManualAlertIn', 'api_alerts_manual'}, self.ns)
        self.store = self.ns['alert_store']
        self.sessions = alert_delivery.DeliverySessions(heartbeat_interval=60, heartbeat_timeout=60)
        credentials = Path(self.temp.name) / 'fixture-credentials.json'
        credentials.write_text(json.dumps({i: hashlib.sha256(b'fixture-phone-secret').hexdigest() for i in ('a', 'b')}))
        self.environment = patch.dict(os.environ, PROJECT_PI_CAREGIVER_CREDENTIALS=str(credentials))
        self.environment.start()
        self.tasks = []

    async def asyncTearDown(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.environment.stop()
        self.temp.cleanup()

    async def session(self, identity='a', token='fixture-phone-secret'):
        ws = MemoryWebSocket()
        task = asyncio.create_task(self.sessions.serve(ws, self.store))
        self.tasks.append(task)
        ws.control('authenticate', installation_id=identity, token=token)
        return ws, task

    async def replay(self, ws, connected):
        ws.control('replay_request', cursor=0, instance=connected['instance'])

    async def manual(self, identity):
        return await self.ns['api_alerts_manual'](self.ns['ManualAlertIn'](event_id=identity))

    async def test_unauthenticated_and_wrong_caregiver_messages_cannot_read_alerts(self):
        ws, task = await self.session(token='wrong')
        self.assertEqual((await ws.next('closed'))['reason'], 'authentication_failed')
        await task
        ws = MemoryWebSocket()
        task = asyncio.create_task(self.sessions.serve(ws, self.store))
        self.tasks.append(task)
        ws.control('replay_request', cursor=0, instance='invented')
        self.assertEqual((await ws.next('closed'))['reason'], 'authentication_failed')
        await task
        self.assertFalse(self.sessions.active)

    async def test_resident_manual_same_id_retries_create_one_real_critical_event(self):
        first = await self.manual('resident-same-id')
        again = await self.manual('resident-same-id')
        self.assertFalse(first['duplicate_event'])
        self.assertTrue(again['duplicate_event'])
        self.assertEqual(first['event']['decision_state'], 'critical')
        self.assertEqual(first['event']['decision_reason'], 'manual_button_emergency')
        self.assertEqual(len(self.store.list_recent()), 1)
        self.assertEqual(len(self.ns['alerts'].events), 1)
        with self.assertRaises(Conflict):
            await self.ns['api_alerts_manual'](self.ns['ManualAlertIn'](event_id='resident-same-id', keyword='changed'))

    async def test_new_manual_ids_remain_distinct_emergencies(self):
        await self.manual('manual-a')
        await self.manual('manual-b')
        self.assertEqual(len(self.store.list_recent()), 2)
        self.assertEqual(len(self.ns['alerts'].events), 2)

    async def test_replay_ack_and_restart_preserve_independent_emergency_recovery(self):
        response = await self.manual('retained-emergency')
        event = response['event']
        ws, task = await self.session()
        connected = await ws.next('connected')
        await self.replay(ws, connected)
        replayed = await ws.next('alert')
        self.assertEqual(replayed['event_id'], event['event_id'])
        self.assertTrue(replayed['present'])
        await ws.next('replay_complete')
        for _ in range(2):
            ws.control('ack_user_confirmed', event_id=event['event_id'], sequence=event['sequence'])
            await ws.next('ack_committed')
        ws.incoming.put_nowait(ConnectionError('disconnect after ACK'))
        await task
        self.assertFalse(self.sessions.active)
        self.store = type(self.store)(self.store.path)
        self.sessions = alert_delivery.DeliverySessions(heartbeat_interval=60, heartbeat_timeout=60)
        for identity, expected in [('a', False), ('b', True)]:
            fresh, _ = await self.session(identity)
            connected = await fresh.next('connected')
            await self.replay(fresh, connected)
            self.assertEqual((await fresh.next('alert'))['present'], expected)
            await fresh.next('replay_complete')

    async def test_spoofed_wrong_sequence_and_unknown_ack_close_session_without_confirmation(self):
        event = (await self.manual('ack-target'))['event']
        messages = [dict(type='ack_user_confirmed', event_id=event['event_id'], sequence=event['sequence'], caregiver_id='b'),
                    dict(type='ack_user_confirmed', event_id=event['event_id'], sequence=999),
                    dict(type='made_up_ack', event_id=event['event_id'], sequence=event['sequence'])]
        for message in messages:
            ws, task = await self.session()
            connected = await ws.next('connected')
            await self.replay(ws, connected)
            await ws.next('alert')
            await ws.next('replay_complete')
            ws.control(message['type'], **{k:v for k,v in message.items() if k != 'type'})
            self.assertEqual((await ws.next('closed'))['code'], 1008)
            await task
            self.assertIsNone(self.store.offer('a', event['event_id'])['user_confirmed_at'])

    async def test_reconnect_replaces_stale_session_and_disconnect_removes_owner(self):
        old, old_task = await self.session()
        await old.next('connected')
        new, new_task = await self.session()
        await new.next('connected')
        self.assertEqual((await old.next('closed'))['code'], 4000)
        await old_task
        self.assertIs(self.sessions.active['a'], new)
        new.incoming.put_nowait(ConnectionError('synthetic disconnect'))
        await new_task
        self.assertFalse(self.sessions.active)

    async def test_invalid_replay_instance_and_negative_cursor_are_rejected(self):
        for cursor, valid_instance in [(-1, True), (0, False), (True, True)]:
            ws, task = await self.session()
            connected = await ws.next('connected')
            ws.control('replay_request', cursor=cursor, instance=connected['instance'] if valid_instance else 'stale-instance')
            self.assertEqual((await ws.next('closed'))['code'], 1008)
            await task
