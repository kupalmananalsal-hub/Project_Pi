#!/usr/bin/env python3
from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


LOGGER = logging.getLogger(__name__)
DEFAULT_MODEL_PATH = Path(
    "/home/thesis/Project_Pi/raspberry_pi/thermal/models/thermal_human_detector.tflite"
)


@dataclass(frozen=True)
class ThermalCluster:
    center_x: float
    center_y: float
    pixel_count: int
    min_temp_c: float
    max_temp_c: float
    avg_temp_c: float
    width: int
    height: int

    def to_dict(self) -> dict[str, float | int]:
        return {
            "center_x": round(self.center_x, 2),
            "center_y": round(self.center_y, 2),
            "pixel_count": self.pixel_count,
            "min_temp_c": round(self.min_temp_c, 2),
            "max_temp_c": round(self.max_temp_c, 2),
            "avg_temp_c": round(self.avg_temp_c, 2),
            "width": self.width,
            "height": self.height,
        }


class ThermalConfidenceScorer:
    """
    MLX90640 human-temperature confidence scoring with cluster and temporal checks.
    """

    HUMAN_SKIN_MIN = 32.0
    HUMAN_SKIN_MAX = 37.5
    HUMAN_SKIN_OPTIMAL = 34.5

    MIN_CLUSTER_SIZE = 8
    MIN_BODY_COVERAGE = 0.02
    MAX_TEMP_VARIANCE = 3.0
    MAX_CLUSTER_STD = 2.0
    REQUIRED_CONSECUTIVE_FRAMES = 3

    FINGER_THRESHOLD = 0.02
    HAND_THRESHOLD = 0.05
    FACE_THRESHOLD = 0.10
    FULL_BODY_THRESHOLD = 0.15

    def __init__(
        self,
        thermal_frame: list[float] | np.ndarray | None = None,
        width: int = 32,
        height: int = 24,
        *,
        temporal_required: bool = False,
        model_path: str | Path | None = None,
        model_threshold: float | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.temporal_required = temporal_required
        self.model_path = Path(
            model_path
            or os.getenv("THERMAL_HUMAN_MODEL_PATH", str(DEFAULT_MODEL_PATH))
        ).expanduser()
        self.model_threshold = float(
            np.clip(
                model_threshold
                if model_threshold is not None
                else float(os.getenv("THERMAL_HUMAN_MODEL_THRESHOLD", "0.55")),
                0.0,
                1.0,
            )
        )
        self.consecutive_human_frames = 0
        self.consecutive_empty_frames = 0
        self.last_human_state = False
        self.frame = self._reshape(thermal_frame) if thermal_frame is not None else None
        self.model_error: str | None = None
        self._interpreter: Any | None = None
        self._input_details: list[dict[str, Any]] = []
        self._output_details: list[dict[str, Any]] = []
        self._load_model()
        if self._interpreter is not None:
            LOGGER.info("Thermal human TFLite model loaded: %s", self.model_path)
        else:
            LOGGER.warning(
                "Thermal human TFLite model unavailable; using heuristic fallback: %s",
                self.model_error,
            )

    def set_frame(self, thermal_frame: list[float] | np.ndarray) -> None:
        self.frame = self._reshape(thermal_frame)

    def count_human_pixels(self) -> int:
        if self.frame is None:
            return 0
        return int(np.count_nonzero(self._human_mask(self.frame)))

    def calculate_body_coverage(self) -> float:
        return self.count_human_pixels() / float(self.width * self.height)

    def detect_body_parts(self) -> list[tuple[float, float, int, tuple[float, float]]]:
        if self.frame is None:
            return []
        parts = []
        for cluster in self._clusters(self._human_mask(self.frame), self.frame):
            parts.append(
                (
                    cluster.center_x,
                    cluster.center_y,
                    cluster.pixel_count,
                    (cluster.min_temp_c, cluster.max_temp_c),
                )
            )
        return parts

    def get_confidence_boost(self) -> tuple[float, str]:
        coverage = self.calculate_body_coverage()
        if coverage < self.FINGER_THRESHOLD:
            return 0.0, "no_human"
        if coverage < self.HAND_THRESHOLD:
            return 0.05, "finger_detected"
        if coverage < self.FULL_BODY_THRESHOLD:
            return 0.10, "hand_or_partial_face"
        return 0.15, "torso_or_full_face"

    def status(self) -> dict[str, object]:
        return {
            "thermal_model_available": self._interpreter is not None,
            "thermal_model_error": self.model_error,
            "thermal_model_path": str(self.model_path),
            "thermal_model_threshold": self.model_threshold,
        }

    def analyze(
        self,
        thermal_frame: list[float] | np.ndarray | None = None,
    ) -> dict[str, object]:
        if thermal_frame is not None:
            self.set_frame(thermal_frame)
        if self.frame is None:
            return self._no_human("missing_frame")

        heuristic = self._analyze_heuristic()
        if self._interpreter is None:
            heuristic["thermal_model_available"] = False
            heuristic["thermal_model_error"] = self.model_error
            heuristic["thermal_model_path"] = str(self.model_path)
            heuristic["thermal_model_threshold"] = self.model_threshold
            return heuristic

        try:
            model_result = self._predict_with_model(self.frame)
        except Exception as exc:  # pragma: no cover - Pi runtime path
            self.model_error = str(exc)
            heuristic["thermal_model_available"] = False
            heuristic["thermal_model_error"] = self.model_error
            heuristic["thermal_model_path"] = str(self.model_path)
            heuristic["thermal_model_threshold"] = self.model_threshold
            return heuristic

        return self._merge_model_and_heuristic(heuristic, model_result)

    def _analyze_heuristic(self) -> dict[str, object]:
        if self.frame is None:
            return self._no_human("missing_frame")

        temps = self.frame
        human_mask = self._human_mask(temps)
        human_pixels = int(np.count_nonzero(human_mask))
        body_coverage = human_pixels / float(self.width * self.height)

        if human_pixels < self.MIN_CLUSTER_SIZE:
            return self._no_human("insufficient_warm_pixels")
        if body_coverage < self.MIN_BODY_COVERAGE:
            return self._no_human("coverage_below_threshold")

        clusters = self._clusters(human_mask, temps)
        dominant = max(clusters, key=lambda item: item.pixel_count, default=None)
        if dominant is None or dominant.pixel_count < self.MIN_CLUSTER_SIZE:
            return self._no_human("no_connected_cluster")

        human_temps = temps[human_mask]
        temp_variance = float(np.std(human_temps))
        if temp_variance > self.MAX_TEMP_VARIANCE:
            return self._no_human(f"temp_too_varied_{temp_variance:.1f}")

        cluster_temps = self._cluster_temperatures(dominant, human_mask, temps)
        cluster_std = float(np.std(cluster_temps))
        if cluster_std > self.MAX_CLUSTER_STD:
            return self._no_human(f"cluster_temp_inconsistent_{cluster_std:.1f}")

        self.consecutive_human_frames += 1
        self.consecutive_empty_frames = 0
        if (
            self.temporal_required
            and self.consecutive_human_frames < self.REQUIRED_CONSECUTIVE_FRAMES
        ):
            return self._no_human(
                "temporal_consistency_"
                f"{self.consecutive_human_frames}/{self.REQUIRED_CONSECUTIVE_FRAMES}",
                reset_human_counter=False,
            )

        detected_part = self._classify_body_part(body_coverage)
        confidence_boost = self._calculate_boost(body_coverage)
        self.last_human_state = True
        return {
            "human_detected": True,
            "confidence_boost": confidence_boost,
            "body_coverage": round(body_coverage, 4),
            "detected_part": detected_part,
            "human_pixel_count": human_pixels,
            "cluster_size": dominant.pixel_count,
            "cluster_mean_temp": round(dominant.avg_temp_c, 2),
            "human_temp_avg": round(float(np.mean(human_temps)), 2),
            "human_temp_min": round(float(np.min(human_temps)), 2),
            "human_temp_max": round(float(np.max(human_temps)), 2),
            "human_clusters": [cluster.to_dict() for cluster in clusters[:5]],
            "dominant_cluster": dominant.to_dict(),
            "details": {
                "human_pixels": human_pixels,
                "temp_range": [
                    round(float(np.min(human_temps)), 1),
                    round(float(np.max(human_temps)), 1),
                ],
                "temp_variance": round(temp_variance, 2),
                "cluster_std": round(cluster_std, 2),
                "consecutive_frames": self.consecutive_human_frames,
            },
        }

    def _load_model(self) -> None:
        if not self.model_path.exists():
            self.model_error = f"model not found: {self.model_path}"
            return

        try:
            try:
                from tflite_runtime.interpreter import Interpreter
            except Exception:
                from tensorflow.lite import Interpreter  # type: ignore

            interpreter = Interpreter(model_path=str(self.model_path))
            interpreter.allocate_tensors()
            self._interpreter = interpreter
            self._input_details = interpreter.get_input_details()
            self._output_details = interpreter.get_output_details()
            self.model_error = None
        except Exception as exc:  # pragma: no cover - optional runtime dependency
            self._interpreter = None
            self.model_error = str(exc)

    def _predict_with_model(self, frame: np.ndarray) -> dict[str, object]:
        if self._interpreter is None or not self._input_details:
            raise RuntimeError(self.model_error or "thermal model unavailable")

        input_detail = self._input_details[0]
        input_tensor = self._prepare_model_input(frame, input_detail)
        self._interpreter.set_tensor(input_detail["index"], input_tensor)
        self._interpreter.invoke()

        outputs = [
            self._dequantize_output(
                self._interpreter.get_tensor(output_detail["index"]),
                output_detail,
            )
            for output_detail in self._output_details
        ]
        confidence = self._extract_confidence(outputs)
        mask = self._extract_mask(outputs)
        coverage = float(np.mean(mask >= 0.5)) if mask is not None else 0.0

        return {
            "thermal_model_available": True,
            "thermal_model_path": str(self.model_path),
            "thermal_model_confidence": round(confidence, 4),
            "thermal_model_threshold": self.model_threshold,
            "thermal_model_mask": mask,
            "thermal_model_coverage": round(coverage, 4),
        }

    def _prepare_model_input(
        self,
        frame: np.ndarray,
        input_detail: dict[str, Any],
    ) -> np.ndarray:
        normalized = np.clip(frame.astype(np.float32), 0.0, 80.0) / 80.0
        shape = [int(size) for size in input_detail["shape"]]
        dtype = input_detail["dtype"]

        if len(shape) == 4:
            if shape[1:3] == [self.height, self.width]:
                tensor = normalized[None, ..., None]
            elif shape[2:4] == [self.height, self.width]:
                tensor = normalized[None, None, ...]
            else:
                tensor = normalized.reshape(shape)
        elif len(shape) == 3:
            tensor = normalized[..., None] if shape[-1] == 1 else normalized[None, ...]
        else:
            tensor = normalized.reshape(shape)

        tensor = tensor.astype(np.float32)
        if np.issubdtype(dtype, np.integer):
            scale, zero_point = input_detail.get("quantization", (0.0, 0))
            if scale:
                tensor = np.round(tensor / scale + zero_point)
            tensor = np.clip(tensor, np.iinfo(dtype).min, np.iinfo(dtype).max)
        return tensor.astype(dtype)

    @staticmethod
    def _dequantize_output(
        output: np.ndarray,
        output_detail: dict[str, Any],
    ) -> np.ndarray:
        array = np.asarray(output)
        if np.issubdtype(array.dtype, np.integer):
            scale, zero_point = output_detail.get("quantization", (0.0, 0))
            if scale:
                array = (array.astype(np.float32) - zero_point) * scale
        return array.astype(np.float32)

    def _extract_confidence(self, outputs: list[np.ndarray]) -> float:
        scalar_candidates = [
            output
            for output in outputs
            if output.size <= 4
        ]
        candidate = scalar_candidates[0] if scalar_candidates else outputs[0]
        value = float(np.asarray(candidate).reshape(-1)[-1])
        if value < 0.0 or value > 1.0:
            value = 1.0 / (1.0 + np.exp(-value))
        return float(np.clip(value, 0.0, 1.0))

    def _extract_mask(self, outputs: list[np.ndarray]) -> np.ndarray | None:
        mask_candidates = [
            output
            for output in outputs
            if output.size >= self.width * self.height
        ]
        if not mask_candidates:
            return None

        mask = np.asarray(mask_candidates[-1], dtype=np.float32).reshape(-1)
        mask = mask[: self.width * self.height].reshape(self.height, self.width)
        return np.clip(mask, 0.0, 1.0)

    def _merge_model_and_heuristic(
        self,
        heuristic: dict[str, object],
        model_result: dict[str, object],
    ) -> dict[str, object]:
        confidence = float(model_result["thermal_model_confidence"])
        model_detected = confidence >= self.model_threshold
        model_coverage = float(model_result.get("thermal_model_coverage") or 0.0)
        heuristic_coverage = float(heuristic.get("body_coverage") or 0.0)
        body_coverage = max(model_coverage, heuristic_coverage)
        detected_part = self._classify_body_part(body_coverage)
        confidence_boost = self._calculate_model_boost(confidence, body_coverage)
        estimated_pixels = int(round(body_coverage * self.width * self.height))

        merged = dict(heuristic)
        merged.update(
            {
                "human_detected": bool(model_detected),
                "confidence_boost": confidence_boost,
                "body_coverage": round(body_coverage, 4),
                "detected_part": detected_part if model_detected else "none",
                "human_pixel_count": estimated_pixels if model_detected else 0,
                "cluster_size": max(
                    int(heuristic.get("cluster_size") or 0),
                    estimated_pixels if model_detected else 0,
                ),
                "thermal_model_available": True,
                "thermal_model_path": str(self.model_path),
                "thermal_model_confidence": round(confidence, 4),
                "thermal_model_threshold": self.model_threshold,
                "thermal_model_coverage": round(model_coverage, 4),
                "thermal_model_error": None,
            }
        )

        details = dict(merged.get("details") or {})
        details.update(
            {
                "heuristic_human_detected": bool(heuristic.get("human_detected")),
                "heuristic_confidence_boost": heuristic.get("confidence_boost", 0.0),
                "heuristic_body_coverage": heuristic_coverage,
                "thermal_model_confidence": round(confidence, 4),
                "thermal_model_threshold": self.model_threshold,
            }
        )
        merged["details"] = details
        return merged

    @staticmethod
    def _calculate_model_boost(confidence: float, coverage: float) -> float:
        if confidence < 0.5:
            return 0.0
        coverage_bonus = min(max(coverage, 0.0), 0.25)
        return round(min(0.25, 0.08 + confidence * 0.12 + coverage_bonus * 0.2), 4)

    def _no_human(self, reason: str, *, reset_human_counter: bool = True) -> dict[str, object]:
        if reset_human_counter:
            self.consecutive_human_frames = 0
        self.consecutive_empty_frames += 1
        self.last_human_state = False
        return {
            "human_detected": False,
            "confidence_boost": 0.0,
            "body_coverage": 0.0,
            "detected_part": "none",
            "human_pixel_count": 0,
            "cluster_size": 0,
            "cluster_mean_temp": 0.0,
            "human_temp_avg": None,
            "human_temp_min": None,
            "human_temp_max": None,
            "human_clusters": [],
            "dominant_cluster": None,
            "details": {
                "reason": reason,
                "consecutive_frames": self.consecutive_human_frames,
                "empty_frames": self.consecutive_empty_frames,
            },
        }

    def _reshape(self, thermal_frame: list[float] | np.ndarray) -> np.ndarray:
        flat = np.asarray(thermal_frame, dtype=np.float32).flatten()
        if flat.size < self.width * self.height:
            raise ValueError(
                f"Thermal frame has {flat.size} values, expected at least {self.width * self.height}"
            )
        return flat[: self.width * self.height].reshape(self.height, self.width)

    def _human_mask(self, frame: np.ndarray) -> np.ndarray:
        return (frame >= self.HUMAN_SKIN_MIN) & (frame <= self.HUMAN_SKIN_MAX)

    def _clusters(self, mask: np.ndarray, frame: np.ndarray) -> list[ThermalCluster]:
        visited = np.zeros_like(mask, dtype=bool)
        clusters: list[ThermalCluster] = []

        for y in range(self.height):
            for x in range(self.width):
                if not mask[y, x] or visited[y, x]:
                    continue
                points = self._flood_fill(mask, visited, x, y)
                xs = np.array([point[0] for point in points], dtype=np.float32)
                ys = np.array([point[1] for point in points], dtype=np.float32)
                temps = np.array(
                    [frame[point[1], point[0]] for point in points],
                    dtype=np.float32,
                )
                clusters.append(
                    ThermalCluster(
                        center_x=float(np.mean(xs)),
                        center_y=float(np.mean(ys)),
                        pixel_count=len(points),
                        min_temp_c=float(np.min(temps)),
                        max_temp_c=float(np.max(temps)),
                        avg_temp_c=float(np.mean(temps)),
                        width=int(np.max(xs) - np.min(xs) + 1),
                        height=int(np.max(ys) - np.min(ys) + 1),
                    )
                )

        clusters.sort(key=lambda item: item.pixel_count, reverse=True)
        return clusters

    def _flood_fill(
        self,
        mask: np.ndarray,
        visited: np.ndarray,
        start_x: int,
        start_y: int,
    ) -> list[tuple[int, int]]:
        stack = [(start_x, start_y)]
        visited[start_y, start_x] = True
        points: list[tuple[int, int]] = []
        while stack:
            x, y = stack.pop()
            points.append((x, y))
            for dy, dx in (
                (-1, 0),
                (1, 0),
                (0, -1),
                (0, 1),
                (-1, -1),
                (-1, 1),
                (1, -1),
                (1, 1),
            ):
                nx = x + dx
                ny = y + dy
                if (
                    0 <= nx < self.width
                    and 0 <= ny < self.height
                    and mask[ny, nx]
                    and not visited[ny, nx]
                ):
                    visited[ny, nx] = True
                    stack.append((nx, ny))
        return points

    def _cluster_temperatures(
        self,
        cluster: ThermalCluster,
        mask: np.ndarray,
        frame: np.ndarray,
    ) -> np.ndarray:
        values = []
        for y in range(self.height):
            for x in range(self.width):
                if not mask[y, x]:
                    continue
                if (
                    abs(x - cluster.center_x) <= max(cluster.width, 1)
                    and abs(y - cluster.center_y) <= max(cluster.height, 1)
                ):
                    values.append(frame[y, x])
        return np.asarray(values or [cluster.avg_temp_c], dtype=np.float32)

    def _classify_body_part(self, coverage: float) -> str:
        if coverage < self.FINGER_THRESHOLD:
            return "no_human"
        if coverage < self.HAND_THRESHOLD:
            return "finger_detected"
        if coverage < self.FULL_BODY_THRESHOLD:
            return "hand_or_partial_face"
        return "torso_or_full_face"

    def _calculate_boost(self, coverage: float) -> float:
        if coverage < self.FINGER_THRESHOLD:
            return 0.0
        if coverage < self.HAND_THRESHOLD:
            return 0.05
        if coverage < self.FULL_BODY_THRESHOLD:
            return 0.10
        return 0.15
