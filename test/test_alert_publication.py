import ast
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import unittest
from typing import Any


class AlertPublicationTest(unittest.TestCase):
    def test_no_subscribers_and_overflow_outcomes(self):
        # Execute the actual hub without initializing production hardware or DB.
        source = Path(__file__).resolve().parents[1] / 'raspberry_pi/backend/main.py'
        node = next(n for n in ast.parse(source.read_text(encoding='utf-8')).body
                    if isinstance(n, ast.ClassDef) and n.name == 'AlertHub')
        records = []
        namespace = dict(asyncio=asyncio, datetime=datetime, timezone=timezone, Any=Any,
                         trace_alert=lambda *args, **kwargs: records.append((args, kwargs)))
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), namespace)

        async def scenario():
            hub = namespace['AlertHub']()
            await hub.publish({'event_id': 'none'})
            self.assertEqual(records[-1][0][2], 'no_subscribers')
            queue = asyncio.Queue(maxsize=1)
            queue.put_nowait({'event_id': 'old'})
            hub.clients.add(queue)
            await hub.publish({'event_id': 'new'})
            self.assertEqual(records[-1][1]['enqueued'], 1)
            self.assertEqual(records[-1][1]['overflow_drops'], 1)
            self.assertEqual(records[-1][1]['failed_enqueues'], 0)
            self.assertEqual(queue.get_nowait()['event_id'], 'new')
            self.assertTrue(any(args == ('queue_drop', 'old', 'dropped') for args, _ in records))
        asyncio.run(scenario())
