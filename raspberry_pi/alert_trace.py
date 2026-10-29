"""Small, bounded JSON-line diagnostics for the local alert pipeline."""

import json
from datetime import datetime, timezone


def trace_alert(stage, event_id, outcome, **details):
    record = {
        "kind": "alert_trace",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "event_id": str(event_id or "unknown"),
        "outcome": outcome,
    }
    record.update({key: value for key, value in details.items() if value is not None})
    print(json.dumps(record, ensure_ascii=False, default=str), flush=True)
