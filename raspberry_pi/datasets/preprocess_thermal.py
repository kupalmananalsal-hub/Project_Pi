#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Iterable

import numpy as np


PROJECT_ROOT = Path(
    os.getenv("PROJECT_PI_ROOT", Path(__file__).resolve().parents[2])
).expanduser()
DATASET_DIR = Path(os.getenv("DATASET_DIR", str(PROJECT_ROOT / "dataset"))).expanduser()
OUTPUT_ROOT = DATASET_DIR / "thermal" / "processed"


def resample_to_mlx90640(image: np.ndarray | list[list[float]] | list[float]) -> np.ndarray:
    """
    Resize a thermal image to 24x32 using bilinear interpolation.
    """

    array = np.asarray(image, dtype=np.float32)
    if array.ndim == 1:
        array = array.reshape(24, 32)
    if array.ndim != 2:
        raise ValueError(f"Expected 2-D thermal image, received shape {array.shape}")

    src_h, src_w = array.shape
    dst_h, dst_w = 24, 32
    y_positions = np.linspace(0, src_h - 1, dst_h)
    x_positions = np.linspace(0, src_w - 1, dst_w)

    y0 = np.floor(y_positions).astype(int)
    x0 = np.floor(x_positions).astype(int)
    y1 = np.clip(y0 + 1, 0, src_h - 1)
    x1 = np.clip(x0 + 1, 0, src_w - 1)
    wy = y_positions - y0
    wx = x_positions - x0

    resized = np.zeros((dst_h, dst_w), dtype=np.float32)
    for iy in range(dst_h):
        top = (1 - wx) * array[y0[iy], x0] + wx * array[y0[iy], x1]
        bottom = (1 - wx) * array[y1[iy], x0] + wx * array[y1[iy], x1]
        resized[iy] = ((1 - wy[iy]) * top) + (wy[iy] * bottom)
    return resized


def extract_temperature_statistics(dataset_path: str | Path) -> dict[str, float]:
    """
    Scan CSV, JSON, NPY, and NPZ files for temperature samples and summarize them.
    """

    values: list[float] = []
    for file_path in _iter_dataset_files(dataset_path):
        if file_path.suffix.lower() == ".csv":
            values.extend(_read_csv_temperatures(file_path))
        elif file_path.suffix.lower() == ".json":
            values.extend(_read_json_temperatures(file_path))
        elif file_path.suffix.lower() == ".npy":
            values.extend(np.load(file_path).astype(np.float32).flatten().tolist())
        elif file_path.suffix.lower() == ".npz":
            archive = np.load(file_path)
            for key in archive.files:
                values.extend(archive[key].astype(np.float32).flatten().tolist())

    if not values:
        return {
            "mean_human_skin_temperature_c": 33.5,
            "std_dev_c": 2.1,
            "normal_min_c": 30.0,
            "normal_max_c": 38.0,
            "fever_threshold_c": 37.5,
        }

    data = np.asarray(values, dtype=np.float32)
    return {
        "mean_human_skin_temperature_c": round(float(np.mean(data)), 2),
        "std_dev_c": round(float(np.std(data)), 2),
        "normal_min_c": round(float(np.min(data)), 2),
        "normal_max_c": round(float(np.max(data)), 2),
        "fever_threshold_c": 37.5,
    }


def generate_training_data(
    dataset_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    output_path = Path(output_path or OUTPUT_ROOT / "thermal_training.jsonl").expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    samples_written = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for sample in _iter_samples(dataset_path):
            resized = resample_to_mlx90640(sample["temperatures"])
            coverage = _body_coverage(resized)
            label = _label_for_coverage(coverage)
            payload = {
                "temperatures": [round(float(value), 2) for value in resized.flatten()],
                "label": label,
                "body_coverage": round(coverage, 4),
                "body_parts_visible": _body_parts_for_label(label),
                "environment": sample.get("environment", "unknown"),
                "distance_meters": sample.get("distance_meters", 0.0),
                "source": sample.get("source"),
            }
            handle.write(json.dumps(payload) + "\n")
            samples_written += 1

    print(f"Wrote {samples_written} thermal samples to {output_path}")
    return output_path


def _iter_dataset_files(dataset_path: str | Path) -> Iterable[Path]:
    root = Path(dataset_path).expanduser()
    if not root.exists():
        return []
    return (
        file_path
        for file_path in root.rglob("*")
        if file_path.is_file()
        and file_path.suffix.lower() in {".csv", ".json", ".npy", ".npz"}
    )


def _iter_samples(dataset_path: str | Path) -> Iterable[dict[str, object]]:
    for file_path in _iter_dataset_files(dataset_path):
        suffix = file_path.suffix.lower()
        if suffix == ".json":
            yield from _json_samples(file_path)
        elif suffix == ".csv":
            yield from _csv_samples(file_path)
        elif suffix == ".npy":
            array = np.load(file_path)
            yield {
                "temperatures": array,
                "environment": "unknown",
                "distance_meters": 0.0,
                "source": str(file_path),
            }


def _json_samples(file_path: Path) -> Iterable[dict[str, object]]:
    try:
        decoded = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    if isinstance(decoded, dict):
        decoded = [decoded]

    samples = []
    for entry in decoded:
        if not isinstance(entry, dict):
            continue
        temperatures = (
            entry.get("temperatures")
            or entry.get("frame")
            or entry.get("pixels")
            or entry.get("thermal")
        )
        if temperatures is None:
            continue
        samples.append(
            {
                "temperatures": temperatures,
                "environment": entry.get("environment", "unknown"),
                "distance_meters": entry.get("distance_meters", 0.0),
                "source": str(file_path),
            }
        )
    return samples


def _csv_samples(file_path: Path) -> Iterable[dict[str, object]]:
    rows = _read_csv_temperatures(file_path)
    if not rows:
        return []

    flat = np.asarray(rows, dtype=np.float32)
    side = int(np.sqrt(flat.size))
    if side * side == flat.size:
        temperatures = flat.reshape(side, side)
    else:
        temperatures = flat.reshape(1, flat.size)

    return [
        {
            "temperatures": temperatures,
            "environment": "unknown",
            "distance_meters": 0.0,
            "source": str(file_path),
        }
    ]


def _read_csv_temperatures(file_path: Path) -> list[float]:
    values: list[float] = []
    with file_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            for item in row:
                try:
                    values.append(float(item))
                except ValueError:
                    continue
    return values


def _read_json_temperatures(file_path: Path) -> list[float]:
    try:
        decoded = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []

    values: list[float] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        else:
            try:
                values.append(float(node))
            except (TypeError, ValueError):
                return

    walk(decoded)
    return values


def _body_coverage(frame: np.ndarray) -> float:
    mask = (frame >= 30.0) & (frame <= 38.0)
    return float(np.count_nonzero(mask)) / float(frame.size)


def _label_for_coverage(coverage: float) -> str:
    if coverage >= 0.15:
        return "human_full"
    if coverage >= 0.01:
        return "human_partial"
    return "no_human"


def _body_parts_for_label(label: str) -> list[str]:
    if label == "human_full":
        return ["face", "hand", "torso"]
    if label == "human_partial":
        return ["face", "hand"]
    return []


if __name__ == "__main__":
    dataset_root = DATASET_DIR / "thermal" / "raw" / "fda_thermal"
    stats = extract_temperature_statistics(dataset_root)
    print(json.dumps(stats, indent=2))
    generate_training_data(dataset_root)
