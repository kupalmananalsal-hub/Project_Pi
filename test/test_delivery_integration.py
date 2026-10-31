"""Real ASGI HTTP/WebSocket tests; only hardware/ML imports are replaced.

Run with the optional dependencies in test/requirements-delivery.txt.
"""
import hashlib
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta

from test.test_backend_alert_smoke import load_backend_module, restore_modules

try:
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
except ImportError:
    TestClient = None


@unittest.skipIf(TestClient is None, "install test/requirements-delivery.txt for real ASGI integration")
class DeliveryIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.module, previous = load_backend_module(self.temp.name, real_http=True)
        self.addCleanup(restore_modules, previous)
        self.module.API_AUTH_MODE = "required"
        self.module.API_TOKEN = "integration-api-token"
        self.client = TestClient(self.module.app, headers={"Authorization": "Bearer integration-api-token"})
        self.addCleanup(self.client.close)
        self.secret = "integration-only-secret-" * 3
        path = Path(self.temp.name) / "credentials.json"
        path.write_text(json.dumps({phone: hashlib.sha256(self.secret.encode()).hexdigest() for phone in ("phone-a", "phone-b")}), encoding="utf-8")
        old = os.environ.get("PROJECT_PI_CAREGIVER_CREDENTIALS")
        os.environ["PROJECT_PI_CAREGIVER_CREDENTIALS"] = str(path)
        self.addCleanup(lambda: os.environ.pop("PROJECT_PI_CAREGIVER_CREDENTIALS", None) if old is None else os.environ.__setitem__("PROJECT_PI_CAREGIVER_CREDENTIALS", old))

    def post(self, identity):
        response = self.client.post("/api/alerts", json={"event_id": identity, "keyword": "help", "confidence": .99, "source": "manual_button"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def hello(self, ws, phone):
        ws.send_json(dict(protocol_version=2, type="authenticate", installation_id=phone, token=self.secret))
        connected = ws.receive_json()
        self.assertEqual(connected["type"], "connected")
        ws.send_json(dict(protocol_version=2, type="replay_request", cursor=0, instance=connected["instance"]))

    def test_required_mode_rejects_unauthenticated_clients_over_real_http(self):
        anonymous = TestClient(self.module.app)
        self.addCleanup(anonymous.close)
        for method, path in (("post", "/api/alerts"), ("delete", "/api/alerts"), ("get", "/api/status")):
            response = getattr(anonymous, method)(path, **({"json": {"keyword": "help"}} if method == "post" else {}))
            self.assertEqual(response.status_code, 401, path)
        with self.assertRaises(WebSocketDisconnect):
            with anonymous.websocket_connect("/ws/thermal") as ws:
                ws.receive_json()
        self.assertEqual(len(self.module.alert_store.list_recent()), 0)

    def test_required_mode_rejects_wrong_and_legacy_token_accepts_correct(self):
        for header in ("Bearer not-the-token-0123456789", "Bearer project-pi-local-token"):
            wrong = TestClient(self.module.app, headers={"Authorization": header})
            self.addCleanup(wrong.close)
            self.assertEqual(wrong.post("/api/alerts", json={"keyword": "help"}).status_code, 401)
            self.assertEqual(wrong.get("/api/alerts").status_code, 401)
            with self.assertRaises(WebSocketDisconnect):
                with wrong.websocket_connect("/ws/alerts") as ws:
                    ws.receive_json()
        self.assertEqual(self.client.get("/api/alerts").status_code, 200)
        with self.client.websocket_connect("/ws/thermal") as ws:
            self.assertIn("timestamp", ws.receive_json())

    def test_open_mode_legacy_client_compat_over_real_http(self):
        """Compatibility only: open mode has no authentication."""
        self.module.API_AUTH_MODE = "open"
        self.module.API_TOKEN = ""
        anonymous = TestClient(self.module.app)
        self.addCleanup(anonymous.close)
        # Request shapes the current app sends with an empty token field.
        response = anonymous.post("/api/alerts", json={"event_id": "no-token", "keyword": "help", "confidence": .99, "source": "manual_button"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(anonymous.get("/api/alerts").status_code, 200)
        with anonymous.websocket_connect("/ws/thermal") as ws:
            self.assertIn("timestamp", ws.receive_json())
        with anonymous.websocket_connect("/ws/alerts") as ws:
            self.assertEqual(ws.receive_json()["type"], "historical")
        # Request shape of the old APK on control routes: the former public token.
        old_apk = TestClient(self.module.app, headers={"Authorization": "Bearer project-pi-local-token"})
        self.addCleanup(old_apk.close)
        self.assertEqual(old_apk.post("/api/leds", json={"led": 0, "r": 0, "g": 0, "b": 0}).status_code, 200)
        # Caregiver protocol v2 keeps its own per-phone authentication in no-token mode.
        with anonymous.websocket_connect("/ws/alerts?protocol=2") as ws:
            self.hello(ws, "phone-a")
            self.assertEqual(ws.receive_json()["event_id"], "no-token")
        with anonymous.websocket_connect("/ws/alerts?protocol=2") as ws:
            ws.send_json(dict(protocol_version=2, type="authenticate", installation_id="phone-a", token="wrong"))
            with self.assertRaises(WebSocketDisconnect):
                ws.receive_json()

    def test_post_persist_ack_restart_and_two_phone_replay(self):
        first = self.post("integration-critical")["event"]
        with self.client.websocket_connect("/ws/alerts?protocol=2") as ws:
            self.hello(ws, "phone-a")
            alert = ws.receive_json()
            self.assertEqual(alert["event"], first)
            self.assertTrue(alert["present"])
            self.assertEqual(ws.receive_json()["type"], "replay_complete")
            for kind in ("ack_received", "ack_presented"):
                ws.send_json(dict(protocol_version=2, type=kind, event_id=first["event_id"], sequence=first["sequence"]))
                self.assertEqual(ws.receive_json()["type"], "ack_committed")
        # Recreate durable store and discard in-memory dedup registry, as on restart.
        self.module.alert_store = self.module.AlertStore(self.module.alert_store.path)
        self.module.alert_idempotency = self.module.AlertIdempotencyRegistry(ttl_seconds=60, max_entries=100)
        self.assertTrue(self.post("integration-critical")["duplicate_event"])
        self.assertEqual(len(self.module.alert_store.list_recent()), 1)
        for phone, present in [("phone-a", True), ("phone-b", True)]:
            with self.client.websocket_connect("/ws/alerts?protocol=2") as ws:
                self.hello(ws, phone)
                self.assertEqual(ws.receive_json()["present"], present)
                ws.receive_json()

    def test_multiple_missed_events_replayed_in_order(self):
        with self.client.websocket_connect("/ws/alerts?protocol=2") as ws:
            self.hello(ws, "phone-a")
            self.assertEqual(ws.receive_json()["type"], "replay_complete")
        for i in range(3):
            self.post(f"missed-{i}")
        with self.client.websocket_connect("/ws/alerts?protocol=2") as ws:
            self.hello(ws, "phone-a")
            events = [ws.receive_json() for _ in range(3)]
            self.assertEqual([e["event_id"] for e in events], [f"missed-{i}" for i in range(3)])
            self.assertEqual(ws.receive_json()["type"], "replay_complete")

    def test_bad_credentials_and_spoofed_ack_rejected(self):
        with self.client.websocket_connect("/ws/alerts?protocol=2") as ws:
            ws.send_json(dict(protocol_version=2, type="authenticate", installation_id="phone-a", token="wrong"))
            with self.assertRaises(WebSocketDisconnect):
                ws.receive_json()
        first = self.post("spoof-target")["event"]
        with self.client.websocket_connect("/ws/alerts?protocol=2") as ws:
            self.hello(ws, "phone-a")
            ws.receive_json()
            ws.receive_json()
            ws.send_json(dict(protocol_version=2, type="ack_received", caregiver_id="phone-b", event_id=first["event_id"], sequence=first["sequence"]))
            with self.assertRaises(WebSocketDisconnect):
                ws.receive_json()
        self.assertIsNone(self.module.alert_store.offer("phone-b", first["event_id"])["received_at"])

    def test_heartbeat_timeout_releases_connection_for_reconnect(self):
        self.module.delivery_sessions = self.module.DeliverySessions(heartbeat_interval=.02, heartbeat_timeout=.02)
        with self.client.websocket_connect("/ws/alerts?protocol=2") as ws:
            self.hello(ws, "phone-a")
            self.assertEqual(ws.receive_json()["type"], "replay_complete")
            self.assertEqual(ws.receive_json()["type"], "heartbeat")
            with self.assertRaises(WebSocketDisconnect):
                ws.receive_json()
        with self.client.websocket_connect("/ws/alerts?protocol=2") as ws:
            self.hello(ws, "phone-a")
            self.assertEqual(ws.receive_json()["type"], "replay_complete")

    def test_two_connected_caregivers_receive_live_and_ack_independently(self):
        with self.client.websocket_connect("/ws/alerts?protocol=2") as a:
            self.hello(a, "phone-a")
            a.receive_json()
            with self.client.websocket_connect("/ws/alerts?protocol=2") as b:
                self.hello(b, "phone-b")
                b.receive_json()
                event = self.post("two-live")["event"]
                for ws in (a, b):
                    alert = ws.receive_json()
                    self.assertEqual(alert["delivery_mode"], "live")
                    self.assertEqual(alert["event_id"], "two-live")
                    ws.receive_json()
                a.send_json(dict(protocol_version=2, type="ack_received", event_id="two-live", sequence=event["sequence"]))
                self.assertEqual(a.receive_json()["type"], "ack_committed")
                self.assertIsNone(self.module.alert_store.offer("phone-b", "two-live")["received_at"])

    def test_queue_overflow_retains_all_events_for_bounded_replay(self):
        queue = asyncio.run(self.module.alerts.connect())
        try:
            for i in range(105):
                self.post(f"overflow-{i}")
            self.assertEqual(queue.qsize(), 100)
        finally:
            self.module.alerts.disconnect(queue)
        with self.client.websocket_connect("/ws/alerts?protocol=2") as ws:
            self.hello(ws, "phone-a")
            first = [ws.receive_json() for _ in range(100)]
            boundary = ws.receive_json()
            self.assertTrue(boundary["more"])
            ws.send_json(dict(protocol_version=2, type="replay_request", cursor=boundary["cursor"], instance=boundary["instance"]))
            last = [ws.receive_json() for _ in range(5)]
            self.assertFalse(ws.receive_json()["more"])
            self.assertEqual([e["event_id"] for e in first + last], [f"overflow-{i}" for i in range(105)])

    def test_controlled_restart_window_and_independent_confirmation(self):
        event = self.post('restart-window')['event']
        instant = datetime.fromisoformat(event['persisted_at'])
        self.module.delivery_sessions.clock = lambda: instant + timedelta(seconds=120)
        for phone in ('phone-a', 'phone-b'):
            self.module.alert_store.offer(phone, event['event_id'])
            self.module.alert_store.acknowledge(phone, event['event_id'], event['sequence'], 'ack_presented')
        self.module.alert_store.acknowledge('phone-a', event['event_id'], event['sequence'], 'ack_user_confirmed')
        for phone, expected in [('phone-a', False), ('phone-b', True)]:
            with self.client.websocket_connect('/ws/alerts?protocol=2') as ws:
                self.hello(ws, phone)
                self.assertEqual(ws.receive_json()['present'], expected)
                ws.receive_json()
        self.module.delivery_sessions.clock = lambda: instant + timedelta(seconds=301)
        with self.client.websocket_connect('/ws/alerts?protocol=2') as ws:
            self.hello(ws, 'phone-b')
            self.assertFalse(ws.receive_json()['present'])
            ws.receive_json()

    def test_reconnecting_phone_supersedes_stale_session(self):
        event = self.post('bad-ack')['event']
        with self.client.websocket_connect('/ws/alerts?protocol=2') as stale:
            self.hello(stale, 'phone-a'); stale.receive_json(); stale.receive_json()
            with self.client.websocket_connect('/ws/alerts?protocol=2') as fresh:
                self.hello(fresh, 'phone-a')
                self.assertEqual(fresh.receive_json()['event_id'], 'bad-ack')
                fresh.receive_json()
                with self.assertRaises(WebSocketDisconnect) as closed:
                    stale.receive_json()
                self.assertEqual(closed.exception.code, 4000)
                fresh.send_json(dict(protocol_version=2, type='ack_received', event_id=event['event_id'], sequence=True))
                with self.assertRaises(WebSocketDisconnect): fresh.receive_json()
        self.assertIsNone(self.module.alert_store.offer('phone-a', event['event_id'])['received_at'])

    def test_interrupted_server_ack_commit_recovers_on_retry(self):
        event = self.post('ack-interrupted')['event']
        original = self.module.alert_store.acknowledge
        def fail(*args):
            raise OSError('injected_storage_failure')
        self.module.alert_store.acknowledge = fail
        with self.client.websocket_connect('/ws/alerts?protocol=2') as ws:
            self.hello(ws, 'phone-a'); ws.receive_json(); ws.receive_json()
            ws.send_json(dict(protocol_version=2, type='ack_received', event_id=event['event_id'], sequence=event['sequence']))
            with self.assertRaises(WebSocketDisconnect): ws.receive_json()
        self.assertIsNone(self.module.alert_store.offer('phone-a', event['event_id'])['received_at'])
        self.module.alert_store.acknowledge = original
        with self.client.websocket_connect('/ws/alerts?protocol=2') as ws:
            self.hello(ws, 'phone-a'); ws.receive_json(); ws.receive_json()
            ws.send_json(dict(protocol_version=2, type='ack_received', event_id=event['event_id'], sequence=event['sequence']))
            self.assertEqual(ws.receive_json()['type'], 'ack_committed')

    def test_storage_and_registry_restart_while_live_session_receives_traffic(self):
        with self.client.websocket_connect('/ws/alerts?protocol=2') as ws:
            self.hello(ws, 'phone-a'); ws.receive_json()
            for i in range(6):
                if i == 3:
                    self.module.alert_store = self.module.AlertStore(self.module.alert_store.path)
                    self.module.alert_idempotency = self.module.AlertIdempotencyRegistry(ttl_seconds=60, max_entries=100)
                event = self.post(f'active-restart-{i}')['event']
                received = ws.receive_json()
                self.assertEqual(received['event_id'], event['event_id'])
                self.assertEqual(received['sequence'], i + 1)
                ws.receive_json()
                ws.send_json(dict(protocol_version=2, type='ack_received', event_id=event['event_id'], sequence=event['sequence']))
                self.assertEqual(ws.receive_json()['type'], 'ack_committed')
            self.assertTrue(self.post('active-restart-0')['duplicate_event'])
