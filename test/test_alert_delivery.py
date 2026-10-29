import ast
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "raspberry_pi"))
from alert_delivery import decode_control, replay_eligible


class Conflict(Exception):
    def __init__(self, **kwargs):
        self.status_code = kwargs.get("status_code")


def store_class():
    tree = ast.parse((ROOT / "raspberry_pi/backend/main.py").read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AlertStore")
    namespace = dict(globals(), HTTPException=Conflict, _as_float=lambda v, d: float(v or d))
    exec(compile(ast.Module(body=[node], type_ignores=[]), "AlertStore", "exec"), namespace)
    return namespace["AlertStore"]


class DeliveryStorageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "alerts.db"
        self.Store = store_class()
        self.store = self.Store(self.path)

    def event(self, identity="event-one"):
        return dict(event_id=identity, keyword="help", confidence=.99,
                    timestamp="2026-10-30T00:00:00Z", decision_state="critical",
                    thermal_state="negative", decision_reason="voice_critical",
                    decision_factors={"test": [1, 2]}, _request_fingerprint="original")

    def test_restart_retains_full_envelope_and_uuid(self):
        event = self.store.insert(self.event())
        restarted = self.Store(self.path)
        self.assertEqual(restarted.lookup("event-one", "original"), event)
        self.assertEqual(restarted.list_recent()[0], event)
        self.assertEqual(restarted.delivery_boundary(), self.store.delivery_boundary())

    def test_concurrent_duplicate_and_conflicting_uuid(self):
        def insert(_):
            return self.Store(self.path).insert(self.event())
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(insert, range(8)))
        self.assertEqual(len(self.store.list_recent()), 1)
        self.assertEqual(sum(not r.get("duplicate_event", False) for r in results), 1)
        with self.assertRaises(Conflict):
            self.store.insert(dict(self.event(), _request_fingerprint="changed"))

    def test_additive_legacy_migration_preserves_rows(self):
        path = Path(self.temp.name) / "legacy.db"
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE alerts(id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp TEXT NOT NULL,keyword TEXT NOT NULL,confidence REAL NOT NULL,direction TEXT,human_detected INTEGER,source TEXT)")
            db.execute("INSERT INTO alerts VALUES(8,'old','help',0.9,'left',1,'legacy')")
        db.close()
        store = self.Store(path)
        self.assertEqual(store.list_recent()[0]["id"], 8)
        self.assertNotIn("event_id", store.list_recent()[0])
        self.assertEqual(store.insert(self.event())["sequence"], 9)
        self.assertEqual(len(store.replay(0, 9)), 1)

    def test_independent_acks_survive_restart(self):
        event = self.store.insert(self.event())
        for phone in ("a", "b"):
            self.store.offer(phone, event["event_id"])
        self.store.acknowledge("a", event["event_id"], event["sequence"], "ack_received")
        self.store.acknowledge("a", event["event_id"], event["sequence"], "ack_presented")
        restarted = self.Store(self.path)
        first = restarted.offer("a", event["event_id"])
        self.assertIsNotNone(first["presented_at"])
        self.assertIsNone(restarted.offer("b", event["event_id"])["received_at"])
        restarted.acknowledge("a", event["event_id"], event["sequence"], "ack_presented")
        self.assertEqual(first, restarted.offer("a", event["event_id"]))

    def test_unoffered_wrong_sequence_unknown_ack_rejected(self):
        event = self.store.insert(self.event())
        for kind, sequence in [("ack_received", event["sequence"]), ("ack_received", 999), ("made_up", 1)]:
            with self.assertRaises(ValueError):
                self.store.acknowledge("stranger", event["event_id"], sequence, kind)

    def test_disconnected_and_queue_overflow_recover_all_rows(self):
        for i in range(205):
            self.store.insert(self.event(str(i)))
        # No hub/subscriber is needed for durable recovery; page through all records.
        recovered = []
        cursor = 0
        while page := self.store.replay(cursor, 205):
            self.assertLessEqual(len(page), 100)
            recovered.extend(page)
            cursor = page[-1]["sequence"]
        self.assertEqual([e["event_id"] for e in recovered], [str(i) for i in range(205)])

    def test_replay_policy_boundaries(self):
        now = datetime.now(timezone.utc)
        for age, eligible in [(0, True), (300, True), (301, False), (-1, False)]:
            event = dict(self.event(), persisted_at=(now - timedelta(seconds=age)).isoformat())
            self.assertEqual(replay_eligible(event, {}, now), eligible)
            self.assertFalse(replay_eligible(event, {"presented_at": "yes"}, now))
            self.assertFalse(replay_eligible(event, {"user_confirmed_at": "yes"}, now))
            self.assertFalse(replay_eligible(dict(event, decision_state="advisory"), {}, now))

    def test_invalid_protocol_payloads(self):
        for raw in ['[]', '{}', 'invalid', 'x' * 16385, '{"protocol_version":1}']:
            with self.assertRaises((ValueError, TypeError)):
                decode_control(raw)

    def test_backup_includes_wal_and_refuses_overwrite(self):
        original = self.store.insert(self.event())
        backup = Path(self.temp.name) / "backup.db"
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("UPDATE alerts SET keyword='wal-marker'")
            connection.commit()
            command = [sys.executable, str(ROOT / "raspberry_pi/scripts/backup_alerts.py"), str(self.path), str(backup)]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            restored = sqlite3.connect(backup)
            try:
                self.assertEqual(restored.execute("SELECT keyword FROM alerts").fetchone()[0], "wal-marker")
                self.assertEqual(json.loads(restored.execute("SELECT envelope_json FROM alerts").fetchone()[0]), original)
            finally:
                restored.close()
            self.assertNotEqual(subprocess.run(command, capture_output=True, timeout=10).returncode, 0)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
