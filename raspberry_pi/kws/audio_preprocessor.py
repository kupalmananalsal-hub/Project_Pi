#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class AudioPreprocessorResult:
    cleaned_audio: np.ndarray
    is_speech: bool
    wake_word: str | None
    wake_word_score: float
    vad_score: float
    available: bool
    error: str | None = None

    def to_metrics(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "openwakeword_available": self.available,
            "openwakeword_vad_score": round(self.vad_score, 4),
            "openwakeword_is_speech": self.is_speech,
            "openwakeword_wake_word": self.wake_word,
            "openwakeword_wake_word_score": round(self.wake_word_score, 4),
        }
        if self.error:
            payload["openwakeword_error"] = self.error
        return payload


class AudioPreprocessor:
    """
    Optional openWakeWord wrapper for wake-word scoring and VAD gating.

    openWakeWord's Speex noise suppression is enabled inside its own prediction
    path. The public API returns wake-word/VAD scores, not a separate cleaned
    PCM buffer, so `cleaned_audio` intentionally returns the incoming frame.
    The existing Project Pi NoiseSuppressor still provides the PCM stream that
    is forwarded to Vosk and Snowboy.
    """

    def __init__(
        self,
        wake_word_models: list[str] | None = None,
        *,
        enabled: bool = True,
        vad_threshold: float = 0.5,
        wake_word_threshold: float = 0.5,
        enable_speex_noise_suppression: bool = True,
    ) -> None:
        self.enabled = enabled
        self.vad_threshold = float(np.clip(vad_threshold, 0.0, 1.0))
        self.wake_word_threshold = float(np.clip(wake_word_threshold, 0.0, 1.0))
        self.wake_word_models = wake_word_models or []
        self.emit_wake_words = bool(self.wake_word_models)
        self.enable_speex_noise_suppression = enable_speex_noise_suppression
        self.model: Any | None = None
        self.available = False
        self.error: str | None = None

        if not self.enabled:
            self.error = "disabled"
            return

        try:
            from openwakeword.model import Model

            self.model = Model(
                wakeword_models=self.wake_word_models,
                enable_speex_noise_suppression=enable_speex_noise_suppression,
                vad_threshold=self.vad_threshold,
            )
            self.available = True
        except Exception as exc:  # pragma: no cover - optional Pi dependency
            self.error = str(exc)

    def process(self, audio_frame: np.ndarray) -> AudioPreprocessorResult:
        frame = np.asarray(audio_frame, dtype=np.int16)
        if not self.enabled:
            return AudioPreprocessorResult(
                cleaned_audio=frame,
                is_speech=True,
                wake_word=None,
                wake_word_score=0.0,
                vad_score=1.0,
                available=False,
                error="disabled",
            )

        if self.model is None:
            return AudioPreprocessorResult(
                cleaned_audio=frame,
                is_speech=True,
                wake_word=None,
                wake_word_score=0.0,
                vad_score=1.0,
                available=False,
                error=self.error or "openwakeword unavailable",
            )

        try:
            prediction_frame = self._prediction_frame(frame)
            prediction = self.model.predict(prediction_frame)
        except Exception as exc:  # pragma: no cover - hardware/runtime path
            return AudioPreprocessorResult(
                cleaned_audio=frame,
                is_speech=True,
                wake_word=None,
                wake_word_score=0.0,
                vad_score=1.0,
                available=False,
                error=str(exc),
            )

        vad_score = self._score_from_prediction(prediction, "vad")
        if "vad" not in prediction:
            vad_score = self._latest_model_vad_score()
        is_speech = vad_score >= self.vad_threshold
        wake_word = None
        wake_word_score = 0.0

        if self.emit_wake_words:
            for model_name, raw_score in prediction.items():
                if model_name == "vad":
                    continue
                score = self._as_float(raw_score)
                if score >= self.wake_word_threshold and score > wake_word_score:
                    wake_word = str(model_name)
                    wake_word_score = score

        return AudioPreprocessorResult(
            cleaned_audio=frame,
            is_speech=is_speech,
            wake_word=wake_word,
            wake_word_score=wake_word_score,
            vad_score=vad_score,
            available=True,
        )

    @staticmethod
    def _score_from_prediction(prediction: dict[str, Any], key: str) -> float:
        return AudioPreprocessor._as_float(prediction.get(key, 0.0))

    def _latest_model_vad_score(self) -> float:
        vad = getattr(self.model, "vad", None)
        buffer = getattr(vad, "prediction_buffer", None)
        if not buffer:
            return 1.0 if self.vad_threshold <= 0 else 0.0
        try:
            return float(max(list(buffer)[-4:]))
        except (TypeError, ValueError):
            return 0.0

    def _prediction_frame(self, frame: np.ndarray) -> np.ndarray:
        if not self.enable_speex_noise_suppression or frame.size % 160 == 0:
            return frame
        next_size = ((frame.size // 160) + 1) * 160
        padded = np.zeros(next_size, dtype=np.int16)
        padded[: frame.size] = frame
        return padded

    @staticmethod
    def _as_float(value: Any) -> float:
        try:
            if isinstance(value, (list, tuple, np.ndarray)):
                if len(value) == 0:
                    return 0.0
                return float(np.asarray(value).flatten()[-1])
            return float(value)
        except (TypeError, ValueError):
            return 0.0
