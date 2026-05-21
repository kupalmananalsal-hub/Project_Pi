#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


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
    ) -> None:
        self.width = width
        self.height = height
        self.temporal_required = temporal_required
        self.consecutive_human_frames = 0
        self.consecutive_empty_frames = 0
        self.last_human_state = False
        self.frame = self._reshape(thermal_frame) if thermal_frame is not None else None

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

    def analyze(
        self,
        thermal_frame: list[float] | np.ndarray | None = None,
    ) -> dict[str, object]:
        if thermal_frame is not None:
            self.set_frame(thermal_frame)
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
