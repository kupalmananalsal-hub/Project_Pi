#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import logging
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
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
RECORDED_ROOT = DEFAULT_ROOT / "recorded"
PROCESSED_ROOT = DEFAULT_ROOT / "processed"
OUTPUT_PATH = PROCESSED_ROOT / "thermal_human_detection.npz"

DATASET_CHOICES = (
    "all",
    "thermo_presence",
    "mldetection",
    "skku",
    "yolo",
    "recorded",
)

LOGGER = logging.getLogger("thermal_preprocess")


@dataclass(frozen=True)
class ThermalSample:
    frame: np.ndarray
    mask: np.ndarray
    source: str
    source_id: str
    dataset: str
    source_units: str
    input_domain: str
    annotation_type: str


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert thermal datasets to Project Pi 32x24 NPZ format."
    )
    parser.add_argument(
        "--dataset",
        choices=DATASET_CHOICES,
        default="all",
        help="Dataset adapter to run. Defaults to all.",
    )
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    parser.add_argument("--recorded-root", type=Path, default=RECORDED_ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--min-coverage", type=float, default=0.005)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(levelname)s:%(name)s:%(message)s",
    )

    adapters = _selected_adapters(args.dataset)
    samples: list[ThermalSample] = []
    for name, adapter in adapters:
        root = args.recorded_root if name == "recorded" else args.raw_root
        dataset_samples = list(adapter(root.expanduser()))
        LOGGER.info("%s: accepted samples=%d", name, len(dataset_samples))
        samples.extend(dataset_samples)

    if not samples:
        raise RuntimeError("No usable thermal samples found.")

    frames = np.stack([sample.frame for sample in samples]).astype(np.float32)
    masks = np.stack([sample.mask for sample in samples]).astype(np.float32)
    coverage = masks.reshape(masks.shape[0], -1).mean(axis=1).astype(np.float32)
    presence = (coverage >= args.min_coverage).astype(np.float32)

    output_path = args.output.expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        frames=frames,
        masks=masks,
        presence=presence,
        coverage=coverage,
        sources=np.asarray([sample.source for sample in samples], dtype=object),
        source_ids=np.asarray([sample.source_id for sample in samples], dtype=object),
        source_units=np.asarray([sample.source_units for sample in samples], dtype=object),
        input_domains=np.asarray([sample.input_domain for sample in samples], dtype=object),
        dataset_names=np.asarray([sample.dataset for sample in samples], dtype=object),
        annotation_types=np.asarray(
            [sample.annotation_type for sample in samples],
            dtype=object,
        ),
    )

    report = _build_report(samples, presence)
    report_path = output_path.with_suffix(".report.json")
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    LOGGER.info("Wrote %d samples to %s", len(samples), output_path)
    LOGGER.info("Wrote preprocessing report to %s", report_path)


def _selected_adapters(dataset: str):
    adapters = [
        ("thermo_presence", preprocess_thermo_presence),
        ("mldetection", preprocess_mldetection),
        ("skku", preprocess_skku),
        ("yolo", preprocess_yolo),
        ("recorded", preprocess_recorded),
    ]
    if dataset == "all":
        return adapters
    return [item for item in adapters if item[0] == dataset]


def preprocess_thermo_presence(root: Path) -> Iterable[ThermalSample]:
    dataset_root = root / "thermo_presence"
    if not _require_dir(dataset_root, "thermo_presence"):
        return

    hdf_files = _files(dataset_root, {".h5", ".hdf5", ".hdf"})
    if not hdf_files:
        LOGGER.warning("thermo_presence: no HDF5 files found in %s", dataset_root)
        return

    for file_path in hdf_files:
        yield from _samples_from_hdf5(
            file_path,
            dataset="thermo_presence",
            preferred_annotation="center",
            source_units="celsius",
        )


def preprocess_mldetection(root: Path) -> Iterable[ThermalSample]:
    dataset_root = root / "mldetection"
    if not _require_dir(dataset_root, "mldetection"):
        return

    yielded = 0
    for file_path in _files(dataset_root, {".h5", ".hdf5", ".hdf"}):
        for sample in _samples_from_hdf5(
            file_path,
            dataset="mldetection",
            preferred_annotation="box",
            source_units="celsius",
        ):
            yielded += 1
            yield sample

    for file_path in _files(dataset_root, {".json"}):
        for sample in _samples_from_json(
            file_path,
            dataset="mldetection",
            source_units="celsius",
        ):
            yielded += 1
            yield sample

    if yielded == 0:
        LOGGER.warning(
            "mldetection: no samples parsed. Expected HDF5/JSON frames with boxes."
        )


def preprocess_skku(root: Path) -> Iterable[ThermalSample]:
    dataset_root = root / "skku_thermal_human"
    if not _require_dir(dataset_root, "skku"):
        return

    yielded = 0
    for file_path in _files(dataset_root, {".h5", ".hdf5", ".hdf"}):
        for sample in _samples_from_hdf5(
            file_path,
            dataset="skku",
            preferred_annotation="box",
            source_units="unknown",
        ):
            yielded += 1
            yield sample

    for file_path in _files(dataset_root, {".npy", ".npz"}):
        for sample in _samples_from_np(
            file_path,
            dataset="skku",
            source_units="unknown",
        ):
            yielded += 1
            yield sample

    for sample in _samples_from_images(
        dataset_root,
        dataset="skku",
        source_units="normalized_image",
    ):
        yielded += 1
        yield sample

    if yielded == 0:
        LOGGER.warning("skku: no usable HDF5/NP/Image samples found.")


def preprocess_yolo(root: Path) -> Iterable[ThermalSample]:
    dataset_root = root / "yolov8_thermal"
    if not _require_dir(dataset_root, "yolo"):
        return

    yielded = 0
    for sample in _samples_from_images(
        dataset_root,
        dataset="yolo",
        source_units="normalized_image",
    ):
        yielded += 1
        yield sample

    if yielded == 0:
        LOGGER.warning("yolo: no image/YOLO-label pairs found in %s", dataset_root)


def preprocess_recorded(root: Path) -> Iterable[ThermalSample]:
    if not _require_dir(root, "recorded"):
        return

    npy_files = _files(root, {".npy"})
    if not npy_files:
        LOGGER.warning("recorded: no .npy frames found in %s", root)
        return

    for file_path in npy_files:
        label = _label_from_recorded_path(file_path)
        try:
            frame = resize_to_mlx90640(np.load(file_path).astype(np.float32))
        except Exception as exc:
            LOGGER.warning("recorded: skipping %s: %s", file_path, exc)
            continue

        frame, source_units, input_domain = normalize_frame(frame, "celsius")
        mask = (
            _mask_from_temperature(frame)
            if label == "positive"
            else np.zeros((HEIGHT, WIDTH), dtype=np.float32)
        )
        yield ThermalSample(
            frame=frame,
            mask=mask,
            source=str(file_path),
            source_id=_source_id(file_path, dataset="recorded", group_parent=True),
            dataset="recorded",
            source_units=source_units,
            input_domain=input_domain,
            annotation_type=f"recorded_{label}",
        )


def _samples_from_hdf5(
    file_path: Path,
    *,
    dataset: str,
    preferred_annotation: str,
    source_units: str,
) -> Iterable[ThermalSample]:
    if h5py is None:
        LOGGER.warning("%s: h5py is not installed; skipping %s", dataset, file_path)
        return

    try:
        with h5py.File(file_path, "r") as handle:
            arrays = _collect_hdf5_datasets(handle)
    except Exception as exc:
        LOGGER.warning("%s: cannot read %s: %s", dataset, file_path, exc)
        return

    frame_arrays = [
        value for _, value in arrays.items() if _looks_like_frame_array(value)
    ]
    if not frame_arrays:
        LOGGER.warning("%s: no 32x24-like frame arrays in %s", dataset, file_path)
        return

    labels = _label_arrays(arrays)
    for frame_array in frame_arrays:
        frames = _normalize_frame_batch(frame_array)
        if not frames:
            continue

        centers = _matching_label(labels["centers"], len(frames))
        boxes = _matching_label(labels["boxes"], len(frames))
        if preferred_annotation == "center" and centers is None:
            LOGGER.warning("%s: no center labels for %s", dataset, file_path)
        if preferred_annotation == "box" and boxes is None:
            LOGGER.warning("%s: no box labels for %s", dataset, file_path)

        for index, frame in enumerate(frames):
            mask = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
            annotation_type = "none"
            if centers is not None:
                mask = np.maximum(mask, _mask_from_centers(centers[index]))
                annotation_type = "center"
            if boxes is not None:
                mask = np.maximum(mask, _mask_from_boxes(boxes[index]))
                annotation_type = (
                    "center+box" if annotation_type == "center" else "box"
                )
            if not np.any(mask):
                continue

            normalized, resolved_units, input_domain = normalize_frame(
                frame,
                source_units,
            )
            yield ThermalSample(
                frame=normalized,
                mask=mask,
                source=f"{file_path}#{index}",
                source_id=_source_id(file_path, dataset=dataset),
                dataset=dataset,
                source_units=resolved_units,
                input_domain=input_domain,
                annotation_type=annotation_type,
            )


def _samples_from_json(
    file_path: Path,
    *,
    dataset: str,
    source_units: str,
) -> Iterable[ThermalSample]:
    try:
        decoded = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:
        LOGGER.warning("%s: skipping malformed JSON %s: %s", dataset, file_path, exc)
        return

    entries = decoded if isinstance(decoded, list) else [decoded]
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        raw_frame = (
            entry.get("temperatures")
            or entry.get("frame")
            or entry.get("thermal")
            or entry.get("pixels")
        )
        if raw_frame is None:
            continue
        try:
            frame = resize_to_mlx90640(np.asarray(raw_frame, dtype=np.float32))
        except Exception as exc:
            LOGGER.warning("%s: skipping JSON frame %s#%d: %s", dataset, file_path, index, exc)
            continue

        mask = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
        annotation_type = "none"
        if entry.get("boxes") or entry.get("bboxes"):
            mask = np.maximum(
                mask,
                _mask_from_boxes(np.asarray(entry.get("boxes") or entry.get("bboxes"))),
            )
            annotation_type = "box"
        if entry.get("centers") or entry.get("points"):
            mask = np.maximum(
                mask,
                _mask_from_centers(np.asarray(entry.get("centers") or entry.get("points"))),
            )
            annotation_type = "center" if annotation_type == "none" else "center+box"
        if not np.any(mask):
            continue

        normalized, resolved_units, input_domain = normalize_frame(frame, source_units)
        yield ThermalSample(
            frame=normalized,
            mask=mask,
            source=f"{file_path}#{index}",
            source_id=_source_id(file_path, dataset=dataset),
            dataset=dataset,
            source_units=resolved_units,
            input_domain=input_domain,
            annotation_type=annotation_type,
        )


def _samples_from_np(
    file_path: Path,
    *,
    dataset: str,
    source_units: str,
) -> Iterable[ThermalSample]:
    try:
        if file_path.suffix.lower() == ".npz":
            archive = np.load(file_path, allow_pickle=True)
            frames = archive["frames"] if "frames" in archive.files else None
            masks = archive["masks"] if "masks" in archive.files else None
            boxes = archive["boxes"] if "boxes" in archive.files else None
            centers = archive["centers"] if "centers" in archive.files else None
        else:
            frames = np.load(file_path, allow_pickle=True)
            masks = boxes = centers = None
    except Exception as exc:
        LOGGER.warning("%s: skipping %s: %s", dataset, file_path, exc)
        return

    if frames is None:
        return
    frame_list = _normalize_frame_batch(frames)
    mask_list = _normalize_mask_batch(masks, len(frame_list)) if masks is not None else None
    box_list = _matching_label([boxes], len(frame_list)) if boxes is not None else None
    center_list = _matching_label([centers], len(frame_list)) if centers is not None else None

    for index, frame in enumerate(frame_list):
        mask = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
        annotation_type = "none"
        if mask_list is not None:
            mask = np.maximum(mask, mask_list[index])
            annotation_type = "mask"
        if box_list is not None:
            mask = np.maximum(mask, _mask_from_boxes(box_list[index]))
            annotation_type = "box" if annotation_type == "none" else f"{annotation_type}+box"
        if center_list is not None:
            mask = np.maximum(mask, _mask_from_centers(center_list[index]))
            annotation_type = "center" if annotation_type == "none" else f"{annotation_type}+center"
        if not np.any(mask):
            continue
        normalized, resolved_units, input_domain = normalize_frame(frame, source_units)
        yield ThermalSample(
            frame=normalized,
            mask=mask,
            source=f"{file_path}#{index}",
            source_id=_source_id(file_path, dataset=dataset),
            dataset=dataset,
            source_units=resolved_units,
            input_domain=input_domain,
            annotation_type=annotation_type,
        )


def _samples_from_images(
    root: Path,
    *,
    dataset: str,
    source_units: str,
) -> Iterable[ThermalSample]:
    if Image is None:
        LOGGER.warning("%s: Pillow is not installed; skipping images", dataset)
        return

    for image_path in _files(root, {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}):
        label_path = _find_label_for_image(image_path)
        if label_path is None:
            LOGGER.warning("%s: no label file for image %s", dataset, image_path)
            continue

        try:
            with Image.open(image_path) as image:
                image_size = image.size
                frame = resize_to_mlx90640(np.asarray(image.convert("L"), dtype=np.float32))
        except Exception as exc:
            LOGGER.warning("%s: cannot read image %s: %s", dataset, image_path, exc)
            continue

        mask, annotation_type = _mask_from_label_file(label_path, image_size)
        if not np.any(mask):
            LOGGER.warning("%s: empty mask from %s", dataset, label_path)
            continue

        normalized, resolved_units, input_domain = normalize_frame(frame, source_units)
        yield ThermalSample(
            frame=normalized,
            mask=mask,
            source=str(image_path),
            source_id=_source_id(image_path, dataset=dataset),
            dataset=dataset,
            source_units=resolved_units,
            input_domain=input_domain,
            annotation_type=annotation_type,
        )


def normalize_frame(frame: np.ndarray, source_units: str) -> tuple[np.ndarray, str, str]:
    frame = resize_to_mlx90640(frame)
    finite = frame[np.isfinite(frame)]
    if finite.size == 0:
        return np.zeros((HEIGHT, WIDTH), dtype=np.float32), "unknown", "image_domain"

    min_value = float(np.min(finite))
    max_value = float(np.max(finite))
    if source_units == "celsius":
        return np.clip(frame, 0.0, 80.0).astype(np.float32), "celsius", "celsius"

    if source_units == "unknown":
        if 0.0 <= min_value and max_value <= 1.5:
            return np.clip(frame, 0.0, 1.0).astype(np.float32), "unknown", "image_domain"
        if -20.0 <= min_value and max_value <= 120.0:
            return np.clip(frame, 0.0, 80.0).astype(np.float32), "celsius", "celsius"

    return _robust_image_normalize(frame), source_units, "image_domain"


def resize_to_mlx90640(array: np.ndarray) -> np.ndarray:
    array = np.asarray(array, dtype=np.float32)
    if array.ndim == 1:
        if array.size == WIDTH * HEIGHT:
            array = array.reshape(HEIGHT, WIDTH)
        else:
            side = int(math.sqrt(array.size))
            if side <= 1:
                raise ValueError(f"Cannot reshape flat array of size {array.size}")
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
    return resized.astype(np.float32)


def _robust_image_normalize(frame: np.ndarray) -> np.ndarray:
    finite = frame[np.isfinite(frame)]
    low = float(np.percentile(finite, 2))
    high = float(np.percentile(finite, 98))
    if high <= low:
        high = low + 1.0
    normalized = np.clip((frame - low) / (high - low), 0.0, 1.0)
    return normalized.astype(np.float32)


def _mask_from_label_file(
    label_path: Path,
    image_size: tuple[int, int],
) -> tuple[np.ndarray, str]:
    suffix = label_path.suffix.lower()
    if suffix == ".txt":
        return _mask_from_yolo_txt(label_path), "yolo_box"
    if suffix == ".xml":
        return _mask_from_voc_xml(label_path, image_size), "voc_box"
    if suffix == ".json":
        try:
            decoded = json.loads(label_path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.warning("Skipping malformed label JSON %s: %s", label_path, exc)
            return np.zeros((HEIGHT, WIDTH), dtype=np.float32), "json_error"
        mask = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
        annotation_type = "none"
        if decoded.get("boxes") or decoded.get("bboxes"):
            mask = np.maximum(mask, _mask_from_boxes(np.asarray(decoded.get("boxes") or decoded.get("bboxes"))))
            annotation_type = "json_box"
        if decoded.get("centers") or decoded.get("points"):
            mask = np.maximum(mask, _mask_from_centers(np.asarray(decoded.get("centers") or decoded.get("points"))))
            annotation_type = "json_center" if annotation_type == "none" else f"{annotation_type}+center"
        return mask, annotation_type
    return np.zeros((HEIGHT, WIDTH), dtype=np.float32), "unknown"


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


def _mask_from_voc_xml(label_path: Path, image_size: tuple[int, int]) -> np.ndarray:
    mask = np.zeros((HEIGHT, WIDTH), dtype=np.float32)
    try:
        root = ET.parse(label_path).getroot()
    except Exception as exc:
        LOGGER.warning("Skipping malformed VOC label %s: %s", label_path, exc)
        return mask

    image_w, image_h = image_size
    boxes = []
    for box in root.findall(".//bndbox"):
        try:
            xmin = float(box.findtext("xmin", "0")) / max(image_w, 1)
            ymin = float(box.findtext("ymin", "0")) / max(image_h, 1)
            xmax = float(box.findtext("xmax", "0")) / max(image_w, 1)
            ymax = float(box.findtext("ymax", "0")) / max(image_h, 1)
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
        if box.size < 4 or not np.all(np.isfinite(box[:4])):
            continue
        x1, y1, x2, y2 = _box_to_xyxy(box[:4])
        x1_i = int(np.clip(np.floor(x1 * WIDTH), 0, WIDTH - 1))
        x2_i = int(np.clip(np.ceil(x2 * WIDTH), x1_i + 1, WIDTH))
        y1_i = int(np.clip(np.floor(y1 * HEIGHT), 0, HEIGHT - 1))
        y2_i = int(np.clip(np.ceil(y2 * HEIGHT), y1_i + 1, HEIGHT))
        mask[y1_i:y2_i, x1_i:x2_i] = 1.0
    return mask


def _box_to_xyxy(box: np.ndarray) -> tuple[float, float, float, float]:
    a, b, c, d = [float(value) for value in box]
    if 0 <= a <= 1 and 0 <= b <= 1 and 0 <= c <= 1 and 0 <= d <= 1:
        if c <= a or d <= b:
            return (
                max(0.0, a - c / 2),
                max(0.0, b - d / 2),
                min(1.0, a + c / 2),
                min(1.0, b + d / 2),
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
        if center.size < 2 or not np.all(np.isfinite(center[:2])):
            continue
        x = float(center[0])
        y = float(center[1])
        if x < 0 or y < 0:
            continue
        if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
            x *= WIDTH
            y *= HEIGHT
        for yy in range(HEIGHT):
            for xx in range(WIDTH):
                if (xx - x) ** 2 + (yy - y) ** 2 <= radius**2:
                    mask[yy, xx] = 1.0
    return mask


def _mask_from_temperature(frame: np.ndarray) -> np.ndarray:
    if float(np.max(frame)) <= 1.0:
        return (frame >= 0.55).astype(np.float32)
    return ((frame >= 30.0) & (frame <= 40.0)).astype(np.float32)


def _collect_hdf5_datasets(handle: object) -> dict[str, np.ndarray]:
    arrays: dict[str, np.ndarray] = {}

    def visit(name: str, node: object) -> None:
        if h5py is not None and isinstance(node, h5py.Dataset):
            try:
                arrays[name.lower()] = np.asarray(node)
            except Exception:
                return

    handle.visititems(visit)
    return arrays


def _label_arrays(arrays: dict[str, np.ndarray]) -> dict[str, list[np.ndarray]]:
    centers = []
    boxes = []
    for key, value in arrays.items():
        if not _looks_like_label_array(value):
            continue
        if any(token in key for token in ("center", "coord", "point", "position")):
            centers.append(value)
        elif any(token in key for token in ("box", "bbox", "bound")):
            boxes.append(value)
    return {"centers": centers, "boxes": boxes}


def _matching_label(candidates: list[np.ndarray | None], n_frames: int) -> np.ndarray | None:
    for candidate in candidates:
        if candidate is None:
            continue
        array = np.asarray(candidate)
        if array.shape[0] == n_frames:
            return array
        if n_frames == 1 and array.ndim >= 1:
            return array.reshape(1, *array.shape)
    return None


def _normalize_frame_batch(array: np.ndarray) -> list[np.ndarray]:
    array = np.asarray(array, dtype=np.float32)
    if array.ndim == 2:
        return [resize_to_mlx90640(array)]
    if array.ndim == 3:
        return [resize_to_mlx90640(frame) for frame in array]
    if array.ndim == 4 and array.shape[-1] == 1:
        return [resize_to_mlx90640(frame[..., 0]) for frame in array]
    return []


def _normalize_mask_batch(array: np.ndarray, n_frames: int) -> list[np.ndarray]:
    masks = _normalize_frame_batch(array)
    if len(masks) == 1 and n_frames > 1:
        masks *= n_frames
    return [(mask > 0.5).astype(np.float32) for mask in masks[:n_frames]]


def _looks_like_frame_array(value: np.ndarray) -> bool:
    value = np.asarray(value)
    return value.ndim >= 2 and (
        value.shape[-2:] in {(HEIGHT, WIDTH), (WIDTH, HEIGHT)}
        or value.shape[-3:-1] in {(HEIGHT, WIDTH), (WIDTH, HEIGHT)}
    )


def _looks_like_label_array(value: np.ndarray) -> bool:
    value = np.asarray(value)
    return value.ndim >= 1 and value.shape[-1] >= 2 and value.shape[-1] <= 8


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


def _files(root: Path, suffixes: set[str]) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    )


def _require_dir(path: Path, dataset: str) -> bool:
    if path.is_dir():
        return True
    LOGGER.warning("%s: expected directory not found: %s", dataset, path)
    return False


def _source_id(path: Path, *, dataset: str, group_parent: bool = False) -> str:
    group = path.parent if group_parent else path
    return f"{dataset}:{group.as_posix()}"


def _label_from_recorded_path(path: Path) -> str:
    lowered = path.as_posix().lower()
    if "positive" in lowered or "/human" in lowered or "\\human" in lowered:
        return "positive"
    return "negative"


def _build_report(samples: list[ThermalSample], presence: np.ndarray) -> dict[str, object]:
    datasets = sorted(set(sample.dataset for sample in samples))
    return {
        "sample_count": len(samples),
        "positive_count": int(np.sum(presence)),
        "negative_count": int(len(presence) - np.sum(presence)),
        "datasets": {
            dataset: {
                "count": sum(1 for sample in samples if sample.dataset == dataset),
                "source_units": sorted(
                    set(sample.source_units for sample in samples if sample.dataset == dataset)
                ),
                "input_domains": sorted(
                    set(sample.input_domain for sample in samples if sample.dataset == dataset)
                ),
                "annotation_types": sorted(
                    set(sample.annotation_type for sample in samples if sample.dataset == dataset)
                ),
            }
            for dataset in datasets
        },
    }


if __name__ == "__main__":
    main()
