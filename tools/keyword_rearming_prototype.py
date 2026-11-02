"""C1.43 OFFLINE PROTOTYPE -- deliberately not imported by the live KWS path.

Score transitions cannot prove separate utterances. Release timing is supplied
by the experiment, has no deployment default, and needs acoustic validation.
Feed explicit per-keyword observations: missing scores are NOT negative scores.
Single-threaded; no audio, models, network, persistence, or event-ID ownership.
"""
from dataclasses import dataclass
import math


@dataclass
class _Episode:
    latched: bool = False
    critical_sent: bool = False
    low_since: float | None = None
    last_at: float | None = None


class KeywordRearmingPrototype:
    """Emit candidate eligibility reasons, never publish or classify emergencies.

    An observed release removes the need for a fixed two-second wait. An initial
    match and one critical-confidence upgrade remain eligible immediately. This
    does NOT solve later thermal escalation; it must not gate live alert delivery.
    """

    def __init__(self, *, release_seconds: float, max_gap_seconds: float,
                 critical_threshold: float):
        if (not math.isfinite(release_seconds) or release_seconds <= 0
                or not math.isfinite(max_gap_seconds) or max_gap_seconds <= 0
                or not math.isfinite(critical_threshold)
                or not 0 < critical_threshold <= 1):
            raise ValueError("finite positive release/gap and critical threshold in (0,1] required")
        self.release_seconds = release_seconds
        self.max_gap_seconds = max_gap_seconds
        self.critical_threshold = critical_threshold
        self._episodes: dict[str, _Episode] = {}

    def observe(self, keyword: str, score: float | None, threshold: float,
                now: float, *, available: bool = True) -> str | None:
        """Observe a timestamped score; None means no new candidate eligibility.

        Call once per known keyword per prediction, including unavailable/missing
        observations. Only adjacent valid low observations establish release;
        unavailable, invalid, sparse or above-threshold scores break that chain.
        """
        if not math.isfinite(now) or not math.isfinite(threshold) or not 0 < threshold <= 1:
            raise ValueError("finite timestamp and threshold in (0,1] required")
        state = self._episodes.setdefault(keyword, _Episode())
        if state.last_at is not None and now < state.last_at:
            raise ValueError("per-keyword timestamps must be monotonic")
        if state.last_at is not None and now - state.last_at > self.max_gap_seconds:
            state.low_since = None
        state.last_at = now
        if (not available or score is None or not math.isfinite(score)
                or not 0 <= score <= 1):
            state.low_since = None
            return None
        if score < threshold:
            if state.low_since is None:
                state.low_since = now
            if now - state.low_since >= self.release_seconds:
                state.latched = False
                state.critical_sent = False
            return None
        state.low_since = None
        if not state.latched:
            state.latched = True
            state.critical_sent = score >= self.critical_threshold
            return "episode_start"
        if score >= self.critical_threshold and not state.critical_sent:
            state.critical_sent = True
            return "critical_upgrade"
        return None
