#!/usr/bin/env python3
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


INT16_MAX = 32768.0


@dataclass(frozen=True)
class NoiseMetrics:
    noise_level_db: float
    signal_level_db: float
    snr_db: float
    reduction_db: float
    profile_ready: bool

    def to_dict(self) -> dict[str, float | bool]:
        return {
            "noise_level_db": round(self.noise_level_db, 2),
            "signal_level_db": round(self.signal_level_db, 2),
            "snr_db": round(self.snr_db, 2),
            "noise_reduction_db": round(self.reduction_db, 2),
            "noise_suppression_active": self.profile_ready,
        }


class NoiseSuppressor:
    """
    Lightweight real-time noise suppressor for keyword spotting.

    The implementation uses:
    - a startup ambient-noise capture window
    - FFT-domain spectral subtraction
    - speech-band emphasis (300 Hz to 3400 Hz)
    - adaptive noise profile updates while speech is absent
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        noise_reduction_strength: float = 0.7,
        noise_profile_seconds: float = 2.0,
        profile_update_rate: float = 0.05,
        speech_min_hz: float = 300.0,
        speech_max_hz: float = 3400.0,
        min_gain: float = 0.08,
    ) -> None:
        self.sample_rate = sample_rate
        self.noise_reduction_strength = float(
            np.clip(noise_reduction_strength, 0.0, 1.0)
        )
        self.noise_profile_seconds = max(0.25, float(noise_profile_seconds))
        self.profile_update_rate = float(np.clip(profile_update_rate, 0.0, 1.0))
        self.speech_min_hz = speech_min_hz
        self.speech_max_hz = speech_max_hz
        self.min_gain = float(np.clip(min_gain, 0.0, 1.0))
        self._capture_buffer = np.empty(0, dtype=np.float32)
        self._noise_spectrum: np.ndarray | None = None
        self._noise_rms = 0.0
        self._window: np.ndarray | None = None
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

    def suppress_noise(
        self,
        audio_chunk: bytes | np.ndarray | list[int] | list[float],
    ) -> np.ndarray:
        samples = self._prepare_samples(audio_chunk)
        if samples.size == 0:
            return np.empty(0, dtype=np.int16)

        if not self.profile_ready:
            self.capture_noise_profile(samples)
            return np.clip(samples, -32768, 32767).astype(np.int16)

        spectrum = np.fft.rfft(self._windowed(samples))
        magnitude = np.abs(spectrum)
        phase = np.angle(spectrum)
        noise_spectrum = self._match_noise_spectrum(magnitude.size)
        frequencies = np.fft.rfftfreq(samples.size, d=1.0 / self.sample_rate)

        speech_mask = (frequencies >= self.speech_min_hz) & (
            frequencies <= self.speech_max_hz
        )
        band_strength = np.where(speech_mask, 1.0, 0.75)
        noise_floor = noise_spectrum * (0.65 + self.noise_reduction_strength)
        cleaned_magnitude = magnitude - (noise_floor * band_strength)
        cleaned_magnitude = np.maximum(cleaned_magnitude, magnitude * self.min_gain)

        cleaned_spectrum = cleaned_magnitude * np.exp(1j * phase)
        cleaned_signal = np.fft.irfft(cleaned_spectrum, n=samples.size).real
        cleaned_signal = np.clip(cleaned_signal, -32768, 32767)

        self._update_metrics(
            raw_signal=samples,
            cleaned_signal=cleaned_signal,
            profile_ready=True,
        )
        return cleaned_signal.astype(np.int16)

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
        return self.last_metrics.to_dict()

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
        if self._window is None or self._window.size != samples.size:
            self._window = np.hanning(samples.size).astype(np.float32)
        return samples * self._window

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
        self._last_metrics = NoiseMetrics(
            noise_level_db=noise_db,
            signal_level_db=signal_db,
            snr_db=snr_db,
            reduction_db=reduction_db,
            profile_ready=profile_ready,
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
