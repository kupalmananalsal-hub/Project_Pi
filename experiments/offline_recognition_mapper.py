"""Disconnected C1.54 harness for synthetic application-shaped engine metadata.

No SDK imports, engine invocation, audio, I/O, clocks, callbacks or alarm policy.
Context/identities and lifecycle events are supplied, never inferred. This is
neither an application adapter nor a durable/concurrent coordinator.
"""
import json
import math

from experiments.recognition_observation_contract import EvidenceLedger, canonical_identity, validate_observation


_META = frozenset({'observation_id', 'producer_id', 'generation_id', 'candidate_id',
                  'sequence', 'revision', 'observed_at', 'clock_domain', 'capture_range'})
_OWW = frozenset({'available', 'is_speech', 'scores', 'wake_words', 'vad_score', 'error'})


def _copy(value):
    return json.loads(canonical_identity(value))


def _label(value):
    if type(value) is not str or not value.strip():
        raise ValueError('nonempty string required')


def _number(value, *, normalized=False):
    if type(value) not in (float, int) or not math.isfinite(value):
        raise ValueError('finite numeric metadata required')
    if normalized and not 0 <= value <= 1:
        raise ValueError('normalized score outside contract domain')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('ambiguous duplicate JSON key')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('nonfinite JSON constant')


def _rows(rows):
    if type(rows) is not list:
        raise ValueError('application score metadata must be a list')
    indexed = {}
    for row in rows:
        if type(row) is not dict or not {'name', 'raw_name', 'threshold'} <= set(row):
            raise ValueError('incomplete application model metadata')
        _label(row['name']); _label(row['raw_name']); _number(row['threshold'])
        if row.get('score') is not None:
            _number(row['score'], normalized=True)
        if row['raw_name'] in indexed:
            raise ValueError('ambiguous repeated model metadata')
        indexed[row['raw_name']] = row
    return indexed


class OfflineRecognitionHarness:
    """Map fixtures into an isolated EvidenceLedger, never application dispatch.

    aliases is an ordered list of [keyword, aliases] rows. Its source is fixture
    data; copying it never imports the KWS application. It selects textual labels,
    not truth, calibrated confidence, finality or emergency authority.
    """
    def __init__(self, aliases):
        aliases = _copy(aliases)
        if type(aliases) is not list or not aliases:
            raise ValueError('explicit ordered vocabulary required')
        names = set()
        for row in aliases:
            if type(row) is not list or len(row) != 2:
                raise ValueError('keyword/alias rows required')
            _label(row[0])
            if row[0] in names or type(row[1]) is not list or not row[1]:
                raise ValueError('unique keywords and nonempty aliases required')
            for alias in row[1]:
                _label(alias)
            names.add(row[0])
        self._aliases = canonical_identity(aliases)
        self._ledger = EvidenceLedger()

    def begin_generation(self, engine, producer_id, generation_id):
        self._ledger.begin_generation(engine, producer_id, generation_id)

    def snapshot(self):
        return self._ledger.snapshot()

    def _match(self, text):
        # Same token normalization, whole-alias matching and supplied keyword
        # precedence as the inspected candidate; no prefix/fuzzy guessing.
        normalized = ' '.join(''.join(c for c in token.lower() if c.isalpha())
                              for token in text.split()).strip()
        tokens = normalized.split()
        for keyword, aliases in json.loads(self._aliases):
            for alias in aliases:
                parts = alias.split()
                if any(tokens[start:start + len(parts)] == parts
                       for start in range(len(tokens) - len(parts) + 1)):
                    return keyword
        return None

    def _emit(self, meta, engine, status, keyword, confidence, original, health='healthy'):
        context = _copy(meta)
        if type(context) is not dict or set(context) != _META:
            raise ValueError('complete fixture source context required')
        record = dict(context, schema_version=1, record_type='recognition_observation',
            engine=engine, status=status, keyword=keyword, confidence=confidence,
            health=health, original_payload=_copy(original))
        if status in ('partial', 'final', 'score', 'detection'):
            record['score_state'] = 'present' if confidence is not None else 'missing'
        else:
            record['score_state'] = 'missing' if status == 'missing' else 'not_applicable'
        record = validate_observation(record)
        self._ledger.ingest(record)  # Schema/mapping/retry failure is atomic in memory.
        return record

    def vosk(self, meta, raw_json, *, final, application_context=None):
        if type(final) is not bool or type(raw_json) is not str:
            raise ValueError('explicit AcceptWaveform verdict and raw JSON string required')
        try:
            payload = json.loads(raw_json, object_pairs_hook=_pairs, parse_constant=_invalid_constant)
        except (ValueError, TypeError) as exc:
            raise ValueError('malformed synthetic Vosk JSON') from exc
        field = 'text' if final else 'partial'
        if type(payload) is not dict or type(payload.get(field)) is not str:
            raise ValueError('result must contain the explicit partial/final text field')
        original = dict(raw_json=raw_json, engine_output=payload,
                        application_context={} if application_context is None else application_context)
        # Word confidences remain raw. A configured Vosk confidence/verifier score
        # is not a normalized utterance-level confidence supplied by this result.
        return self._emit(meta, 'vosk', 'final' if final else 'partial',
                          self._match(payload[field]), None, original)

    def snowboy(self, meta, result, *, config):
        if type(result) is not int:
            raise ValueError('RunDetection result must be an integer, not confidence')
        config = _copy(config)
        if type(config) is not dict or set(config) != {'keywords', 'alert_keyword', 'confidence'}:
            raise ValueError('explicit application label/confidence configuration required')
        if type(config['keywords']) is not list or not config['keywords']:
            raise ValueError('configured detector label list required')
        for keyword in config['keywords']:
            _label(keyword)
        _label(config['alert_keyword'])
        original = dict(engine_output=result, config=config)
        if result > 0:
            if result > len(config['keywords']):
                raise ValueError('detector index has no configured source label')
            return self._emit(meta, 'snowboy', 'detection', config['keywords'][result - 1], None, original)
        if result == 0:
            return self._emit(meta, 'snowboy', 'no_detection', None, None, original)
        # Inspected runtime logs -1 and continues; it does not prove process death.
        # Other negative codes are retained without assigning silence semantics.
        return self._emit(meta, 'snowboy', 'gap', None, None, original, health='unknown')

    def openwakeword(self, meta, metadata, *, model_name):
        _label(model_name)
        if type(metadata) is not dict or set(metadata) != _OWW:
            raise ValueError('project process-result metadata only; exclude cleaned_audio')
        payload = _copy(metadata)
        if type(payload['available']) is not bool or type(payload['is_speech']) is not bool:
            raise ValueError('explicit availability/VAD verdicts required')
        _number(payload['vad_score'])
        if payload['error'] is not None and type(payload['error']) is not str:
            raise ValueError('application error metadata must be a string or null')
        scores, detections = _rows(payload['scores']), _rows(payload['wake_words'])
        if (not payload['available'] or not payload['is_speech']) and (scores or detections):
            raise ValueError('contradictory application availability/speech metadata')
        if payload['available'] and payload['error'] is not None:
            raise ValueError('successful application result cannot also claim error')
        for name, detected in detections.items():
            score = scores.get(name)
            if score is None or score.get('score') is None:
                raise ValueError('reported detection requires its corresponding score row')
            for field in ('name', 'raw_name', 'score', 'threshold'):
                if canonical_identity(score.get(field)) != canonical_identity(detected.get(field)):
                    raise ValueError('contradictory application detection metadata')
        row = scores.get(model_name)
        original = dict(engine_output=payload, selected_model=model_name,
                        reported_detection=model_name in detections)
        if row is None or row.get('score') is None:
            return self._emit(meta, 'openwakeword', 'missing', None, None, original,
                              health='healthy' if payload['available'] else 'unavailable')
        # Do not rerun or select a threshold; wake_words preserves what the
        # application reported, while score is evidence even below threshold.
        return self._emit(meta, 'openwakeword', 'score', row['name'], row['score'], original)

    def failure(self, meta, *, engine, error):
        error = _copy(error)
        if type(error) is not dict or not error:
            raise ValueError('explicit fixture failure description required')
        return self._emit(meta, engine, 'failure', None, None,
                          dict(engine_output=error, supplied_lifecycle='failure'), health='failed')

    def publication_receipt(self, supplied_receipt):
        # Current dispatcher returns None; do not infer outcome from that value.
        return self._ledger.record_publication_receipt(supplied_receipt)
