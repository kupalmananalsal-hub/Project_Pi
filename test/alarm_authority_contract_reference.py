"""C1.47 TEST ONLY: evidence, classification and fixture authority are separate.

No acoustic authority policy is selected here. FIXTURE_AUTHORIZED is an explicit
counterfactual input, never a validated real-world permission. This unbounded,
single-threaded in-memory model is NOT a durable coordinator or runtime adapter.
Association and episode membership are supplied by fixtures, without time limits,
confidence calibration, release inference, cross-engine merging or sensor I/O.
"""
from copy import deepcopy
import json
import math


class AuthorityContractReference:
    def __init__(self, classify):
        # Must be a pure snapshot callback. The test adapter constructs a fresh
        # existing decision engine; doing that in production is NOT proposed.
        self.classify = classify
        self._records = {}
        self._bindings = {}
        self._labels = {}
        self._voices = {}
        self._health = {}
        self._continuous = {}
        self._sequence = {}
        self._voice_episodes = set()
        self._events = {}

    def ingest(self, episode, observation):
        encoded = json.dumps(observation, sort_keys=True, allow_nan=False)
        record = json.loads(encoded)
        if not isinstance(episode, str) or not episode:
            raise ValueError('explicit fixture episode required')
        for field in ('observation_id', 'source', 'session'):
            if not isinstance(record.get(field), str) or not record[field]:
                raise ValueError('observation/source/session identity required')
        identity = record['observation_id']
        if identity in self._records:
            if self._records[identity] != (episode, encoded):
                raise ValueError('conflicting observation identity or association')
            return  # An old identical retry never rewinds evidence.
        sequence = record.get('sequence')
        if type(sequence) is not int or sequence < 1:
            raise ValueError('positive source sequence required')
        status = record.get('status')
        if status not in {'provisional', 'final', 'score', 'failure', 'gap', 'missing'}:
            raise ValueError('explicit observation status required')
        keyword = record.get('keyword')
        if keyword is not None and (not isinstance(keyword, str) or not keyword):
            raise ValueError('keyword must be a label or null')
        confidence = record.get('confidence')
        if confidence is not None and (type(confidence) not in (float, int)
                or not math.isfinite(confidence) or not 0 <= confidence <= 1):
            raise ValueError('confidence must be finite, in range, or null')
        if status == 'score' and (keyword is None or confidence is None):
            raise ValueError('absent model scores require an explicit missing control')
        session = (record['source'], record['session'])
        if sequence <= self._sequence.get(session, 0):
            raise ValueError('out-of-order input requires reconciliation')
        if episode in self._bindings and self._bindings[episode] != session:
            raise ValueError('cannot merge engines or generations into an episode')
        is_detection = status in {'provisional', 'final', 'score'}
        if self._health.get(session) == 'failed' and is_detection:
            raise ValueError('new engine generation requires a new session')
        if is_detection and keyword and episode in self._labels and self._labels[episode] != keyword:
            raise ValueError('cannot merge different keyword candidates')
        if not is_detection and (keyword is not None or confidence is not None):
            raise ValueError('health/missing controls cannot fabricate detections')
        # Validation precedes all state changes. No durable transaction is implied.
        previous = self._sequence.get(session, 0)
        self._records[identity] = (episode, encoded)
        self._bindings[episode] = session
        self._sequence[session] = sequence
        self._continuous[session] = (self._continuous.get(session, True)
                                    and sequence == previous + 1 and is_detection)
        if status == 'failure' or self._health.get(session) == 'failed':
            self._health[session] = 'failed'
        elif not is_detection or (keyword is not None and confidence is None):
            self._health[session] = 'unknown'
        else:
            self._health[session] = 'ok'
        if is_detection:
            if keyword is None:
                # Ordinary/empty hypothesis revision invalidates CURRENT pairing;
                # it does not erase observations, events or user dispositions.
                self._voices.pop(episode, None)
            elif confidence is not None:
                self._voices[episode] = record
                self._labels[episode] = keyword
                self._voice_episodes.add(episode)
        # Missing scores, gaps and failures preserve retained evidence. Its future
        # eligibility is independently bounded by association_valid, never silence.

    def review(self, episode, thermal, *, association_valid, authority='UNRESOLVED'):
        if type(association_valid) is not bool:
            raise ValueError('fixture association verdict must be explicit')
        if authority not in {'UNRESOLVED', 'FIXTURE_AUTHORIZED', 'FIXTURE_DENIED'}:
            raise ValueError('unknown fixture authority verdict')
        session = self._bindings.get(episode)
        result = dict(authority=authority, health=self._health.get(session, 'unknown'),
                      continuous=self._continuous.get(session, False),
                      candidate_decision=None, event=None)
        voice = self._voices.get(episode)
        if not association_valid or voice is None:
            return result
        decision = self.classify(deepcopy(voice), deepcopy(thermal))
        result['candidate_decision'] = deepcopy(decision)
        if authority != 'FIXTURE_AUTHORIZED':
            return result
        level = decision['decision_state']
        key = (episode, level)
        if level not in {'advisory', 'critical'} or key in self._events:
            return result
        if level == 'advisory' and (episode, 'critical') in self._events:
            return result
        event = {**deepcopy(voice), **deepcopy(decision), 'episode_id': episode,
                 'event_id': 'fixture:' + json.dumps([episode, level], separators=(',', ':'))}
        self._events[key] = event
        result['event'] = deepcopy(event)
        return result

    def journal(self):
        return [json.loads(encoded) for _, encoded in self._records.values()]

    def events(self):
        return deepcopy(list(self._events.values()))

    def voice_episode_count(self):
        return len(self._voice_episodes)
