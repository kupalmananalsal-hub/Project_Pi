"""C1.44 TEST-ONLY decision/publication model, never live recognition.

Episode membership and association validity are supplied by synthetic fixtures.
No release timing, real segmentation, durable coordinator, API or Flutter output
is implemented. IDs below are fixture IDs, not the proposed production ID scheme.
"""
from copy import deepcopy
import math


class EpisodeReviewModel:
    def __init__(self, classify, publish):
        self.classify = classify
        self.publish = publish
        self.voices = {}
        self.closed = set()
        self.unknown = set()
        self.sent = set()
        self.pending = {}

    def observe(self, episode, voice, thermal, *, available=True):
        score = voice.get("confidence") if voice is not None else None
        if not available or score is None or not math.isfinite(score) or not 0 <= score <= 1:
            self.unknown.add(episode)
            return None
        if episode in self.closed:
            raise ValueError("released episode cannot accept a new observation")
        previous = self.voices.get(episode)
        if previous and (previous["source"], previous["keyword"]) != (voice["source"], voice["keyword"]):
            raise ValueError("fixture cannot merge distinct sources or labels")
        self.unknown.discard(episode)
        self.voices[episode] = deepcopy(voice)
        return self.thermal(episode, thermal, association_valid=True)

    def release(self, episode, *, verified):
        # A fixture verdict, NEVER inferred from a timestamp, silence or a missing score.
        if verified:
            self.closed.add(episode)

    def thermal(self, episode, thermal, *, association_valid):
        if not association_valid or episode in self.closed or episode not in self.voices:
            return None
        decision = self.classify(self.voices[episode], thermal)
        level = decision["decision_state"]
        if level not in {"advisory", "critical"}:
            return None
        key = (episode, level)
        if key in self.sent or (level == "advisory" and (episode, "critical") in self.sent):
            return None
        # Freeze BEFORE publication: an ambiguous failure must retry the same payload.
        self.pending.setdefault(key, deepcopy({**self.voices[episode], **decision,
            "episode_id": episode, "event_id": f"fixture:{episode}:{level}"}))
        return self._publish(key)

    def _publish(self, key):
        event = self.pending[key]
        self.publish(deepcopy(event))
        self.sent.add(key)  # Commit intent only after callback reports success.
        del self.pending[key]
        return deepcopy(event)

    def retry_pending(self):
        return [self._publish(key) for key in list(self.pending)]
