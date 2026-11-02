"""C1.51 TEST ONLY: in-memory observations and fixture classification transitions.

Never imported by runtime. No I/O, clocks, timers, engines, publication callbacks,
acoustic thresholds, release rules or audible authority policy. All membership,
timestamps, association, eligibility and classification are supplied by fixtures.
Unbounded, single-threaded and non-durable; not an integration-ready coordinator.
"""
from datetime import datetime
import json
import math


ENGINES = {'vosk', 'snowboy', 'openwakeword'}
DETECTIONS = {'partial', 'final', 'score'}
CONTROLS = {'missing', 'gap', 'failure'}
FIELDS = {'schema_version', 'observation_id', 'engine', 'generation', 'candidate_id',
          'sequence', 'revision', 'kind', 'observed_at', 'original_payload',
          'keyword', 'confidence', 'score_state'}


def _copy(value):
    """Reject lossy/nonfinite JSON, then return an independent JSON-value copy."""
    def check(item):
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise ValueError('JSON object keys must be strings')
                check(child)
        elif type(item) is list:
            for child in item:
                check(child)
        elif type(item) is float:
            if not math.isfinite(item):
                raise ValueError('nonfinite JSON number')
        elif item is not None and type(item) not in (str, int, bool):
            raise ValueError('plain JSON values required')
    check(value)
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _identity(value):
    if type(value) is not str or not value.strip():
        raise ValueError('nonempty string identity required')


def _same_json(left, right):
    # Dict equality conflates True/1 and 1/1.0; immutable JSON identity must not.
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def _timestamp(value):
    if type(value) is not str:
        raise ValueError('fixture timestamp must be an aware ISO string')
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError('invalid fixture timestamp') from exc
    if parsed.utcoffset() is None:
        raise ValueError('timestamp needs an explicit timezone')


class ObservationAdapter:
    """Immutable ledger plus per-engine/generation/candidate views.

    Matcher is a pure fixture text-to-label callback, not a recognizer. Controls
    retain last evidence and finality; health/continuity describe later uncertainty.
    Sequence orders a generation; timestamps never imply expiry or silence.
    """
    def __init__(self, matcher):
        self.matcher = matcher
        self._active = {}
        self._generations = set()
        self._health = {}
        self._sequence = {}
        self._continuous = {}
        self._records = {}
        self._views = {}
        self._receipts = {}

    def begin_generation(self, engine, generation):
        if engine not in ENGINES:
            raise ValueError('unknown engine')
        _identity(generation)
        key = (engine, generation)
        if self._active.get(engine) == generation:
            return  # Idempotent declaration cannot heal a failed generation.
        if key in self._generations:
            raise ValueError('retired generation cannot reactivate')
        self._generations.add(key)
        self._active[engine] = generation
        self._health[key] = 'unknown'
        self._sequence[key] = 0
        self._continuous[key] = True

    def ingest(self, observation):
        record = _copy(observation)
        if type(record) is not dict or set(record) != FIELDS:
            raise ValueError('complete versioned observation schema required')
        if type(record['schema_version']) is not int or record['schema_version'] != 1:
            raise ValueError('unsupported schema version')
        for field in ('observation_id', 'engine', 'generation', 'candidate_id'):
            _identity(record[field])
        engine, generation = record['engine'], record['generation']
        if engine not in ENGINES:
            raise ValueError('unknown engine')
        sequence = record['sequence']
        if type(sequence) is not int or sequence < 1:
            raise ValueError('positive integer source sequence required')
        _timestamp(record['observed_at'])
        if type(record['original_payload']) is not dict:
            raise ValueError('original payload must be an object')
        kind, keyword, score = record['kind'], record['keyword'], record['confidence']
        if type(kind) is not str or kind not in DETECTIONS | CONTROLS:
            raise ValueError('explicit detection or uncertainty status required')
        if keyword is not None:
            _identity(keyword)
        score_state = record['score_state']
        if score_state == 'present':
            if type(score) not in (int, float) or not 0 <= score <= 1:
                raise ValueError('present score must be finite and in domain [0,1]')
        elif score_state not in ('missing', 'not_applicable') or score is not None:
            raise ValueError('explicit absent-score state must have null confidence')
        revision = record['revision']
        if kind in DETECTIONS:
            if type(revision) is not int or revision < 1:
                raise ValueError('positive candidate revision required')
            if score_state == 'not_applicable':
                raise ValueError('recognition score must be present or explicitly missing')
            if engine == 'vosk':
                if kind not in ('partial', 'final'):
                    raise ValueError('Vosk needs explicit partial/final status')
                text = record['original_payload'].get('partial' if kind == 'partial' else 'text')
                if type(text) is not str or self.matcher(text) != keyword:
                    raise ValueError('Vosk fixture label must match original text')
            elif kind != 'score':
                raise ValueError('score engines cannot claim ASR finality')
        else:
            expected_score_state = 'missing' if kind == 'missing' else 'not_applicable'
            if revision is not None or keyword is not None or score is not None or score_state != expected_score_state:
                raise ValueError('uncertainty controls cannot fabricate recognition evidence')

        identity = record['observation_id']
        if identity in self._records:
            if not _same_json(self._records[identity], record):
                raise ValueError('observation identity conflict')
            return _copy(record)  # Old retry cannot rewind current view or create episodes.
        source = (engine, generation)
        if self._active.get(engine) != generation:
            raise ValueError('generation is absent or retired')
        if sequence <= self._sequence[source]:
            raise ValueError('out-of-order source observation')
        key = (engine, generation, record['candidate_id'])
        view = _copy(self._views.get(key, dict(engine=engine, generation=generation,
            candidate_id=record['candidate_id'], revision=0, keyword=None, confidence=None,
            score_state='missing', evidence_status=None, evidence_observation_id=None)))
        if kind in DETECTIONS:
            if self._health[source] == 'failed':
                raise ValueError('recovery needs an explicitly new generation')
            if view['evidence_status'] == 'final':
                raise ValueError('final candidate cannot reopen')
            if revision != view['revision'] + 1:
                raise ValueError('candidate revisions must be consecutive')
            view['revision'] = revision
            # Missing score is not ordinary/negative speech or a replacement score.
            if kind != 'score' or score_state == 'present':
                view.update(keyword=keyword, confidence=score, score_state=score_state,
                            evidence_status=kind, evidence_observation_id=identity)
        view.update(latest_observation_id=identity, latest_kind=kind,
                    latest_score_state=score_state)
        health = self._health[source]
        if kind == 'failure':
            health = 'failed'
        elif health != 'failed':
            health = 'ok' if kind in DETECTIONS and score_state == 'present' else 'unknown'
        continuous = (self._continuous[source] and sequence == self._sequence[source] + 1
                      and kind in DETECTIONS and score_state == 'present')
        # Every validation and callback above precedes state changes.
        self._records[identity] = record
        self._views[key] = view
        self._health[source] = health
        self._sequence[source] = sequence
        self._continuous[source] = continuous
        return _copy(record)

    def candidate(self, key):
        if key not in self._views:
            return None
        view = _copy(self._views[key])
        source = key[:2]
        view.update(health=self._health[source], continuous=self._continuous[source],
                    generation_active=self._active[key[0]] == key[1])
        return view

    def candidates(self):
        return [self.candidate(key) for key in self._views]

    def journal(self):
        return _copy(list(self._records.values()))

    def record_receipt(self, receipt):
        record = _copy(receipt)
        if type(record) is not dict or set(record) != {'receipt_id', 'observation_id', 'outcome', 'observed_at', 'reason'}:
            raise ValueError('complete submission receipt required')
        for field in ('receipt_id', 'observation_id', 'reason'):
            _identity(record[field])
        _timestamp(record['observed_at'])
        if record['outcome'] not in ('accepted', 'rejected', 'unknown') or record['observation_id'] not in self._records:
            raise ValueError('receipt needs known observation and explicit outcome')
        identity = record['receipt_id']
        if identity in self._receipts and not _same_json(self._receipts[identity], record):
            raise ValueError('receipt identity conflict')
        self._receipts[identity] = record
        return _copy(record)

    def receipts(self):
        return _copy(list(self._receipts.values()))


class EpisodeContract:
    """Fixture membership and immutable classification records, NEVER siren events.

    Caller supplies a pure classifier, association validity and classification
    eligibility. None of these imply audible authority. Missing/failure evidence
    retention is separate from fixture permission to classify it. No release rule,
    automatic episode creation, durable transaction, publication or ACK ownership.
    """
    def __init__(self, adapter, classify):
        self.adapter = adapter
        self.classify = classify
        self._bindings = {}
        self._candidate_episodes = {}
        self._thermal = {}
        self._events = {}

    def bind_episode(self, episode_id, candidate_key):
        _identity(episode_id)
        if type(candidate_key) is not tuple or len(candidate_key) != 3:
            raise ValueError('structured engine/generation/candidate key required')
        for item in candidate_key:
            _identity(item)
        if self.adapter.candidate(candidate_key) is None:
            raise ValueError('unknown candidate')
        if episode_id in self._bindings and self._bindings[episode_id] != candidate_key:
            raise ValueError('episode cannot merge candidates or engines')
        if candidate_key in self._candidate_episodes and self._candidate_episodes[candidate_key] != episode_id:
            raise ValueError('same candidate cannot fabricate another episode')
        self._bindings[episode_id] = candidate_key
        self._candidate_episodes[candidate_key] = episode_id

    def bindings(self):
        return _copy({episode: list(key) for episode, key in self._bindings.items()})

    def reevaluate(self, episode_id, thermal_record, *, association_valid, classification_eligible):
        if type(association_valid) is not bool or type(classification_eligible) is not bool:
            raise ValueError('explicit boolean fixture verdicts required')
        if episode_id not in self._bindings:
            raise ValueError('unknown fixture episode')
        thermal = _copy(thermal_record)
        if type(thermal) is not dict or set(thermal) != {'thermal_id', 'observed_at', 'payload'}:
            raise ValueError('complete fixture thermal observation required')
        _identity(thermal['thermal_id']); _timestamp(thermal['observed_at'])
        if type(thermal['payload']) is not dict:
            raise ValueError('thermal payload must be an object')
        thermal_id = thermal['thermal_id']
        if thermal_id in self._thermal and not _same_json(self._thermal[thermal_id], thermal):
            raise ValueError('thermal identity conflict')
        key = self._bindings[episode_id]
        view = self.adapter.candidate(key)
        result = dict(classification=None, event=None, health=view['health'],
                      audible_authority='UNRESOLVED')
        event = None
        if (association_valid and classification_eligible and view['keyword'] is not None
                and view['confidence'] is not None and view['score_state'] == 'present'):
            original = self.adapter._records[view['evidence_observation_id']]
            voice = dict(keyword=view['keyword'], confidence=view['confidence'],
                         source=view['engine'], timestamp=original['observed_at'])
            decision = _copy(self.classify(_copy(voice), _copy(thermal['payload'])))
            if type(decision) is not dict or decision.get('decision_state') not in {'advisory', 'critical', 'suppressed', 'confirmed', 'system_fault'}:
                raise ValueError('classifier must return an explicit decision snapshot')
            result['classification'] = decision
            level = decision['decision_state']
            transition = (episode_id, level)
            if (level in {'advisory', 'critical'} and transition not in self._events
                    and not (level == 'advisory' and (episode_id, 'critical') in self._events)):
                event = dict(voice, event_id='fixture-transition:'+json.dumps([episode_id, level], separators=(',', ':')),
                             event_kind='fixture_classification_transition', episode_id=episode_id,
                             candidate_key=list(key), observation_id=view['evidence_observation_id'],
                             thermal_id=thermal_id, decision_state=level, classification=decision,
                             audible_authority='UNRESOLVED')
        # Callback/validation failures above cannot partly record a transition/frame.
        self._thermal[thermal_id] = thermal
        if event is not None:
            self._events[(episode_id, event['decision_state'])] = _copy(event)
            result['event'] = _copy(event)
        return _copy(result)

    def events(self):
        return _copy(list(self._events.values()))

    def thermal_journal(self):
        return _copy(list(self._thermal.values()))
