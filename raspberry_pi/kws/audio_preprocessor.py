#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


MODEL_PATH = "/home/thesis/Project_Pi/raspberry_pi/kws/openwakeword_models/"
DEFAULT_WAKE_WORD_MODELS = [
    MODEL_PATH + "tulong.tflite",
    MODEL_PATH + "help.tflite",
]


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
        self.wake_word_models = (
            DEFAULT_WAKE_WORD_MODELS.copy()
            if wake_word_models is None
            else wake_word_models
        )
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

    def process(self, audio_frame: np.ndarray) -> dict[str, object]:
        frame = np.asarray(audio_frame, dtype=np.int16)
        if not self.enabled:
            return self._result(
                frame,
                is_speech=True,
                vad_score=1.0,
                available=False,
                error="disabled",
            )

        if self.model is None:
            return self._result(
                frame,
                is_speech=True,
                vad_score=1.0,
                available=False,
                error=self.error or "openwakeword unavailable",
            )

        try:
            prediction_frame = self._prediction_frame(frame)
            prediction = self.model.predict(prediction_frame)
        except Exception as exc:  # pragma: no cover - hardware/runtime path
            return self._result(
                frame,
                is_speech=True,
                vad_score=1.0,
                available=False,
                error=str(exc),
            )

        vad_score = self._score_from_prediction(prediction, "vad")
        if "vad" not in prediction:
            vad_score = self._latest_model_vad_score()
        is_speech = vad_score >= self.vad_threshold
        wake_words: list[dict[str, object]] = []

        if is_speech and self.emit_wake_words:
            for model_name, raw_score in prediction.items():
                if model_name == "vad":
                    continue
                score = self._as_float(raw_score)
                if score >= self.wake_word_threshold:
                    wake_words.append(
                        {
                            "name": self._keyword_name(str(model_name)),
                            "score": score,
                        }
                    )

        return self._result(
            frame,
            is_speech=is_speech,
            wake_words=wake_words,
            vad_score=vad_score,
            available=True,
        )

    def to_metrics(self, result: dict[str, object]) -> dict[str, object]:
        wake_words = self._wake_words_from_result(result)
        top_wake_word = max(
            wake_words,
            key=lambda wake_word: self._as_float(wake_word.get("score", 0.0)),
            default=None,
        )
        payload: dict[str, object] = {
            "openwakeword_available": bool(result.get("available", False)),
            "openwakeword_vad_score": round(
                self._as_float(result.get("vad_score", 0.0)),
                4,
            ),
            "openwakeword_is_speech": bool(result.get("is_speech", False)),
            "openwakeword_wake_words": wake_words,
            "openwakeword_wake_word": (
                top_wake_word.get("name") if top_wake_word else None
            ),
            "openwakeword_wake_word_score": round(
                self._as_float(top_wake_word.get("score", 0.0))
                if top_wake_word
                else 0.0,
                4,
            ),
        }
        error = result.get("error")
        if error:
            payload["openwakeword_error"] = str(error)
        return payload

    @staticmethod
    def _result(
        cleaned_audio: np.ndarray,
        *,
        is_speech: bool,
        vad_score: float,
        available: bool,
        wake_words: list[dict[str, object]] | None = None,
        error: str | None = None,
    ) -> dict[str, object]:
        return {
            "cleaned_audio": cleaned_audio,
            "is_speech": is_speech,
            "wake_words": wake_words or [],
            "vad_score": vad_score,
            "available": available,
            "error": error,
        }

    @staticmethod
    def _wake_words_from_result(result: dict[str, object]) -> list[dict[str, object]]:
        wake_words = result.get("wake_words", [])
        if not isinstance(wake_words, list):
            return []
        return [wake_word for wake_word in wake_words if isinstance(wake_word, dict)]

    @staticmethod
    def _keyword_name(model_name: str) -> str:
        keyword = Path(model_name).stem
        return " ".join(
            keyword.replace("_", " ").replace("-", " ").strip().lower().split()
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
