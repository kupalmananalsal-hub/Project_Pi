"""C1.46 TEST-ONLY structured observations; never imported by application code.

No confirmation timer, recognition threshold, emergency policy, model or I/O.
This preserves evidence; it does not decide whether a partial warrants a siren.
"""
import json


def read_hypothesis_result(recognizer, data):
    final = bool(recognizer.AcceptWaveform(data))
    raw = recognizer.Result() if final else recognizer.PartialResult()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("ASR result must be an object")
    text = payload.get("text" if final else "partial", "")
    if not isinstance(text, str):
        raise ValueError("ASR text must be a string")
    return {"kind":"final" if final else "partial", "text":text.lower().strip(),
            "payload":payload, "raw_json":raw}


class HypothesisReference:
    """In-memory evidence ledger only; no emergency event or cancellation output.

    Caller supplies session/utterance identities and validated association verdicts.
    These are explicit fixture contracts, not acoustic segmentation/timeout rules.
    All exports are copies. Immutable observations and mutable candidate views have
    separate identities; no observation is a legacy backend alert envelope.
    """

    def __init__(self, matcher):
        self.matcher = matcher
        self._records = {}
        self._views = {}
        self._sequence = {}
        self._failed_sessions = set()
        self._health = {}
        self._session_continuous = {}

    def ingest(self, observation):
        encoded = json.dumps(observation, sort_keys=True, allow_nan=False)
        record = json.loads(encoded)
        for name in ("observation_id", "session", "utterance"):
            if not isinstance(record.get(name), str) or not record[name]:
                raise ValueError("nonempty observation/session/utterance identities required")
        if type(record.get("sequence")) is not int or record["sequence"] < 1:
            raise ValueError("positive integer sequence required")
        identity = record["observation_id"]
        if identity in self._records:
            if self._records[identity] != encoded:
                raise ValueError("observation identity reused with changed evidence")
            return json.loads(encoded)  # Retry cannot rewind the current candidate.
        result = record.get("result")
        if not isinstance(result, dict) or not isinstance(record.get("context"), dict):
            raise ValueError("structured result and full context required")
        kind = result.get("kind")
        if kind not in {"partial", "final", "silence", "gap", "failure"}:
            raise ValueError("unknown result kind")
        if kind in {"partial", "final"}:
            payload = json.loads(result["raw_json"])
            field = "text" if kind == "final" else "partial"
            if (not isinstance(payload, dict) or not isinstance(payload.get(field, ""), str)
                    or payload != result.get("payload")
                    or payload.get(field, "").lower().strip() != result.get("text")):
                raise ValueError("result kind/text/payload must preserve original ASR result")
        session = record["session"]
        key = (session, record["utterance"])
        sequence = record["sequence"]
        previous = self._sequence.get(session, 0)
        if sequence <= previous:
            raise ValueError("out-of-order observation requires reconciliation")
        if session in self._failed_sessions and kind in {"partial", "final"}:
            raise ValueError("new engine generation requires new session identity")
        old_view = self._views.get(key)
        if (old_view is not None and old_view["status"] == "final"
                and kind in {"partial", "final"}):
            raise ValueError("new hypothesis requires a new utterance identity")
        view = json.loads(json.dumps(old_view)) if old_view else {
            "candidate_id":"hypothesis:"+json.dumps(list(key), separators=(",", ":")),
            "observation_id":None, "keyword":None, "continuous":True}
        continuous = self._session_continuous.get(session, True) and sequence == previous + 1
        view["continuous"] = view["continuous"] and continuous
        view["latest_observation_id"] = identity
        if kind in {"partial", "final"}:
            view.update(observation_id=identity, keyword=self.matcher(result["text"]),
                        status="final" if kind == "final" else "provisional", health="ok")
        else:
            # Finality is a property of the ASR segment, independent of later health.
            if view.get("status") != "final":
                view["status"] = "failed" if kind == "failure" else "unknown"
            view["continuous"] = False
            continuous = False
        health = ("failed" if kind == "failure" or session in self._failed_sessions
                  else "ok" if kind in {"partial", "final"} else "unknown")
        # All validation/matching precedes mutation. Not a durable transaction implementation.
        self._records[identity] = encoded
        self._views[key] = view
        self._sequence[session] = sequence
        self._health[session] = health
        self._session_continuous[session] = continuous
        if kind == "failure":
            self._failed_sessions.add(session)
        return json.loads(encoded)

    def latest(self, key):
        view = self._views.get(key)
        if view is None:
            return None
        exported = json.loads(json.dumps(view))
        # Do not report old candidates as healthy/continuous after a session fault/gap.
        exported["health"] = self._health[key[0]]
        exported["continuous"] = exported["continuous"] and self._session_continuous[key[0]]
        return exported

    def journal(self):
        return [json.loads(record) for record in self._records.values()]

    def for_classification(self, key, *, association_valid):
        view = self.latest(key)
        if not association_valid or view is None or view["keyword"] is None:
            return None
        original = json.loads(self._records[view["observation_id"]])
        return {"candidate_id":view["candidate_id"], "keyword":view["keyword"],
                "provisional":original["result"]["kind"] == "partial",
                "health":view["health"], "continuous":view["continuous"],
                "observation":original}
