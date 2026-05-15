#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


INT16_MAX = 32768.0
DEFAULT_CONFIG_PATH = Path("/tmp/project_pi_noise_suppression.json")


@dataclass(frozen=True)
class NoiseMetrics:
    noise_level_db: float
    signal_level_db: float
    snr_db: float
    reduction_db: float
    profile_ready: bool

    def to_dict(self) -> dict[str, float | bool]:
        return {
            "noise_floor_db": round(self.noise_level_db, 2),
            "noise_level_db": round(self.noise_level_db, 2),
            "signal_level_db": round(self.signal_level_db, 2),
            "snr_estimate": round(self.snr_db, 2),
            "snr_db": round(self.snr_db, 2),
            "reduction_db": round(self.reduction_db, 2),
            "noise_reduction_db": round(self.reduction_db, 2),
            "noise_suppression_active": self.profile_ready,
        }


@dataclass
class NoiseSuppressionConfig:
    active: bool = True
    strength: float = 0.5
    sensitivity: float = 0.5
    snowboy_sensitivity: float | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "NoiseSuppressionConfig":
        return cls(
            active=_as_bool(payload.get("active"), True),
            strength=_clamp(payload.get("strength"), 0.5),
            sensitivity=_clamp(payload.get("sensitivity"), 0.5),
            snowboy_sensitivity=_optional_clamp(payload.get("snowboy_sensitivity")),
        )


class NoiseSuppressionConfigStore:
    def __init__(self, path: Path | str = DEFAULT_CONFIG_PATH):
        self.path = Path(path)

    def load(self) -> NoiseSuppressionConfig:
        if not self.path.exists():
            return NoiseSuppressionConfig()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return NoiseSuppressionConfig()
        if not isinstance(payload, dict):
            return NoiseSuppressionConfig()
        return NoiseSuppressionConfig.from_dict(payload)

    def save(self, config: NoiseSuppressionConfig) -> NoiseSuppressionConfig:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
        return config


class NoiseSuppressor:
    """
    Real-time noise suppression with adjustable strength and sensitivity.

    - `strength`: how much background energy to subtract
    - `sensitivity`: how much low-volume / wide-band speech detail to preserve
    - preserves human fundamentals (~85-400 Hz) and speech formants (300-3400 Hz)
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        noise_reduction_strength: float = 0.5,
        sensitivity: float = 0.5,
        active: bool = True,
        noise_profile_seconds: float = 2.0,
        profile_update_rate: float = 0.05,
        min_gain: float = 0.06,
    ) -> None:
        self.sample_rate = sample_rate
        self.active = active
        self.strength = _clamp(noise_reduction_strength, 0.5)
        self.sensitivity = _clamp(sensitivity, 0.5)
        self.noise_profile_seconds = max(0.25, float(noise_profile_seconds))
        self.profile_update_rate = float(np.clip(profile_update_rate, 0.0, 1.0))
        self.min_gain = float(np.clip(min_gain, 0.0, 1.0))
        self.noise_floor_db = -60.0
        self.snr_estimate = 20.0
        self.reduction_db = 0.0
        self._capture_buffer = np.empty(0, dtype=np.float32)
        self._noise_spectrum: np.ndarray | None = None
        self._noise_rms = 0.0
        self._window_cache: dict[int, np.ndarray] = {}
        self._last_metrics = NoiseMetrics(
            noise_level_db=-90.0,
            signal_level_db=-90.0,
            snr_db=0.0,
            reduction_db=0.0,
            profile_ready=False,
        )

    @property
    def profile_ready(self) -> bool:
        return self._noise_spectrum is not None

    @property
    def last_metrics(self) -> NoiseMetrics:
        return self._last_metrics

    def set_strength(self, value: float) -> None:
        self.strength = _clamp(value, self.strength)

    def set_sensitivity(self, value: float) -> None:
        self.sensitivity = _clamp(value, self.sensitivity)

    def set_active(self, value: bool) -> None:
        self.active = bool(value)

    def apply_config(self, config: NoiseSuppressionConfig) -> None:
        self.set_active(config.active)
        self.set_strength(config.strength)
        self.set_sensitivity(config.sensitivity)

    def export_settings(self) -> dict[str, float | bool]:
        metrics = self.get_last_metrics()
        return {
            "active": self.active,
            "strength": round(self.strength, 3),
            "sensitivity": round(self.sensitivity, 3),
            "noise_floor_db": metrics["noise_floor_db"],
            "snr_estimate": metrics["snr_estimate"],
            "reduction_db": metrics["reduction_db"],
        }

    def capture_noise_profile(
        self,
        audio_chunk: bytes | np.ndarray | list[int] | list[float],
        duration_seconds: float | None = None,
    ) -> bool:
        samples = self._prepare_samples(audio_chunk)
        if samples.size == 0:
            return self.profile_ready

        required_seconds = (
            self.noise_profile_seconds
            if duration_seconds is None
            else max(0.1, float(duration_seconds))
        )
        required_samples = int(self.sample_rate * required_seconds)
        self._capture_buffer = np.concatenate([self._capture_buffer, samples])
        if self._capture_buffer.size < required_samples:
            self._update_metrics(
                raw_signal=samples,
                cleaned_signal=samples,
                profile_ready=False,
            )
            return False

        capture = self._capture_buffer[:required_samples]
        self._noise_spectrum = self._compute_noise_spectrum(capture)
        self._noise_rms = self._rms(capture)
        self._capture_buffer = np.empty(0, dtype=np.float32)
        self._update_metrics(
            raw_signal=capture,
            cleaned_signal=capture,
            profile_ready=True,
        )
        return True

    def process(
        self,
        audio_chunk: bytes | np.ndarray | list[int] | list[float],
    ) -> tuple[np.ndarray, dict[str, float | bool]]:
        samples = self._prepare_samples(audio_chunk)
        if samples.size == 0:
            return np.empty(0, dtype=np.int16), self.get_last_metrics()

        if not self.profile_ready:
            self.capture_noise_profile(samples)
            passthrough = np.clip(samples, -32768, 32767).astype(np.int16)
            return passthrough, self.get_last_metrics()

        if not self.active or self.strength <= 0.001:
            self._update_metrics(
                raw_signal=samples,
                cleaned_signal=samples,
                profile_ready=True,
            )
            passthrough = np.clip(samples, -32768, 32767).astype(np.int16)
            return passthrough, self.get_last_metrics()

        spectrum = np.fft.rfft(self._windowed(samples))
        magnitude = np.abs(spectrum)
        phase = np.angle(spectrum)
        noise_spectrum = self._match_noise_spectrum(magnitude.size)
        frequencies = np.fft.rfftfreq(samples.size, d=1.0 / self.sample_rate)

        fundamental_mask = (frequencies >= 85.0) & (frequencies <= 400.0)
        formant_mask = (frequencies >= 300.0) & (frequencies <= 3400.0)
        voice_mask = fundamental_mask | formant_mask

        speech_preservation = 0.35 + (self.sensitivity * 0.65)
        non_voice_preservation = 0.04 + (self.sensitivity * 0.36)

        band_preservation = np.where(
            voice_mask,
            speech_preservation,
            non_voice_preservation,
        )
        subtract_strength = self.strength * (1.18 - (self.sensitivity * 0.55))
        noise_floor = noise_spectrum * subtract_strength
        cleaned_magnitude = magnitude - (noise_floor * (1.0 - band_preservation))
        cleaned_magnitude = np.maximum(cleaned_magnitude, magnitude * self.min_gain)

        cleaned_spectrum = cleaned_magnitude * np.exp(1j * phase)
        cleaned_signal = np.fft.irfft(cleaned_spectrum, n=samples.size).real
        cleaned_signal = np.clip(cleaned_signal, -32768, 32767)

        self._update_metrics(
            raw_signal=samples,
            cleaned_signal=cleaned_signal,
            profile_ready=True,
        )
        return cleaned_signal.astype(np.int16), self.get_last_metrics()

    def suppress_noise(
        self,
        audio_chunk: bytes | np.ndarray | list[int] | list[float],
    ) -> np.ndarray:
        cleaned, _ = self.process(audio_chunk)
        return cleaned

    def update_noise_profile(
        self,
        audio_chunk: bytes | np.ndarray | list[int] | list[float],
        is_speech: bool = False,
    ) -> None:
        samples = self._prepare_samples(audio_chunk)
        if samples.size == 0:
            return

        if not self.profile_ready:
            self.capture_noise_profile(samples)
            return

        if is_speech:
            return

        current = self._compute_noise_spectrum(samples)
        if current.size == 0:
            return

        matched = self._match_noise_spectrum(current.size)
        alpha = self.profile_update_rate
        self._noise_spectrum = ((1.0 - alpha) * matched) + (alpha * current)
        self._noise_rms = ((1.0 - alpha) * self._noise_rms) + (alpha * self._rms(samples))

    def get_last_metrics(self) -> dict[str, float | bool]:
        metrics = self.last_metrics.to_dict()
        metrics["active"] = self.active
        metrics["strength"] = round(self.strength, 3)
        metrics["sensitivity"] = round(self.sensitivity, 3)
        return metrics

    def _prepare_samples(
        self,
        audio_chunk: bytes | np.ndarray | list[int] | list[float],
    ) -> np.ndarray:
        if isinstance(audio_chunk, bytes):
            samples = np.frombuffer(audio_chunk, dtype=np.int16)
            return samples.astype(np.float32)
        if isinstance(audio_chunk, np.ndarray):
            return audio_chunk.astype(np.float32, copy=False)
        return np.asarray(audio_chunk, dtype=np.float32)

    def _compute_noise_spectrum(self, samples: np.ndarray) -> np.ndarray:
        if samples.size == 0:
            return np.empty(0, dtype=np.float32)
        spectrum = np.fft.rfft(self._windowed(samples))
        return np.abs(spectrum).astype(np.float32)

    def _windowed(self, samples: np.ndarray) -> np.ndarray:
        window = self._window_cache.get(samples.size)
        if window is None:
            window = np.hanning(samples.size).astype(np.float32)
            self._window_cache[samples.size] = window
        return samples * window

    def _match_noise_spectrum(self, size: int) -> np.ndarray:
        if self._noise_spectrum is None or self._noise_spectrum.size == size:
            return (
                self._noise_spectrum
                if self._noise_spectrum is not None
                else np.zeros(size, dtype=np.float32)
            )

        x_old = np.linspace(0.0, 1.0, num=self._noise_spectrum.size)
        x_new = np.linspace(0.0, 1.0, num=size)
        return np.interp(x_new, x_old, self._noise_spectrum).astype(np.float32)

    def _update_metrics(
        self,
        *,
        raw_signal: np.ndarray,
        cleaned_signal: np.ndarray,
        profile_ready: bool,
    ) -> None:
        signal_rms = self._rms(cleaned_signal)
        noise_rms = self._noise_rms if profile_ready else self._rms(raw_signal)
        signal_db = self._rms_db(signal_rms)
        noise_db = self._rms_db(noise_rms)
        snr_db = signal_db - noise_db
        raw_db = self._rms_db(self._rms(raw_signal))
        reduction_db = max(0.0, raw_db - signal_db)

        self.noise_floor_db = noise_db
        self.snr_estimate = snr_db
        self.reduction_db = reduction_db
        self._last_metrics = NoiseMetrics(
            noise_level_db=noise_db,
            signal_level_db=signal_db,
            snr_db=snr_db,
            reduction_db=reduction_db,
            profile_ready=profile_ready and self.active,
        )

    @staticmethod
    def _rms(signal: np.ndarray) -> float:
        if signal.size == 0:
            return 0.0
        normalized = signal.astype(np.float32) / INT16_MAX
        return float(np.sqrt(np.mean(np.square(normalized))))

    @staticmethod
    def _rms_db(rms: float) -> float:
        if rms <= 1e-9:
            return -90.0
        return 20.0 * math.log10(rms)


def _clamp(value: object, fallback: float) -> float:
    try:
        return float(np.clip(float(value), 0.0, 1.0))
    except (TypeError, ValueError):
        return fallback


def _optional_clamp(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(np.clip(float(value), 0.0, 1.0))
    except (TypeError, ValueError):
        return None


def _as_bool(value: object, fallback: bool) -> bool:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
