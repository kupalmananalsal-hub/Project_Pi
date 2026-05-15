#!/usr/bin/env python3
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any


class AlertDecisionEngine:
    """
    Combines keyword confidence, thermal confidence, and noise conditions into
    a final alert decision.
    """

    def __init__(self) -> None:
        self.keyword_confidence = 0.0
        self.thermal_confidence_boost = 0.0
        self.noise_level_db = -90.0
        self.recent_alerts: deque[dict[str, Any]] = deque()
        self.false_positive_history: dict[str, deque[float]] = defaultdict(deque)

    def evaluate(
        self,
        keyword_event: dict[str, Any],
        thermal_frame: dict[str, Any] | None,
    ) -> dict[str, Any]:
        now = time.monotonic()
        keyword = str(keyword_event.get("keyword", "")).strip().lower()
        self.keyword_confidence = self._as_float(keyword_event.get("confidence"))

        thermal_frame = thermal_frame or {}
        self.thermal_confidence_boost = self._as_float(
            thermal_frame.get("confidence_boost")
        )
        human_detected = bool(thermal_frame.get("human_detected", False))
        body_coverage = self._as_float(thermal_frame.get("body_coverage"))
        detected_part = str(thermal_frame.get("detected_part") or "no_human")

        signal_level_db = self._as_float(
            keyword_event.get("signal_level_db"), fallback=-90.0
        )
        self.noise_level_db = self._as_float(
            keyword_event.get("noise_level_db"), fallback=-90.0
        )
        snr_db = self._as_float(
            keyword_event.get("snr_db"),
            fallback=signal_level_db - self.noise_level_db,
        )
        noise_penalty = self._noise_penalty_for_snr(snr_db)

        final_confidence = min(
            max(self.keyword_confidence + self.thermal_confidence_boost - noise_penalty, 0.0),
            1.0,
        )

        if self.should_suppress_as_false_positive(keyword, final_confidence):
            final_confidence = min(final_confidence, 0.69)

        if final_confidence >= 0.85:
            alert_level = "full_alert"
            should_alert = True
        elif final_confidence >= 0.70:
            alert_level = "visual_only"
            should_alert = True
        else:
            alert_level = "none"
            should_alert = False

        if should_alert:
            self._prune_history(now)
            self.recent_alerts.append(
                {
                    "keyword": keyword,
                    "final_confidence": final_confidence,
                    "timestamp_monotonic": now,
                    "human_detected": human_detected,
                }
            )
        else:
            self.false_positive_history[keyword].append(now)
            self._trim_false_positive_history(keyword, now)

        decision_factors = {
            "keyword_confidence": round(self.keyword_confidence, 4),
            "thermal_boost": round(self.thermal_confidence_boost, 4),
            "noise_penalty": round(noise_penalty, 4),
            "human_detected": human_detected,
            "body_coverage": round(body_coverage, 4),
            "detected_part": detected_part,
            "noise_level_db": round(self.noise_level_db, 2),
            "signal_level_db": round(signal_level_db, 2),
            "snr_db": round(snr_db, 2),
        }

        return {
            "should_alert": should_alert,
            "final_confidence": round(final_confidence, 4),
            "decision_factors": decision_factors,
            "alert_level": alert_level,
        }

    def should_suppress_as_false_positive(self, keyword: str, confidence: float) -> bool:
        now = time.monotonic()
        self._trim_false_positive_history(keyword, now)
        repeated_low_confidence = len(self.false_positive_history[keyword]) >= 3
        recently_alerted_same_keyword = any(
            entry["keyword"] == keyword
            and now - entry["timestamp_monotonic"] < 10.0
            for entry in self.recent_alerts
        )
        return confidence < 0.75 and repeated_low_confidence and recently_alerted_same_keyword

    def _prune_history(self, now: float) -> None:
        while self.recent_alerts and now - self.recent_alerts[0]["timestamp_monotonic"] > 30.0:
            self.recent_alerts.popleft()

    def _trim_false_positive_history(self, keyword: str, now: float) -> None:
        history = self.false_positive_history[keyword]
        while history and now - history[0] > 30.0:
            history.popleft()

    @staticmethod
    def _noise_penalty_for_snr(snr_db: float) -> float:
        if snr_db >= 20.0:
            return 0.0
        if snr_db >= 10.0:
            return 0.05
        return 0.10

    @staticmethod
    def _as_float(value: Any, fallback: float = 0.0) -> float:
        if value is None:
            return fallback
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback
