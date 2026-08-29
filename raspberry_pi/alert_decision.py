#!/usr/bin/env python3
from __future__ import annotations

import math
import sys
import time
from collections import defaultdict, deque
from dataclasses import dataclass, fields
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class DecisionState(str, Enum):
    SUPPRESSED = "suppressed"
    ADVISORY = "advisory"
    CONFIRMED = "confirmed"
    CRITICAL = "critical"
    SYSTEM_FAULT = "system_fault"


class AlertModality(str, Enum):
    VOICE_ONLY = "voice_only"
    VOICE_THERMAL = "voice_thermal"
    THERMAL_ONLY = "thermal_only"
    SENSOR_FAULT = "sensor_fault"


class ThermalState(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    UNAVAILABLE = "unavailable"
    STALE = "stale"
    INVALID = "invalid"


DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parent / "config" / "alert_policy.yaml"
)


@dataclass(frozen=True)
class AlertPolicy:
    policy_version: str = "phase1.2.safe_defaults"
    advisory_threshold: float = 0.70
    critical_threshold: float = 0.85
    thermal_freshness_seconds: float = 1.25
    repeat_window_seconds: float = 10.0
    repeat_required_count: int = 2
    repeat_escalates_to_critical: bool = True
    idempotency_ttl_seconds: float = 60.0
    idempotency_max_entries: int = 512
    policy_source: str = "safe_defaults"

    @classmethod
    def load(cls, path: Path | None = None) -> "AlertPolicy":
        config_path = path or DEFAULT_POLICY_PATH
        if not config_path.exists():
            cls._warn_policy_fallback(
                config_path,
                "policy file is missing",
            )
            return cls()

        try:
            return cls._load_from_file(config_path)
        except Exception as exc:
            cls._warn_policy_fallback(config_path, str(exc))
            return cls()

    @classmethod
    def _load_from_file(cls, config_path: Path) -> "AlertPolicy":
        raw_values: dict[str, str] = {}
        has_policy_content = False
        for line_number, line in enumerate(
            config_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            stripped = line.split("#", 1)[0].strip()
            if not stripped:
                continue
            has_policy_content = True
            if ":" not in stripped or stripped.startswith(":"):
                raise ValueError(f"malformed policy line {line_number}")
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip().strip('"\'')
            if not key:
                raise ValueError(f"empty policy key on line {line_number}")
            raw_values[key] = value

        if not has_policy_content:
            raise ValueError("policy file is empty")

        field_map = {field.name: field for field in fields(cls)}
        required_keys = set(field_map) - {"policy_source"}
        missing_keys = sorted(required_keys - set(raw_values))
        if missing_keys:
            raise ValueError(
                "policy file is missing required setting(s): "
                + ", ".join(missing_keys)
            )

        unknown_keys = sorted(set(raw_values) - required_keys)
        if unknown_keys:
            raise ValueError(
                "policy file contains unsupported setting(s): "
                + ", ".join(unknown_keys)
            )

        parsed = cls._parse_policy_values(raw_values)
        policy = cls(**parsed, policy_source="file")
        policy._validate()
        return policy

    @classmethod
    def _parse_policy_values(cls, raw_values: dict[str, str]) -> dict[str, object]:
        parsed: dict[str, object] = {}
        field_map = {field.name: field for field in fields(cls)}
        for key, raw_value in raw_values.items():
            if key not in field_map:
                continue
            default = field_map[key].default
            if isinstance(default, bool):
                normalized = raw_value.strip().lower()
                if normalized not in {"true", "false"}:
                    raise ValueError(f"{key} must be true or false")
                parsed[key] = normalized == "true"
            elif isinstance(default, int) and not isinstance(default, bool):
                parsed[key] = int(raw_value)
            elif isinstance(default, float):
                value = float(raw_value)
                if not math.isfinite(value):
                    raise ValueError(f"{key} must be finite")
                parsed[key] = value
            else:
                parsed[key] = raw_value
        return parsed

    def _validate(self) -> None:
        if not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        if not 0.0 <= self.advisory_threshold < self.critical_threshold <= 1.0:
            raise ValueError(
                "thresholds must satisfy "
                "0.0 <= advisory_threshold < critical_threshold <= 1.0"
            )
        if self.thermal_freshness_seconds <= 0:
            raise ValueError("thermal_freshness_seconds must be positive")
        if self.repeat_window_seconds <= 0:
            raise ValueError("repeat_window_seconds must be positive")
        if self.repeat_required_count < 2:
            raise ValueError("repeat_required_count must be at least 2")
        if not isinstance(self.repeat_escalates_to_critical, bool):
            raise ValueError("repeat_escalates_to_critical must be boolean")
        if self.idempotency_ttl_seconds <= 0:
            raise ValueError("idempotency_ttl_seconds must be positive")
        if self.idempotency_max_entries <= 0:
            raise ValueError("idempotency_max_entries must be positive")

    @staticmethod
    def _warn_policy_fallback(config_path: Path, reason: str) -> None:
        print(
            "Alert policy warning: "
            f"{config_path.name} ignored; using safe defaults ({reason})",
            file=sys.stderr,
            flush=True,
        )


@dataclass(frozen=True)
class ThermalEvidence:
    state: ThermalState
    human_detected: bool = False
    body_coverage: float = 0.0
    detected_part: str = "none"
    confidence_boost: float = 0.0
    raw_confidence_boost: float = 0.0
    thermal_confidence: float | None = None
    frame_timestamp: str | None = None
    frame_age_seconds: float | None = None
    frame_valid: bool = True
    model_available: bool | None = None
    model_confidence: float | None = None
    model_threshold: float | None = None
    heuristic_human_detected: bool | None = None
    heuristic_confidence_boost: float | None = None
    error: str | None = None


class AlertDecisionEngine:
    """
    Authoritative alert policy for Project Pi.

    `keyword_confidence` is the raw detector score kept for compatibility.
    `adjusted_voice_confidence` is the raw score after the SNR penalty.
    `final_confidence` is a rule-based fusion score:
    adjusted voice confidence + applied thermal boost. It is not a calibrated
    probability and should not be treated as one.
    """

    def __init__(
        self,
        policy: AlertPolicy | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.policy = policy or AlertPolicy.load()
        self.clock = clock or time.monotonic
        self.keyword_confidence = 0.0
        self.thermal_confidence_boost = 0.0
        self.noise_level_db = -90.0
        self.recent_alerts: deque[dict[str, Any]] = deque()
        self.false_positive_history: dict[str, deque[float]] = defaultdict(deque)
        self.repeat_history: dict[str, deque[float]] = defaultdict(deque)

    def reset(self) -> None:
        self.recent_alerts.clear()
        self.false_positive_history.clear()
        self.repeat_history.clear()

    def evaluate(
        self,
        keyword_event: dict[str, Any],
        thermal_frame: dict[str, Any] | None,
    ) -> dict[str, Any]:
        now = self.clock()
        keyword = str(keyword_event.get("keyword", "")).strip().lower()
        raw_voice_confidence = self._as_float(keyword_event.get("confidence"))
        self.keyword_confidence = raw_voice_confidence
        thermal = self._thermal_evidence(thermal_frame)
        self.thermal_confidence_boost = thermal.confidence_boost

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

        adjusted_voice_confidence = self._clamp01(
            raw_voice_confidence - noise_penalty,
        )
        final_confidence = self._clamp01(
            adjusted_voice_confidence + thermal.confidence_boost,
        )

        repeat_count = 0
        is_medium_voice = (
            self.policy.advisory_threshold
            <= raw_voice_confidence
            < self.policy.critical_threshold
        )
        if keyword and is_medium_voice:
            repeat_count = self._record_repeat(keyword, now)
        elif keyword:
            self._prune_repeat_history(keyword, now)

        state, modality, reason = self._classify(
            keyword_event=keyword_event,
            thermal=thermal,
            repeat_count=repeat_count,
            raw_voice_confidence=raw_voice_confidence,
            final_confidence=final_confidence,
        )
        alert_level = self._legacy_alert_level(state)
        should_alert = state in {
            DecisionState.ADVISORY,
            DecisionState.CONFIRMED,
            DecisionState.CRITICAL,
        }

        if should_alert:
            self._prune_recent_alerts(now)
            self.recent_alerts.append(
                {
                    "keyword": keyword,
                    "decision_state": state.value,
                    "final_confidence": final_confidence,
                    "timestamp_monotonic": now,
                    "thermal_state": thermal.state.value,
                }
            )
        else:
            self.false_positive_history[keyword].append(now)
            self._trim_false_positive_history(keyword, now)

        decision_factors = {
            "keyword_confidence": round(self.keyword_confidence, 4),
            "raw_voice_confidence": round(raw_voice_confidence, 4),
            "adjusted_voice_confidence": round(adjusted_voice_confidence, 4),
            "thermal_boost": round(thermal.confidence_boost, 4),
            "applied_thermal_boost": round(thermal.confidence_boost, 4),
            "raw_thermal_boost": round(thermal.raw_confidence_boost, 4),
            "thermal_confidence": (
                round(thermal.thermal_confidence, 4)
                if thermal.thermal_confidence is not None
                else None
            ),
            "noise_penalty": round(noise_penalty, 4),
            "legacy_fusion_score": round(final_confidence, 4),
            "legacy_fusion_note": (
                "adjusted_voice_confidence + applied_thermal_boost; "
                "not a calibrated probability"
            ),
            "human_detected": thermal.state == ThermalState.POSITIVE,
            "raw_human_detected": thermal.human_detected,
            "body_coverage": round(thermal.body_coverage, 4),
            "detected_part": thermal.detected_part,
            "thermal_state": thermal.state.value,
            "thermal_frame_timestamp": thermal.frame_timestamp,
            "thermal_frame_age_seconds": (
                round(thermal.frame_age_seconds, 4)
                if thermal.frame_age_seconds is not None
                else None
            ),
            "thermal_frame_valid": thermal.frame_valid,
            "thermal_model_available": thermal.model_available,
            "thermal_model_confidence": (
                round(thermal.model_confidence, 4)
                if thermal.model_confidence is not None
                else None
            ),
            "thermal_model_threshold": thermal.model_threshold,
            "heuristic_human_detected": thermal.heuristic_human_detected,
            "heuristic_confidence_boost": thermal.heuristic_confidence_boost,
            "thermal_error": thermal.error,
            "noise_level_db": round(self.noise_level_db, 2),
            "signal_level_db": round(signal_level_db, 2),
            "snr_db": round(snr_db, 2),
            "repeat_count": repeat_count,
            "repeat_window_seconds": self.policy.repeat_window_seconds,
            "repeat_required_count": self.policy.repeat_required_count,
            "policy_source": self.policy.policy_source,
        }

        return {
            "should_alert": should_alert,
            "final_confidence": round(final_confidence, 4),
            "decision_factors": decision_factors,
            # Legacy compatibility for the current Flutter app.
            "alert_level": alert_level,
            "decision_state": state.value,
            "decision_reason": reason,
            "alert_modality": modality.value,
            "thermal_state": thermal.state.value,
            "policy_version": self.policy.policy_version,
            "policy_source": self.policy.policy_source,
            "keyword_confidence": round(self.keyword_confidence, 4),
            "raw_voice_confidence": round(raw_voice_confidence, 4),
            "adjusted_voice_confidence": round(adjusted_voice_confidence, 4),
            "thermal_boost": round(thermal.confidence_boost, 4),
        }

    def _classify(
        self,
        *,
        keyword_event: dict[str, Any],
        thermal: ThermalEvidence,
        repeat_count: int,
        raw_voice_confidence: float,
        final_confidence: float,
    ) -> tuple[DecisionState, AlertModality, str]:
        if str(keyword_event.get("event", "")).strip().lower() == "system_fault":
            return (
                DecisionState.SYSTEM_FAULT,
                AlertModality.SENSOR_FAULT,
                "sensor_failure",
            )

        thermal_positive = thermal.state == ThermalState.POSITIVE
        modality = (
            AlertModality.VOICE_THERMAL
            if thermal_positive
            else AlertModality.VOICE_ONLY
        )

        if keyword_event.get("source") == "manual_button_single":
            return (
                DecisionState.ADVISORY,
                AlertModality.VOICE_ONLY,
                "manual_button_single_advisory",
            )

        if keyword_event.get("source") == "manual_button":
            return (
                DecisionState.CRITICAL,
                modality,
                "manual_button_emergency",
            )

        if raw_voice_confidence >= self.policy.critical_threshold:
            return (
                DecisionState.CRITICAL,
                modality,
                "voice_confirmed_by_thermal"
                if thermal_positive
                else "voice_high_confidence",
            )

        if raw_voice_confidence < self.policy.advisory_threshold:
            return (
                DecisionState.SUPPRESSED,
                AlertModality.VOICE_ONLY,
                "voice_below_threshold",
            )

        if (
            self.policy.repeat_escalates_to_critical
            and repeat_count >= self.policy.repeat_required_count
        ):
            return (
                DecisionState.CRITICAL,
                modality,
                "repeated_distress_escalation",
            )

        if final_confidence < self.policy.advisory_threshold:
            return (
                DecisionState.SUPPRESSED,
                AlertModality.VOICE_ONLY,
                "adjusted_voice_below_threshold",
            )

        if thermal_positive:
            return (
                DecisionState.CONFIRMED,
                AlertModality.VOICE_THERMAL,
                "voice_confirmed_by_thermal",
            )

        return (
            DecisionState.ADVISORY,
            AlertModality.VOICE_ONLY,
            self._advisory_reason(thermal.state),
        )

    def _thermal_evidence(self, thermal_frame: dict[str, Any] | None) -> ThermalEvidence:
        if not thermal_frame:
            return ThermalEvidence(state=ThermalState.UNAVAILABLE, frame_valid=False)

        explicit_state = self._explicit_thermal_state(thermal_frame.get("thermal_state"))
        frame_age_seconds = self._as_optional_float(
            self._first_present(
                thermal_frame,
                "frame_age_seconds",
                "thermal_frame_age_seconds",
            )
        )
        frame_timestamp = (
            str(thermal_frame.get("timestamp"))
            if thermal_frame.get("timestamp") is not None
            else None
        )
        frame_valid = self._frame_valid(thermal_frame)
        human_detected = self._as_bool(thermal_frame.get("human_detected", False))
        raw_boost = self._as_float(thermal_frame.get("confidence_boost"))
        error = self._first_present(
            thermal_frame,
            "thermal_error",
            "error",
            "analysis_error",
        )

        if explicit_state == ThermalState.UNAVAILABLE:
            state = ThermalState.UNAVAILABLE
        elif explicit_state == ThermalState.INVALID:
            state = ThermalState.INVALID
        elif not frame_valid:
            state = ThermalState.INVALID
        elif error:
            state = ThermalState.UNAVAILABLE
        elif self._is_stale(frame_age_seconds):
            state = ThermalState.STALE
        elif explicit_state is not None:
            state = explicit_state
        elif human_detected:
            state = ThermalState.POSITIVE
        else:
            state = ThermalState.NEGATIVE

        applied_boost = raw_boost if state == ThermalState.POSITIVE else 0.0
        details = thermal_frame.get("details")
        details = details if isinstance(details, dict) else {}

        model_confidence = self._as_optional_float(
            thermal_frame.get("thermal_model_confidence")
        )
        return ThermalEvidence(
            state=state,
            human_detected=human_detected,
            body_coverage=self._as_float(thermal_frame.get("body_coverage")),
            detected_part=str(thermal_frame.get("detected_part") or "none"),
            confidence_boost=applied_boost,
            raw_confidence_boost=raw_boost,
            thermal_confidence=self._first_not_none(
                self._as_optional_float(thermal_frame.get("thermal_confidence")),
                model_confidence,
            ),
            frame_timestamp=frame_timestamp,
            frame_age_seconds=frame_age_seconds,
            frame_valid=frame_valid,
            model_available=self._as_optional_bool(
                thermal_frame.get("thermal_model_available")
            ),
            model_confidence=model_confidence,
            model_threshold=self._as_optional_float(
                thermal_frame.get("thermal_model_threshold")
            ),
            heuristic_human_detected=self._as_optional_bool(
                details.get("heuristic_human_detected")
            ),
            heuristic_confidence_boost=self._as_optional_float(
                details.get("heuristic_confidence_boost")
            ),
            error=str(error) if error else None,
        )

    def _record_repeat(self, keyword: str, now: float) -> int:
        history = self.repeat_history[keyword]
        while history and now - history[0] > self.policy.repeat_window_seconds:
            history.popleft()
        history.append(now)
        return len(history)

    def _prune_repeat_history(self, keyword: str, now: float) -> None:
        history = self.repeat_history[keyword]
        while history and now - history[0] > self.policy.repeat_window_seconds:
            history.popleft()

    def should_suppress_as_false_positive(self, keyword: str, confidence: float) -> bool:
        now = self.clock()
        self._trim_false_positive_history(keyword, now)
        repeated_low_confidence = len(self.false_positive_history[keyword]) >= 3
        recently_alerted_same_keyword = any(
            entry["keyword"] == keyword
            and now - entry["timestamp_monotonic"] < 10.0
            for entry in self.recent_alerts
        )
        return confidence < 0.75 and repeated_low_confidence and recently_alerted_same_keyword

    def _prune_recent_alerts(self, now: float) -> None:
        while (
            self.recent_alerts
            and now - self.recent_alerts[0]["timestamp_monotonic"] > 30.0
        ):
            self.recent_alerts.popleft()

    def _trim_false_positive_history(self, keyword: str, now: float) -> None:
        history = self.false_positive_history[keyword]
        while history and now - history[0] > 30.0:
            history.popleft()

    def _is_stale(self, frame_age_seconds: float | None) -> bool:
        return (
            frame_age_seconds is not None
            and frame_age_seconds > self.policy.thermal_freshness_seconds
        )

    @staticmethod
    def _legacy_alert_level(state: DecisionState) -> str:
        # Compatibility mapping for the current Flutter app. The authoritative
        # state remains `decision_state`; this alias can be removed after a
        # Flutter migration.
        if state == DecisionState.SUPPRESSED:
            return "none"
        if state == DecisionState.ADVISORY:
            return "visual_only"
        if state in {DecisionState.CONFIRMED, DecisionState.CRITICAL}:
            return "full_alert"
        return "none"

    @staticmethod
    def _advisory_reason(state: ThermalState) -> str:
        return {
            ThermalState.NEGATIVE: "thermal_negative",
            ThermalState.UNAVAILABLE: "thermal_unavailable",
            ThermalState.STALE: "thermal_stale",
            ThermalState.INVALID: "thermal_invalid",
            ThermalState.POSITIVE: "voice_advisory",
        }[state]

    @staticmethod
    def _explicit_thermal_state(value: object) -> ThermalState | None:
        if value is None:
            return None
        try:
            return ThermalState(str(value).strip().lower())
        except ValueError:
            return ThermalState.INVALID

    @classmethod
    def _frame_valid(cls, thermal_frame: dict[str, Any]) -> bool:
        explicit_frame_valid = None
        if "frame_valid" in thermal_frame:
            explicit_frame_valid = cls._as_bool(thermal_frame.get("frame_valid"))
        temperatures = thermal_frame.get("temperatures")
        if temperatures is not None:
            return (
                cls._temperature_frame_valid(temperatures)
                and explicit_frame_valid is not False
            )
        if explicit_frame_valid is not None:
            return explicit_frame_valid
        return True

    @staticmethod
    def _temperature_frame_valid(temperatures: Any) -> bool:
        try:
            values = list(temperatures)
        except TypeError:
            return False
        if len(values) != 768:
            return False
        for value in values:
            try:
                if not math.isfinite(float(value)):
                    return False
            except (TypeError, ValueError):
                return False
        return True

    @staticmethod
    def _noise_penalty_for_snr(snr_db: float) -> float:
        if snr_db >= 20.0:
            return 0.0
        if snr_db >= 10.0:
            return 0.05
        return 0.10

    @staticmethod
    def _clamp01(value: float) -> float:
        return min(max(value, 0.0), 1.0)

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

    @classmethod
    def _as_optional_float(cls, value: Any) -> float | None:
        if value is None:
            return None
        return cls._as_float(value)

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        normalized = str(value).strip().lower()
        return normalized in {"1", "true", "yes", "on"}

    @classmethod
    def _as_optional_bool(cls, value: Any) -> bool | None:
        if value is None:
            return None
        return cls._as_bool(value)

    @staticmethod
    def _first_present(payload: dict[str, Any], *keys: str) -> object | None:
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _first_not_none(*values: Any) -> Any:
        for value in values:
            if value is not None:
                return value
        return None
