"""Pure experimental recognition contract. NOT imported or wired by applications.

No recognition, label inference, clocks, I/O, callbacks, suppression, episodes,
classification, persistence, thermal or alarm authority. Supplied records are data.
Unbounded single-threaded memory only; not a durable/concurrent runtime adapter.
"""
from datetime import datetime
import json
import math


_ENGINES = frozenset({'vosk', 'snowboy', 'openwakeword'})
_DETECTIONS = frozenset({'partial', 'final', 'score', 'detection'})
_CONTROLS = frozenset({'missing', 'no_detection', 'gap', 'failure'})
_FIELDS = frozenset({'schema_version', 'record_type', 'observation_id', 'engine',
    'producer_id', 'generation_id', 'candidate_id', 'sequence', 'revision', 'status',
    'observed_at', 'clock_domain', 'capture_range', 'original_payload', 'keyword',
    'confidence', 'score_state', 'health'})


def canonical_identity(value):
    """Lossless plain JSON-value identity; true, 1 and 1.0 remain distinct.

    This is not a fingerprint for the existing AlertIn API. Object key order is
    ignored; supplied raw JSON text inside a payload remains an exact string.
    """
    ancestors = set()

    def check(item):
        if type(item) in (dict, list):
            identity = id(item)
            if identity in ancestors:
                raise ValueError('cyclic JSON is not evidence')
            ancestors.add(identity)
            if type(item) is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        raise ValueError('JSON keys must be strings')
                    check(child)
            else:
                for child in item:
                    check(child)
            ancestors.remove(identity)
        elif type(item) is float:
            if not math.isfinite(item):
                raise ValueError('nonfinite number')
        elif item is not None and type(item) not in (str, int, bool):
            raise ValueError('plain JSON values required')

    check(value)
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _label(value):
    if type(value) is not str or not value.strip():
        raise ValueError('nonempty string required')


def _timestamp(value):
    _label(value)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError('invalid supplied timestamp') from exc
    if parsed.utcoffset() is None:
        raise ValueError('supplied timestamp needs timezone')


def validate_observation(raw):
    """Return a detached version-1 value, without interpreting spoken evidence."""
    record = json.loads(canonical_identity(raw))
    if type(record) is not dict or set(record) != _FIELDS:
        raise ValueError('complete observation schema required; no extra fields')
    if type(record['schema_version']) is not int or record['schema_version'] != 1:
        raise ValueError('unsupported schema version')
    if record['record_type'] != 'recognition_observation':
        raise ValueError('not an observation record')
    for field in ('observation_id', 'engine', 'producer_id', 'generation_id', 'clock_domain'):
        _label(record[field])
    engine, status = record['engine'], record['status']
    if engine not in _ENGINES or type(status) is not str or status not in _DETECTIONS | _CONTROLS:
        raise ValueError('unknown engine or status')
    if type(record['sequence']) is not int or record['sequence'] < 1:
        raise ValueError('positive integer source sequence required')
    _timestamp(record['observed_at'])
    capture = record['capture_range']
    if capture is not None:
        if (type(capture) is not dict or set(capture) != {'first', 'last'}
                or any(type(capture[k]) is not int for k in capture)
                or not 0 <= capture['first'] <= capture['last']):
            raise ValueError('explicit nonnegative capture range required')
    if type(record['original_payload']) is not dict:
        raise ValueError('original evidence payload must be an object')
    candidate = record['candidate_id']
    if candidate is not None:
        _label(candidate)
    keyword, confidence = record['keyword'], record['confidence']
    if keyword is not None:
        _label(keyword)
    if record['score_state'] == 'present':
        if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
            raise ValueError('confidence must be finite and within its declared [0,1] domain')
    elif record['score_state'] not in ('missing', 'not_applicable') or confidence is not None:
        raise ValueError('absent score must be explicit and null, not zero')
    health = record['health']
    if health not in ('healthy', 'unknown', 'unavailable', 'failed'):
        raise ValueError('explicit engine health required')
    if status in _DETECTIONS:
        if candidate is None or type(record['revision']) is not int or record['revision'] < 1:
            raise ValueError('recognition needs candidate and positive integer revision')
        if health != 'healthy':
            raise ValueError('successful recognition cannot claim failed/unavailable health')
        if engine == 'vosk' and status not in ('partial', 'final'):
            raise ValueError('Vosk requires explicit ASR finality')
        if engine != 'vosk' and status not in ('score', 'detection'):
            raise ValueError('score engines cannot claim ASR finality')
        if record['score_state'] == 'not_applicable':
            raise ValueError('recognition confidence is present or explicitly missing')
        if status == 'score' and (keyword is None or record['score_state'] != 'present'):
            raise ValueError('missing model score requires explicit missing status')
        if status == 'detection' and keyword is None:
            raise ValueError('detector observation needs a known label, not an invented score')
    else:
        absent = 'missing' if status == 'missing' else 'not_applicable'
        if (record['revision'] is not None or keyword is not None or confidence is not None
                or record['score_state'] != absent):
            raise ValueError('controls cannot fabricate a recognition or score')
        if status == 'failure' and health != 'failed':
            raise ValueError('failure requires failed engine health')
        if status == 'no_detection' and health != 'healthy':
            raise ValueError('no detection is distinct from engine failure')
        if status != 'failure' and health == 'failed':
            raise ValueError('failed health requires explicit failure status')
    return record


class EvidenceLedger:
    """Non-actuating memory. Source-local order, independent candidate revisions.

    Snapshot order is lexical source/generation/sequence, not a global acoustic
    chronology. A receipt only records a supplied outcome, never durable delivery.
    """
    def __init__(self):
        self._active = {}
        self._generations = {}
        self._records = {}  # Canonical strings prevent retained caller references.
        self._views = {}
        self._receipts = {}

    def begin_generation(self, engine, producer_id, generation_id):
        for value in (engine, producer_id, generation_id):
            _label(value)
        if engine not in _ENGINES:
            raise ValueError('unknown engine')
        producer = (engine, producer_id)
        source = producer + (generation_id,)
        if self._active.get(producer) == generation_id:
            return  # Does not heal failed health or reset ordering.
        if source in self._generations:
            raise ValueError('retired generation cannot reactivate')
        self._generations[source] = dict(engine=engine, producer_id=producer_id,
            generation_id=generation_id, health='unknown', sequence=0,
            latest_status=None, continuous=True)
        self._active[producer] = generation_id

    def ingest(self, raw):
        record = validate_observation(raw)
        encoded = canonical_identity(record)
        identity = record['observation_id']
        if identity in self._records:
            if self._records[identity] != encoded:
                raise ValueError('immutable observation identity conflict')
            return dict(record_type='in_memory_observation_receipt', observation_id=identity, outcome='duplicate')
        source = (record['engine'], record['producer_id'], record['generation_id'])
        if self._active.get(source[:2]) != source[2]:
            raise ValueError('generation absent or retired')
        generation = dict(self._generations[source])
        if record['sequence'] <= generation['sequence']:
            raise ValueError('out-of-order observation requires reconciliation')
        if generation['health'] == 'failed' and record['status'] != 'failure':
            raise ValueError('failed generation needs explicit new generation recovery')
        status = record['status']
        view = None
        if record['candidate_id'] is not None:
            key = source + (record['candidate_id'],)
            view = json.loads(canonical_identity(self._views.get(key, dict(
                engine=source[0], producer_id=source[1], generation_id=source[2],
                candidate_id=key[3], revision_history=[], keyword=None, confidence=None,
                recognition_status=None, evidence_observation_id=None))))
            if status in _DETECTIONS:
                if view['recognition_status'] == 'final':
                    raise ValueError('final candidate cannot be reopened')
                if record['revision'] != len(view['revision_history']) + 1:
                    raise ValueError('candidate revisions must be consecutive')
                view['revision_history'].append(identity)
                view.update(keyword=record['keyword'], confidence=record['confidence'],
                    recognition_status=status, evidence_observation_id=identity)
            view.update(latest_status=status, latest_observation_id=identity)
        generation.update(health=record['health'], sequence=record['sequence'], latest_status=status,
            continuous=(generation['continuous'] and record['sequence'] == generation['sequence'] + 1
                        and status not in ('missing', 'gap', 'failure')))
        # All schema/order/revision checks precede mutation.
        self._records[identity] = encoded
        self._generations[source] = generation
        if view is not None:
            self._views[key] = view
        return dict(record_type='in_memory_observation_receipt', observation_id=identity, outcome='recorded')

    def candidate(self, key):
        if type(key) is not tuple or len(key) != 4:
            raise ValueError('structured engine/producer/generation/candidate key required')
        for value in key:
            _label(value)
        if key not in self._views:
            return None
        view = json.loads(canonical_identity(self._views[key]))
        generation = self._generations[key[:3]]
        view.update(generation_health=generation['health'], continuous=generation['continuous'],
                    generation_active=self._active[key[:2]] == key[2])
        return view

    def record_publication_receipt(self, raw):
        encoded = canonical_identity(raw)
        record = json.loads(encoded)
        if type(record) is not dict or set(record) != {'receipt_id', 'observation_id', 'outcome', 'observed_at', 'clock_domain', 'reason'}:
            raise ValueError('complete supplied publication receipt required')
        for field in ('receipt_id', 'observation_id', 'clock_domain', 'reason'):
            _label(record[field])
        _timestamp(record['observed_at'])
        if record['outcome'] not in ('accepted', 'rejected', 'unknown') or record['observation_id'] not in self._records:
            raise ValueError('known observation and explicit supplied outcome required')
        identity = record['receipt_id']
        if identity in self._receipts and self._receipts[identity] != encoded:
            raise ValueError('immutable receipt identity conflict')
        self._receipts[identity] = encoded
        return json.loads(encoded)

    def snapshot(self):
        records = [json.loads(value) for value in self._records.values()]
        records.sort(key=lambda r: (r['engine'], r['producer_id'], r['generation_id'], r['sequence'], r['observation_id']))
        generations = []
        for key in sorted(self._generations):
            value = dict(self._generations[key])
            value['active'] = self._active[key[:2]] == key[2]
            generations.append(value)
        return dict(observations=records, candidates=[self.candidate(key) for key in sorted(self._views)],
                    generations=generations,
                    publication_receipts=[json.loads(self._receipts[key]) for key in sorted(self._receipts)])
