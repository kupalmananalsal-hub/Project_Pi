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
    Human-temperature thermal confidence scoring tuned for MLX90640 frames.
    """

    HUMAN_SKIN_MIN = 30.0
    HUMAN_SKIN_MAX = 38.0
    HUMAN_SKIN_OPTIMAL = 34.0

    FINGER_THRESHOLD = 0.01
    HAND_THRESHOLD = 0.05
    FACE_THRESHOLD = 0.10
    FULL_BODY_THRESHOLD = 0.15

    def __init__(
        self,
        thermal_frame: list[float] | np.ndarray,
        width: int = 32,
        height: int = 24,
    ) -> None:
        flat = np.asarray(thermal_frame, dtype=np.float32).flatten()
        if flat.size < width * height:
            raise ValueError(
                f"Thermal frame has {flat.size} values, expected at least {width * height}"
            )
        self.width = width
        self.height = height
        self.frame = flat[: width * height].reshape(height, width)

    def count_human_pixels(self) -> int:
        return int(np.count_nonzero(self._human_mask()))

    def calculate_body_coverage(self) -> float:
        return self.count_human_pixels() / float(self.width * self.height)

    def detect_body_parts(self) -> list[tuple[float, float, int, tuple[float, float]]]:
        parts = []
        for cluster in self._clusters():
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

    def analyze(self) -> dict[str, object]:
        coverage = self.calculate_body_coverage()
        clusters = self._clusters()
        boost, label = self.get_confidence_boost()
        dominant = max(clusters, key=lambda item: item.pixel_count, default=None)

        return {
            "human_detected": coverage >= self.FINGER_THRESHOLD,
            "body_coverage": round(coverage, 4),
            "detected_part": label,
            "confidence_boost": boost,
            "human_pixel_count": self.count_human_pixels(),
            "human_temp_avg": round(float(self._masked_average()), 2)
            if coverage > 0
            else None,
            "human_temp_min": round(float(self._masked_min()), 2)
            if coverage > 0
            else None,
            "human_temp_max": round(float(self._masked_max()), 2)
            if coverage > 0
            else None,
            "human_clusters": [cluster.to_dict() for cluster in clusters[:5]],
            "dominant_cluster": dominant.to_dict() if dominant else None,
        }

    def _human_mask(self) -> np.ndarray:
        return (self.frame >= self.HUMAN_SKIN_MIN) & (self.frame <= self.HUMAN_SKIN_MAX)

    def _masked_average(self) -> float:
        mask = self._human_mask()
        return float(np.mean(self.frame[mask]))

    def _masked_min(self) -> float:
        mask = self._human_mask()
        return float(np.min(self.frame[mask]))

    def _masked_max(self) -> float:
        mask = self._human_mask()
        return float(np.max(self.frame[mask]))

    def _clusters(self) -> list[ThermalCluster]:
        mask = self._human_mask()
        visited = np.zeros_like(mask, dtype=bool)
        clusters: list[ThermalCluster] = []

        for y in range(self.height):
            for x in range(self.width):
                if not mask[y, x] or visited[y, x]:
                    continue

                stack = [(x, y)]
                visited[y, x] = True
                points: list[tuple[int, int]] = []

                while stack:
                    px, py = stack.pop()
                    points.append((px, py))
                    for nx, ny in (
                        (px - 1, py),
                        (px + 1, py),
                        (px, py - 1),
                        (px, py + 1),
                    ):
                        if (
                            0 <= nx < self.width
                            and 0 <= ny < self.height
                            and mask[ny, nx]
                            and not visited[ny, nx]
                        ):
                            visited[ny, nx] = True
                            stack.append((nx, ny))

                xs = np.array([point[0] for point in points], dtype=np.float32)
                ys = np.array([point[1] for point in points], dtype=np.float32)
                temps = np.array(
                    [self.frame[point[1], point[0]] for point in points], dtype=np.float32
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
