#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np


DEFAULT_MODEL_ID = "Khalsuu/filipino-wav2vec2-l-xls-r-300m-official"
DEFAULT_SAMPLE_RATE = 16000
VERIFIED_CONFIDENCE = 0.95

LOGGER = logging.getLogger(__name__)


class Wav2Vec2Verifier:
    """Second-pass Filipino ASR verifier for low-confidence Vosk detections."""

    def __init__(
        self,
        model_path: str | None = None,
        *,
        onnx_path: str | Path | None = None,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
    ) -> None:
        self.model_path = model_path or os.getenv("WAV2VEC2_MODEL_PATH", DEFAULT_MODEL_ID)
        self.sample_rate = int(sample_rate)
        self.processor: Any | None = None
        self.model: Any | None = None
        self.session: Any | None = None
        self.torch: Any | None = None
        self.device = os.getenv("WAV2VEC2_DEVICE", "cpu")
        self.backend = "unavailable"
        self.available = False
        self.error: str | None = None

        self._load(onnx_path)

    def verify(self, audio_chunk: np.ndarray, keyword: str) -> tuple[bool, float]:
        if not self.available:
            return False, 0.0

        normalized_keyword = self._normalize_text(keyword)
        if not normalized_keyword:
            return False, 0.0

        try:
            audio = self._prepare_audio(audio_chunk)
            if audio.size == 0:
                return False, 0.0
            transcript = self._transcribe(audio)
        except Exception as exc:  # pragma: no cover - runtime model failures
            LOGGER.warning("wav2vec2 verifier failed for '%s': %s", keyword, exc)
            return False, 0.0

        normalized_transcript = self._normalize_text(transcript)
        if normalized_keyword in normalized_transcript:
            LOGGER.info(
                "wav2vec2 verified '%s' in transcript '%s'",
                normalized_keyword,
                normalized_transcript,
            )
            return True, VERIFIED_CONFIDENCE

        LOGGER.info(
            "wav2vec2 rejected '%s'; transcript='%s'",
            normalized_keyword,
            normalized_transcript,
        )
        return False, 0.0

    def _load(self, onnx_path: str | Path | None) -> None:
        selected_onnx_path = self._resolve_onnx_path(onnx_path)
        if selected_onnx_path is not None and selected_onnx_path.exists():
            try:
                self._load_onnx(selected_onnx_path)
                return
            except Exception as exc:  # pragma: no cover - optional ONNX runtime path
                LOGGER.warning(
                    "wav2vec2 ONNX load failed from %s; falling back to transformers: %s",
                    selected_onnx_path,
                    exc,
                )

        try:
            self._load_transformers()
        except Exception as exc:  # pragma: no cover - optional Pi dependency
            self.error = str(exc)
            self.available = False
            self.backend = "unavailable"
            LOGGER.warning(
                "wav2vec2 verifier disabled; failed to load %s: %s",
                self.model_path,
                exc,
            )

    def _load_transformers(self) -> None:
        import torch  # pylint: disable=import-outside-toplevel
        from transformers import (  # pylint: disable=import-outside-toplevel
            AutoModelForCTC,
            AutoProcessor,
        )

        self.processor = AutoProcessor.from_pretrained(self.model_path)
        self.model = AutoModelForCTC.from_pretrained(self.model_path)
        if self.device != "cpu":
            self.model.to(self.device)
        self.model.eval()
        self.torch = torch
        self.backend = "transformers"
        self.available = True
        LOGGER.info(
            "wav2vec2 verifier loaded with transformers model %s on %s",
            self.model_path,
            self.device,
        )

    def _load_onnx(self, onnx_path: Path) -> None:
        import onnxruntime as ort  # pylint: disable=import-outside-toplevel
        from transformers import AutoProcessor  # pylint: disable=import-outside-toplevel

        self.processor = AutoProcessor.from_pretrained(self.model_path)
        self.session = ort.InferenceSession(
            str(onnx_path),
            providers=["CPUExecutionProvider"],
        )
        self.backend = "onnx"
        self.available = True
        LOGGER.info("wav2vec2 verifier loaded with ONNX model %s", onnx_path)

    def _transcribe(self, audio: np.ndarray) -> str:
        if self.backend == "onnx":
            return self._transcribe_onnx(audio)
        return self._transcribe_transformers(audio)

    def _transcribe_transformers(self, audio: np.ndarray) -> str:
        if self.processor is None or self.model is None or self.torch is None:
            return ""

        inputs = self.processor(
            audio,
            sampling_rate=self.sample_rate,
            return_tensors="pt",
            padding=True,
        )
        inputs = {
            name: value.to(self.device) if hasattr(value, "to") else value
            for name, value in inputs.items()
        }
        with self.torch.no_grad():
            logits = self.model(**inputs).logits
        predicted_ids = self.torch.argmax(logits, dim=-1)
        return str(self.processor.batch_decode(predicted_ids)[0])

    def _transcribe_onnx(self, audio: np.ndarray) -> str:
        if self.processor is None or self.session is None:
            return ""

        inputs = self.processor(
            audio,
            sampling_rate=self.sample_rate,
            return_tensors="np",
            padding=True,
        )
        ort_inputs: dict[str, np.ndarray] = {}
        for model_input in self.session.get_inputs():
            value = inputs.get(model_input.name)
            if value is not None:
                ort_inputs[model_input.name] = np.asarray(value)

        logits = self.session.run(None, ort_inputs)[0]
        predicted_ids = np.argmax(logits, axis=-1)
        return str(self.processor.batch_decode(predicted_ids)[0])

    @staticmethod
    def _prepare_audio(audio_chunk: np.ndarray) -> np.ndarray:
        audio = np.asarray(audio_chunk).reshape(-1)
        if audio.size == 0:
            return np.asarray([], dtype=np.float32)

        audio = audio.astype(np.float32, copy=False)
        audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
        if float(np.max(np.abs(audio))) > 1.5:
            audio = audio / 32768.0
        return np.clip(audio, -1.0, 1.0).astype(np.float32, copy=False)

    @staticmethod
    def _normalize_text(text: str) -> str:
        parts = (
            "".join(char for char in token.lower() if char.isalpha())
            for token in str(text).split()
        )
        return " ".join(part for part in parts if part)

    @staticmethod
    def _resolve_onnx_path(onnx_path: str | Path | None) -> Path | None:
        configured = onnx_path or os.getenv("WAV2VEC2_ONNX_PATH")
        if configured:
            return Path(configured).expanduser()
        return Path(__file__).with_name("filipino_wav2vec2.onnx")
