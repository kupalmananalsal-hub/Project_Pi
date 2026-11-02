"""C1.58 cancellation tests execute actual extracted API/registry and synthetic stores."""
import asyncio
from pathlib import Path
import tempfile
import types
import unittest
from test import test_runtime_safety_blockers as fixtures

ROOT = Path(__file__).resolve().parents[1]


class RequestCancellationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='C1_58_cancel_', dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.ns = fixtures.backend_namespace(Path(self.temp.name)/'synthetic.db')
        payload = dict(fixtures.voice(.4), event_id='cancel-test', timestamp=fixtures.datetime.now(fixtures.timezone.utc).isoformat())
        self.event = types.SimpleNamespace(model_dump=lambda: dict(payload))

    def install_gate(self, phase):
        entered, release = asyncio.Event(), asyncio.Event()
        blocked = False
        async def to_thread(fn, *args, **kw):
            nonlocal blocked
            name = fn.__name__
            gate = not blocked and ((phase == 'thermal' and name == 'latest') or (phase in ('insert', 'after_commit') and name == 'insert'))
            if gate:
                blocked = True
                if phase == 'after_commit':
                    result = fn(*args, **kw)
                entered.set()
                await release.wait()
                if phase == 'after_commit': return result
            return fn(*args, **kw)
        proxy = types.SimpleNamespace(**{n:getattr(asyncio,n) for n in ('Lock','get_running_loop','Future','shield','CancelledError')}, to_thread=to_thread)
        self.ns['asyncio'] = proxy
        if phase == 'publish':
            original = self.ns['alerts'].publish
            async def publish(event):
                entered.set()
                await release.wait()
                await original(event)
            self.ns['alerts'].publish = publish
        return entered, release

    def test_cancelled_owner_releases_claim_before_persistence(self):
        async def run():
            entered, release = self.install_gate('thermal')
            owner = asyncio.create_task(self.ns['api_alerts'](self.event))
            await entered.wait(); owner.cancel()
            with self.assertRaises(asyncio.CancelledError): await owner
            self.assertEqual(self.ns['alert_idempotency'].in_flight_size(), 0)
            release.set()
            result = await self.ns['api_alerts'](self.event)
            self.assertFalse(result['duplicate_event'])
            self.assertEqual(len(self.ns['alert_store'].list_recent()), 1)
        asyncio.run(run())

    def test_cancelled_duplicate_does_not_cancel_shared_result(self):
        async def run():
            entered, release = self.install_gate('thermal')
            owner = asyncio.create_task(self.ns['api_alerts'](self.event))
            await entered.wait()
            registry = self.ns['alert_idempotency']
            original_claim = registry.claim
            joined = asyncio.Event(); count = 0
            async def claim(*a):
                nonlocal count
                result = await original_claim(*a);count += 1
                if count == 2: joined.set()
                return result
            registry.claim = claim
            one = asyncio.create_task(self.ns['api_alerts'](self.event))
            two = asyncio.create_task(self.ns['api_alerts'](self.event))
            try:
                await joined.wait();one.cancel()
                with self.assertRaises(asyncio.CancelledError): await one
                shared = next(iter(registry._in_flight.values()))['future']
                self.assertFalse(shared.cancelled())
                release.set()
                first = await owner; duplicate = await two
                self.assertTrue(duplicate['duplicate_event'])
                self.assertFalse(first['event']['duplicate_event'])
                self.assertTrue(duplicate['event']['duplicate_event'])
                self.assertEqual(
                    {k:v for k,v in first['event'].items() if k != 'duplicate_event'},
                    {k:v for k,v in duplicate['event'].items() if k != 'duplicate_event'})
                self.assertEqual(len(self.ns['alerts'].events), 1)
                self.assertEqual(self.ns['thermal'].reads, 1)
            finally:
                release.set()
                for task in (owner, one, two):
                    if not task.done(): task.cancel()
                await asyncio.gather(owner, one, two, return_exceptions=True)
        asyncio.run(run())

    def test_owner_cancel_at_insert_or_after_commit_recovers_same_event_id(self):
        for phase in ('insert','after_commit','publish'):
            with self.subTest(phase=phase):
                # Fresh synthetic store per cancellation boundary.
                ns = fixtures.backend_namespace(Path(self.temp.name)/(phase+'.db'))
                self.ns = ns
                async def run():
                    entered, release = self.install_gate(phase)
                    owner = asyncio.create_task(ns['api_alerts'](self.event))
                    await entered.wait();owner.cancel()
                    with self.assertRaises(asyncio.CancelledError): await owner
                    self.assertEqual(ns['alert_idempotency'].in_flight_size(), 0)
                    release.set()
                    result = await ns['api_alerts'](self.event)
                    self.assertEqual(result['event']['event_id'], 'cancel-test')
                    self.assertEqual(len(ns['alert_store'].list_recent()), 1)
                    if phase != 'insert':
                        self.assertTrue(result['duplicate_event'])
                        self.assertEqual(ns['thermal'].reads, 1)
                    self.assertEqual(len(ns['alert_store'].replay(0, 100)), 1)
                asyncio.run(run())

    def test_cancelled_owner_wakes_joined_waiter_and_allows_retry(self):
        async def run():
            entered, release = self.install_gate('thermal')
            owner = asyncio.create_task(self.ns['api_alerts'](self.event))
            await entered.wait()
            registry = self.ns['alert_idempotency']
            original = registry.claim
            joined = asyncio.Event()
            async def claim(*args):
                result = await original(*args)
                joined.set()
                return result
            registry.claim = claim
            waiter = asyncio.create_task(self.ns['api_alerts'](self.event))
            await joined.wait(); owner.cancel()
            with self.assertRaises(asyncio.CancelledError): await owner
            with self.assertRaises(asyncio.CancelledError): await waiter
            self.assertEqual(registry.in_flight_size(), 0)
            release.set()
            result = await self.ns['api_alerts'](self.event)
            self.assertFalse(result['duplicate_event'])
        asyncio.run(run())

    def test_cancelled_threaded_insert_can_finish_after_same_id_retry(self):
        import threading
        async def run():
            loop = asyncio.get_running_loop()
            entered, completed = asyncio.Event(), asyncio.Event()
            release, lock = threading.Event(), threading.Lock()
            store = self.ns['alert_store']
            original = store.insert
            first = True
            def insert(payload):
                nonlocal first
                with lock:
                    hold = first
                    first = False
                if hold:
                    loop.call_soon_threadsafe(entered.set)
                    release.wait()
                try:
                    return original(payload)
                finally:
                    if hold: loop.call_soon_threadsafe(completed.set)
            store.insert = insert
            owner = asyncio.create_task(self.ns['api_alerts'](self.event))
            try:
                await entered.wait(); owner.cancel()
                with self.assertRaises(asyncio.CancelledError): await owner
                self.assertEqual(self.ns['alert_idempotency'].in_flight_size(), 0)
                retry = await self.ns['api_alerts'](self.event)
                self.assertFalse(retry['duplicate_event'])
            finally:
                release.set()
                await completed.wait()
            self.assertEqual(len(store.list_recent()), 1)
            self.assertEqual(len(self.ns['alerts'].events), 1)
        asyncio.run(run())

    def test_unchanged_thermal_and_same_id_replay_do_not_repeat_critical(self):
        async def run():
            self.ns['thermal'].state = 'positive'
            first = await self.ns['api_alerts'](self.event)
            self.assertEqual(first['event']['decision_state'], 'critical')
            for _ in range(3):
                retry = await self.ns['api_alerts'](self.event)
                self.assertTrue(retry['duplicate_event'])
                self.assertEqual(retry['event']['sequence'], first['event']['sequence'])
            self.assertEqual(self.ns['thermal'].reads, 1)
            self.assertEqual(len(self.ns['alert_store'].list_recent()), 1)
            self.assertEqual(len(self.ns['alerts'].events), 1)
        asyncio.run(run())
