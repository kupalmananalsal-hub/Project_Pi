#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

import numpy as np

try:
    import h5py
except Exception:  # pragma: no cover - optional training dependency
    h5py = None

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional training dependency
    Image = None


WIDTH = 32
HEIGHT = 24
DEFAULT_ROOT = Path.home() / "thesis_dataset" / "thermal"
RAW_ROOT = DEFAULT_ROOT / "raw"
PROCESSED_ROOT = DEFAULT_ROOT / "processed"
OUTPUT_PATH = PROCESSED_ROOT / "thermal_human_detection.npz"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert thermal datasets to Project Pi 32x24 NPZ format."
    )
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--min-coverage", type=float, default=0.005)
    args = parser.parse_args()

    samples = list(iter_samples(args.raw_root.expanduser()))
    if not samples:
        raise RuntimeError(f"No usable thermal samples found under {args.raw_root}")

    frames = np.stack([sample["frame"] for sample in samples]).astype(np.float32)
    masks = np.stack([sample["mask"] for sample in samples]).astype(np.float32)
    coverage = masks.reshape(masks.shape[0], -1).mean(axis=1).astype(np.float32)
    presence = (coverage >= args.min_coverage).astype(np.float32)
    sources = np.asarray([sample["source"] for sample in samples], dtype=object)

    args.output.expanduser().parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output.expanduser(),
        frames=frames,
        masks=masks,
        presence=presence,
        coverage=coverage,
        sources=sources,
    )
    print(f"Wrote {len(samples)} samples to {args.output.expanduser()}")
    print(f"Positive samples: {int(presence.sum())}")
    print(f"Negative samples: {int((1 - presence).sum())}")


def iter_samples(raw_root: Path) -> Iterable[dict[str, object]]:
    raw_root = raw_root.expanduser()
    if not raw_root.exists():
        return
    for root in sorted(path for path in raw_root.iterdir() if path.is_dir()):
        yield from _iter_hdf5_samples(root)
        yield from _iter_np_samples(root)
        yield from _iter_image_samples(root)
        yield from _iter_json_samples(root)


def _iter_hdf5_samples(root: Path) -> Iterable[dict[str, object]]:
    if h5py is None:
        return

    for file_path in root.rglob("*"):
        if file_path.suffix.lower() not in {".h5", ".hdf5", ".hdf"}:
            continue

        try:
            with h5py.File(file_path, "r") as handle:
                datasets = _collect_hdf5_datasets(handle)
                frame_sets = [
                    value
                    for key, value in datasets.items()
                    if _looks_like_frame_array(value)
                ]
                label_sets = {
                    key: value
                    for key, value in datasets.items()
                    if _looks_like_label_array(key, value)
                }

                for frame_array in frame_sets:
                    yield from _samples_from_frame_array(
                        frame_array,
                        source=file_path,
                        label_sets=label_sets,
                    )
        except OSError:
            continue


def _collect_hdf5_datasets(handle: object) -> dict[str, np.ndarray]:
    datasets: dict[str, np.ndarray] = {}

    def visit(name: str, node: object) -> None:
        if h5py is not None and isinstance(node, h5py.Dataset):
            try:
                datasets[name.lower()] = np.asarray(node)
            except Exception:
                return

    handle.visititems(visit)
    return datasets


def _samples_from_frame_array(
    frame_array: np.ndarray,
    *,
    source: Path,
    label_sets: dict[str, np.ndarray],
) -> Iterable[dict[str, object]]:
    frames = _normalize_frame_batch(frame_array)
    center_labels = _first_center_label_set(label_sets, len(frames))
    box_labels = _first_box_label_set(label_sets, len(frames))

    for index, frame in enumerate(frames):
        mask = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
        if center_labels is not None:
            mask = np.maximum(mask, _mask_from_centers(center_labels[index]))
        if box_labels is not None:
            mask = np.maximum(mask, _mask_from_boxes(box_labels[index]))
        if center_labels is None and box_labels is None:
            mask = _mask_from_temperature(frame)

        yield {
            "frame": _to_celsius_range(frame),
            "mask": mask,
            "source": f"{source}#{index}",
        }


def _normalize_frame_batch(array: np.ndarray) -> list[np.ndarray]:
    array = np.asarray(array, dtype=np.float32)
    if array.ndim == 2:
        return [resize_to_mlx90640(array)]
    if array.ndim == 3:
        return [resize_to_mlx90640(frame) for frame in array]
    if array.ndim == 4 and array.shape[-1] == 1:
        return [resize_to_mlx90640(frame[..., 0]) for frame in array]
    return []


def _iter_np_samples(root: Path) -> Iterable[dict[str, object]]:
    for file_path in root.rglob("*"):
        suffix = file_path.suffix.lower()
        if suffix not in {".npy", ".npz"}:
            continue

        try:
            if suffix == ".npy":
                array = np.load(file_path, allow_pickle=True)
                yield from _samples_from_array_like(array, file_path)
            else:
                archive = np.load(file_path, allow_pickle=True)
                if {"frames", "masks"}.issubset(set(archive.files)):
                    frames = _normalize_frame_batch(archive["frames"])
                    masks = _normalize_mask_batch(archive["masks"], len(frames))
                    for index, frame in enumerate(frames):
                        yield {
                            "frame": _to_celsius_range(frame),
                            "mask": masks[index],
                            "source": f"{file_path}#{index}",
                        }
                else:
                    for key in archive.files:
                        yield from _samples_from_array_like(archive[key], file_path)
        except Exception:
            continue


def _samples_from_array_like(array: np.ndarray, source: Path) -> Iterable[dict[str, object]]:
    for index, frame in enumerate(_normalize_frame_batch(array)):
        yield {
            "frame": _to_celsius_range(frame),
            "mask": _mask_from_temperature(frame),
            "source": f"{source}#{index}",
        }


def _iter_image_samples(root: Path) -> Iterable[dict[str, object]]:
    if Image is None:
        return

    image_suffixes = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
    for image_path in root.rglob("*"):
        if image_path.suffix.lower() not in image_suffixes:
            continue

        label_path = _find_label_for_image(image_path)
        if label_path is None:
            continue

        try:
            with Image.open(image_path) as image:
                frame = resize_to_mlx90640(np.asarray(image.convert("L"), dtype=np.float32))
        except Exception:
            continue

        frame = _to_celsius_range(frame)
        mask = _mask_from_label_file(label_path, image_path)
        yield {"frame": frame, "mask": mask, "source": str(image_path)}


def _iter_json_samples(root: Path) -> Iterable[dict[str, object]]:
    for file_path in root.rglob("*.json"):
        try:
            decoded = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        entries = decoded if isinstance(decoded, list) else [decoded]
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            frame = (
                entry.get("temperatures")
                or entry.get("frame")
                or entry.get("thermal")
                or entry.get("pixels")
            )
            if frame is None:
                continue
            try:
                resized = resize_to_mlx90640(np.asarray(frame, dtype=np.float32))
            except Exception:
                continue
            mask = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
            if entry.get("boxes"):
                mask = np.maximum(mask, _mask_from_boxes(np.asarray(entry["boxes"])))
            if entry.get("centers"):
                mask = np.maximum(mask, _mask_from_centers(np.asarray(entry["centers"])))
            if not np.any(mask):
                mask = _mask_from_temperature(resized)
            yield {
                "frame": _to_celsius_range(resized),
                "mask": mask,
                "source": f"{file_path}#{index}",
            }


def resize_to_mlx90640(array: np.ndarray) -> np.ndarray:
    array = np.asarray(array, dtype=np.float32)
    if array.ndim == 1:
        if array.size == WIDTH * HEIGHT:
            array = array.reshape(HEIGHT, WIDTH)
        else:
            side = int(math.sqrt(array.size))
            array = array[: side * side].reshape(side, side)
    if array.ndim != 2:
        raise ValueError(f"Expected 2-D array, got {array.shape}")

    if array.shape == (HEIGHT, WIDTH):
        return array.astype(np.float32)
    if array.shape == (WIDTH, HEIGHT):
        return array.T.astype(np.float32)

    src_h, src_w = array.shape
    y_positions = np.linspace(0, src_h - 1, HEIGHT)
    x_positions = np.linspace(0, src_w - 1, WIDTH)
    y0 = np.floor(y_positions).astype(int)
    x0 = np.floor(x_positions).astype(int)
    y1 = np.clip(y0 + 1, 0, src_h - 1)
    x1 = np.clip(x0 + 1, 0, src_w - 1)
    wy = y_positions - y0
    wx = x_positions - x0

    resized = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
    for iy in range(HEIGHT):
        top = (1 - wx) * array[y0[iy], x0] + wx * array[y0[iy], x1]
        bottom = (1 - wx) * array[y1[iy], x0] + wx * array[y1[iy], x1]
        resized[iy] = ((1 - wy[iy]) * top) + (wy[iy] * bottom)
    return resized


def _to_celsius_range(frame: np.ndarray) -> np.ndarray:
    frame = np.asarray(frame, dtype=np.float32)
    finite = frame[np.isfinite(frame)]
    if finite.size == 0:
        return np.zeros((HEIGHT, WIDTH), dtype=np.float32)

    min_value = float(np.min(finite))
    max_value = float(np.max(finite))
    if 0.0 <= min_value and max_value <= 80.0:
        return np.clip(frame, 0.0, 80.0).astype(np.float32)

    if 0.0 <= min_value and max_value <= 255.0:
        return np.clip((frame / 255.0) * 80.0, 0.0, 80.0).astype(np.float32)

    span = max(max_value - min_value, 1e-6)
    return np.clip(((frame - min_value) / span) * 80.0, 0.0, 80.0).astype(np.float32)


def _mask_from_label_file(label_path: Path, image_path: Path) -> np.ndarray:
    suffix = label_path.suffix.lower()
    if suffix == ".txt":
        return _mask_from_yolo_txt(label_path)
    if suffix == ".xml":
        return _mask_from_voc_xml(label_path, image_path)
    if suffix == ".json":
        try:
            decoded = json.loads(label_path.read_text(encoding="utf-8"))
        except Exception:
            return np.zeros((HEIGHT, WIDTH), dtype=np.float32)
        boxes = decoded.get("boxes") or decoded.get("bboxes") or []
        centers = decoded.get("centers") or decoded.get("points") or []
        mask = _mask_from_boxes(np.asarray(boxes)) if boxes else np.zeros((HEIGHT, WIDTH), dtype=np.float32)
        if centers:
            mask = np.maximum(mask, _mask_from_centers(np.asarray(centers)))
        return mask
    return np.zeros((HEIGHT, WIDTH), dtype=np.float32)


def _mask_from_yolo_txt(label_path: Path) -> np.ndarray:
    mask = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
    for line in label_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.strip().split()
        if len(parts) < 5:
            continue
        try:
            _, cx, cy, w, h = [float(value) for value in parts[:5]]
        except ValueError:
            continue
        mask = np.maximum(mask, _mask_from_boxes(np.asarray([[cx, cy, w, h]])))
    return mask


def _mask_from_voc_xml(label_path: Path, image_path: Path) -> np.ndarray:
    mask = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
    try:
        root = ET.parse(label_path).getroot()
    except Exception:
        return mask

    try:
        if Image is not None:
            with Image.open(image_path) as image:
                image_w, image_h = image.size
        else:
            image_w, image_h = WIDTH, HEIGHT
    except Exception:
        image_w, image_h = WIDTH, HEIGHT

    boxes = []
    for obj in root.findall(".//object"):
        box = obj.find("bndbox")
        if box is None:
            continue
        try:
            xmin = float(box.findtext("xmin", "0")) / image_w
            ymin = float(box.findtext("ymin", "0")) / image_h
            xmax = float(box.findtext("xmax", "0")) / image_w
            ymax = float(box.findtext("ymax", "0")) / image_h
        except ValueError:
            continue
        boxes.append([xmin, ymin, xmax, ymax])
    if boxes:
        mask = _mask_from_boxes(np.asarray(boxes))
    return mask


def _mask_from_boxes(boxes: np.ndarray) -> np.ndarray:
    mask = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
    boxes = np.asarray(boxes, dtype=np.float32)
    if boxes.size == 0:
        return mask
    boxes = boxes.reshape(-1, boxes.shape[-1])

    for box in boxes:
        if box.size < 4:
            continue
        x1, y1, x2, y2 = _box_to_xyxy(box[:4])
        x1 = int(np.clip(np.floor(x1 * WIDTH), 0, WIDTH - 1))
        x2 = int(np.clip(np.ceil(x2 * WIDTH), x1 + 1, WIDTH))
        y1 = int(np.clip(np.floor(y1 * HEIGHT), 0, HEIGHT - 1))
        y2 = int(np.clip(np.ceil(y2 * HEIGHT), y1 + 1, HEIGHT))
        mask[y1:y2, x1:x2] = 1.0
    return mask


def _box_to_xyxy(box: np.ndarray) -> tuple[float, float, float, float]:
    a, b, c, d = [float(value) for value in box]
    if 0 <= a <= 1 and 0 <= b <= 1 and 0 <= c <= 1 and 0 <= d <= 1:
        if c <= a or d <= b:
            cx, cy, w, h = a, b, c, d
            return (
                max(0.0, cx - w / 2),
                max(0.0, cy - h / 2),
                min(1.0, cx + w / 2),
                min(1.0, cy + h / 2),
            )
        return a, b, c, d
    return (
        max(0.0, min(a, c) / WIDTH),
        max(0.0, min(b, d) / HEIGHT),
        min(1.0, max(a, c) / WIDTH),
        min(1.0, max(b, d) / HEIGHT),
    )


def _mask_from_centers(centers: np.ndarray, radius: int = 2) -> np.ndarray:
    mask = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
    centers = np.asarray(centers, dtype=np.float32)
    if centers.size == 0:
        return mask
    centers = centers.reshape(-1, centers.shape[-1])
    for center in centers:
        if center.size < 2:
            continue
        x = float(center[0])
        y = float(center[1])
        if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
            x *= WIDTH
            y *= HEIGHT
        for yy in range(HEIGHT):
            for xx in range(WIDTH):
                if (xx - x) ** 2 + (yy - y) ** 2 <= radius**2:
                    mask[yy, xx] = 1.0
    return mask


def _mask_from_temperature(frame: np.ndarray) -> np.ndarray:
    return ((frame >= 30.0) & (frame <= 40.0)).astype(np.float32)


def _normalize_mask_batch(array: np.ndarray, n_frames: int) -> list[np.ndarray]:
    masks = _normalize_frame_batch(array)
    if len(masks) == 1 and n_frames > 1:
        masks *= n_frames
    return [(mask > 0.5).astype(np.float32) for mask in masks[:n_frames]]


def _first_center_label_set(
    label_sets: dict[str, np.ndarray],
    n_frames: int,
) -> np.ndarray | None:
    for key, value in label_sets.items():
        if any(token in key for token in ("center", "coord", "point", "position")):
            value = np.asarray(value)
            if value.shape[0] == n_frames:
                return value
    return None


def _first_box_label_set(
    label_sets: dict[str, np.ndarray],
    n_frames: int,
) -> np.ndarray | None:
    for key, value in label_sets.items():
        if any(token in key for token in ("box", "bbox", "bound")):
            value = np.asarray(value)
            if value.shape[0] == n_frames:
                return value
    return None


def _looks_like_frame_array(value: np.ndarray) -> bool:
    value = np.asarray(value)
    return value.ndim >= 2 and (
        value.shape[-2:] in {(HEIGHT, WIDTH), (WIDTH, HEIGHT)}
        or value.shape[-3:-1] in {(HEIGHT, WIDTH), (WIDTH, HEIGHT)}
    )


def _looks_like_label_array(key: str, value: np.ndarray) -> bool:
    if not any(token in key for token in ("label", "coord", "point", "position", "box", "bbox")):
        return False
    value = np.asarray(value)
    return value.ndim >= 2 and value.shape[-1] >= 2


def _find_label_for_image(image_path: Path) -> Path | None:
    candidates = [
        image_path.with_suffix(".txt"),
        image_path.with_suffix(".xml"),
        image_path.with_suffix(".json"),
        image_path.parent.parent / "labels" / f"{image_path.stem}.txt",
        image_path.parent.parent / "labels" / f"{image_path.stem}.xml",
        image_path.parent.parent / "annotations" / f"{image_path.stem}.xml",
        image_path.parent.parent / "annotations" / f"{image_path.stem}.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


if __name__ == "__main__":
    main()
