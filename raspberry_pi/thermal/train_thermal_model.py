#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np


WIDTH = 32
HEIGHT = 24
DEFAULT_DATA = (
    Path.home() / "thesis_dataset" / "thermal" / "processed" / "thermal_human_detection.npz"
)
DEFAULT_OUTPUT_DIR = Path("raspberry_pi/thermal/models")
THRESHOLDS = np.round(np.arange(0.05, 1.0, 0.05), 2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the Project Pi thermal human detector.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--validation-split", type=float, default=0.15)
    parser.add_argument("--test-split", type=float, default=0.15)
    parser.add_argument(
        "--split-by",
        choices=("source_id", "source_file", "session_id", "subject", "random"),
        default="source_id",
        help="Group key for train/val/test split. Use random only for debugging.",
    )
    parser.add_argument(
        "--selection-metric",
        choices=("f1", "precision", "recall"),
        default="f1",
        help="Metric used to choose the deployment threshold from validation data.",
    )
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    import tensorflow as tf

    tf.random.set_seed(args.seed)

    data = load_dataset(args.data.expanduser())
    splits, split_report = make_splits(
        data,
        validation_split=args.validation_split,
        test_split=args.test_split,
        split_by=args.split_by,
        seed=args.seed,
    )

    train_ds = make_tf_dataset(data, splits["train"], args.batch_size, training=True)
    val_ds = make_tf_dataset(data, splits["val"], args.batch_size, training=False)
    test_ds = make_tf_dataset(data, splits["test"], args.batch_size, training=False)

    model = build_model(learning_rate=args.learning_rate)
    model.summary()

    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_presence_auc",
            mode="max",
            patience=8,
            restore_best_weights=True,
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_presence_loss",
            mode="min",
            factor=0.5,
            patience=4,
        ),
    ]

    history = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=args.epochs,
        callbacks=callbacks,
    )

    val_scores = predict_presence(model, val_ds)
    test_scores = predict_presence(model, test_ds)
    calibration = calibrate_threshold(
        val_scores["y_true"],
        val_scores["y_score"],
        selection_metric=args.selection_metric,
    )
    threshold = float(calibration["best"]["threshold"])
    test_metrics = metrics_at_threshold(
        test_scores["y_true"],
        test_scores["y_score"],
        threshold,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    keras_path = args.output_dir / "thermal_human_detector.keras"
    tflite_path = args.output_dir / "thermal_human_detector.tflite"
    metrics_path = args.output_dir / "thermal_human_detector_metrics.json"
    metadata_path = args.output_dir / "thermal_human_detector.metadata.json"
    split_path = args.output_dir / "split.json"
    pr_curve_path = args.output_dir / "thermal_human_detector_pr_curve.png"
    pr_curve_csv_path = args.output_dir / "thermal_human_detector_pr_curve.csv"

    model.save(keras_path)
    convert_to_tflite(model, tflite_path)
    save_split_report(split_report, split_path)
    save_pr_curve(
        calibration["sweep"],
        pr_curve_path=pr_curve_path,
        csv_path=pr_curve_csv_path,
    )

    metrics_payload = {
        "validation": calibration,
        "test": test_metrics,
        "data": str(args.data.expanduser()),
        "history": {
            key: [float(value) for value in values]
            for key, values in history.history.items()
        },
    }
    metrics_path.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")

    metadata = build_metadata(
        data=data,
        args=args,
        calibration=calibration,
        test_metrics=test_metrics,
        split_report=split_report,
    )
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(json.dumps({"best_threshold": calibration["best"], "test": test_metrics}, indent=2))
    print(f"Saved Keras model: {keras_path}")
    print(f"Saved TFLite model: {tflite_path}")
    print(f"Saved split assignment: {split_path}")
    print(f"Saved PR curve: {pr_curve_path if pr_curve_path.exists() else pr_curve_csv_path}")
    print(f"Saved metadata: {metadata_path}")


def load_dataset(path: Path) -> dict[str, np.ndarray]:
    archive = np.load(path, allow_pickle=True)
    frames = archive["frames"].astype(np.float32)
    masks = archive["masks"].astype(np.float32)
    presence = archive["presence"].astype(np.float32).reshape(-1, 1)

    if frames.ndim != 3 or frames.shape[1:] != (HEIGHT, WIDTH):
        raise ValueError(f"frames must have shape (N, {HEIGHT}, {WIDTH}), got {frames.shape}")
    if masks.shape != frames.shape:
        raise ValueError(f"masks must match frames shape, got {masks.shape}")

    n_samples = frames.shape[0]
    source_ids = _archive_array(archive, "source_ids", n_samples, "unknown")
    sources = _archive_array(archive, "sources", n_samples, "unknown")
    source_units = _archive_array(archive, "source_units", n_samples, "unknown")
    input_domains = _archive_array(archive, "input_domains", n_samples, "unknown")
    dataset_names = _archive_array(archive, "dataset_names", n_samples, "unknown")
    annotation_types = _archive_array(archive, "annotation_types", n_samples, "unknown")

    model_frames = np.stack(
        [
            normalize_for_model(frame, input_domain=str(input_domains[index]))
            for index, frame in enumerate(frames)
        ]
    ).astype(np.float32)

    return {
        "frames": model_frames,
        "masks": (masks > 0.5).astype(np.float32),
        "presence": presence,
        "source_ids": source_ids.astype(str),
        "sources": sources.astype(str),
        "source_units": source_units.astype(str),
        "input_domains": input_domains.astype(str),
        "dataset_names": dataset_names.astype(str),
        "annotation_types": annotation_types.astype(str),
    }


def _archive_array(archive: Any, key: str, n_samples: int, default: str) -> np.ndarray:
    if key in archive.files:
        values = np.asarray(archive[key], dtype=object)
        if values.shape[0] == n_samples:
            return values
    return np.asarray([default] * n_samples, dtype=object)


def normalize_for_model(frame: np.ndarray, *, input_domain: str) -> np.ndarray:
    frame = np.asarray(frame, dtype=np.float32)
    if input_domain == "celsius":
        return np.clip(frame, 0.0, 80.0) / 80.0
    if float(np.nanmax(frame)) <= 1.0 and float(np.nanmin(frame)) >= 0.0:
        return np.clip(frame, 0.0, 1.0)
    finite = frame[np.isfinite(frame)]
    low = float(np.percentile(finite, 2))
    high = float(np.percentile(finite, 98))
    if high <= low:
        high = low + 1.0
    return np.clip((frame - low) / (high - low), 0.0, 1.0)


def make_splits(
    data: dict[str, np.ndarray],
    *,
    validation_split: float,
    test_split: float,
    split_by: str,
    seed: int,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    n_samples = len(data["frames"])
    if split_by == "random":
        indices = np.arange(n_samples)
        rng = np.random.default_rng(seed)
        rng.shuffle(indices)
        test_count = int(n_samples * test_split)
        val_count = int(n_samples * validation_split)
        splits = {
            "test": indices[:test_count],
            "val": indices[test_count : test_count + val_count],
            "train": indices[test_count + val_count :],
        }
        return splits, _split_report(data, splits, split_by=split_by)

    group_keys = group_keys_for_split(data, split_by)
    groups: dict[str, list[int]] = defaultdict(list)
    for index, group_key in enumerate(group_keys):
        groups[str(group_key)].append(index)

    rng = random.Random(seed)
    group_items = list(groups.items())
    rng.shuffle(group_items)

    total = n_samples
    target_test = int(total * test_split)
    target_val = int(total * validation_split)
    buckets: dict[str, list[int]] = {"train": [], "val": [], "test": []}
    group_assignments: dict[str, str] = {}

    for group_key, indices in group_items:
        if len(buckets["test"]) < target_test:
            split = "test"
        elif len(buckets["val"]) < target_val:
            split = "val"
        else:
            split = "train"
        buckets[split].extend(indices)
        group_assignments[group_key] = split

    splits = {
        split: np.asarray(sorted(indices), dtype=np.int64)
        for split, indices in buckets.items()
    }
    report = _split_report(data, splits, split_by=split_by)
    report["group_assignments"] = group_assignments
    return splits, report


def group_keys_for_split(data: dict[str, np.ndarray], split_by: str) -> np.ndarray:
    if split_by == "source_id":
        return data["source_ids"]
    if split_by == "source_file":
        return np.asarray([str(source).split("#")[0] for source in data["sources"]])
    if split_by == "session_id":
        return np.asarray([_extract_token(value, "session") for value in data["source_ids"]])
    if split_by == "subject":
        return np.asarray([_extract_token(value, "subject") for value in data["source_ids"]])
    raise ValueError(f"Unsupported split_by: {split_by}")


def _extract_token(value: str, token_type: str) -> str:
    pattern = r"(session|sess|subject|subj|person|user)[-_ ]?([a-zA-Z0-9]+)"
    matches = re_findall(pattern, value)
    preferred = {
        "session": {"session", "sess"},
        "subject": {"subject", "subj", "person", "user"},
    }[token_type]
    for key, token in matches:
        if key.lower() in preferred:
            return f"{token_type}:{token}"
    return str(value).split("#")[0]


def re_findall(pattern: str, value: str) -> list[tuple[str, str]]:
    import re

    return re.findall(pattern, str(value), flags=re.IGNORECASE)


def _split_report(
    data: dict[str, np.ndarray],
    splits: dict[str, np.ndarray],
    *,
    split_by: str,
) -> dict[str, Any]:
    report = {"split_by": split_by, "splits": {}}
    for split, indices in splits.items():
        labels = data["presence"][indices].reshape(-1)
        datasets = Counter(data["dataset_names"][indices].tolist())
        domains = Counter(data["input_domains"][indices].tolist())
        report["splits"][split] = {
            "sample_count": int(len(indices)),
            "positive_count": int(np.sum(labels)),
            "negative_count": int(len(labels) - np.sum(labels)),
            "datasets": dict(datasets),
            "input_domains": dict(domains),
            "indices": indices.astype(int).tolist(),
            "source_ids": sorted(set(data["source_ids"][indices].tolist())),
        }
    return report


def save_split_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def make_tf_dataset(
    data: dict[str, np.ndarray],
    indices: np.ndarray,
    batch_size: int,
    *,
    training: bool,
):
    import tensorflow as tf

    x = data["frames"][indices][..., None]
    y_presence = data["presence"][indices]
    y_mask = data["masks"][indices][..., None]

    dataset = tf.data.Dataset.from_tensor_slices(
        (x, {"presence": y_presence, "mask": y_mask})
    )
    if training:
        dataset = dataset.shuffle(min(len(indices), 4096), reshuffle_each_iteration=True)
        dataset = dataset.map(augment, num_parallel_calls=tf.data.AUTOTUNE)
    return dataset.batch(batch_size).prefetch(tf.data.AUTOTUNE)


def augment(frame, targets):
    import tensorflow as tf

    noise = tf.random.normal(tf.shape(frame), mean=0.0, stddev=0.015)
    temp_shift = tf.random.uniform([], minval=-0.04, maxval=0.04)
    frame = tf.clip_by_value(frame + noise + temp_shift, 0.0, 1.0)

    do_flip = tf.random.uniform([]) > 0.5
    frame = tf.cond(do_flip, lambda: tf.reverse(frame, axis=[1]), lambda: frame)
    targets["mask"] = tf.cond(
        do_flip,
        lambda: tf.reverse(targets["mask"], axis=[1]),
        lambda: targets["mask"],
    )
    return frame, targets


def build_model(*, learning_rate: float):
    import tensorflow as tf

    inputs = tf.keras.Input(shape=(HEIGHT, WIDTH, 1), name="thermal_frame")

    x = tf.keras.layers.Conv2D(12, 3, padding="same", activation="relu")(inputs)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.SeparableConv2D(16, 3, padding="same", activation="relu")(x)
    x = tf.keras.layers.MaxPooling2D()(x)
    x = tf.keras.layers.SeparableConv2D(24, 3, padding="same", activation="relu")(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.SeparableConv2D(32, 3, padding="same", activation="relu")(x)

    pooled = tf.keras.layers.GlobalAveragePooling2D()(x)
    pooled = tf.keras.layers.Dense(24, activation="relu")(pooled)
    pooled = tf.keras.layers.Dropout(0.15)(pooled)
    presence = tf.keras.layers.Dense(1, activation="sigmoid", name="presence")(pooled)

    mask = tf.keras.layers.UpSampling2D()(x)
    mask = tf.keras.layers.Conv2D(16, 3, padding="same", activation="relu")(mask)
    mask = tf.keras.layers.Conv2D(1, 1, activation="sigmoid", name="mask")(mask)

    model = tf.keras.Model(inputs=inputs, outputs={"presence": presence, "mask": mask})
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate),
        loss={
            "presence": "binary_crossentropy",
            "mask": "binary_crossentropy",
        },
        loss_weights={
            "presence": 1.0,
            "mask": 0.35,
        },
        metrics={
            "presence": [
                tf.keras.metrics.BinaryAccuracy(name="accuracy"),
                tf.keras.metrics.Precision(name="precision"),
                tf.keras.metrics.Recall(name="recall"),
                tf.keras.metrics.AUC(name="auc"),
            ],
            "mask": [tf.keras.metrics.BinaryAccuracy(name="mask_accuracy")],
        },
    )
    return model


def predict_presence(model, dataset) -> dict[str, np.ndarray]:
    y_true: list[float] = []
    y_score: list[float] = []
    for frames, targets in dataset:
        predictions = model.predict(frames, verbose=0)
        y_true.extend(targets["presence"].numpy().reshape(-1).tolist())
        y_score.extend(np.asarray(predictions["presence"]).reshape(-1).tolist())
    return {
        "y_true": np.asarray(y_true, dtype=np.int32),
        "y_score": np.asarray(y_score, dtype=np.float32),
    }


def calibrate_threshold(
    y_true: np.ndarray,
    y_score: np.ndarray,
    *,
    selection_metric: str,
) -> dict[str, Any]:
    sweep = [
        metrics_at_threshold(y_true, y_score, float(threshold))
        for threshold in THRESHOLDS
    ]
    best = max(sweep, key=lambda item: (item[selection_metric], item["recall"]))
    return {"selection_metric": selection_metric, "best": best, "sweep": sweep}


def metrics_at_threshold(
    y_true: np.ndarray,
    y_score: np.ndarray,
    threshold: float,
) -> dict[str, float | int]:
    y_true = np.asarray(y_true, dtype=np.int32)
    y_pred = (np.asarray(y_score, dtype=np.float32) >= threshold).astype(np.int32)

    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    tn = int(np.sum((y_true == 0) & (y_pred == 0)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))

    accuracy = (tp + tn) / max(len(y_true), 1)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = (2 * precision * recall) / max(precision + recall, 1e-6)
    false_positive_rate = fp / max(fp + tn, 1)

    return {
        "threshold": round(float(threshold), 2),
        "accuracy": round(float(accuracy), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "false_positive_rate": round(float(false_positive_rate), 4),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def save_pr_curve(
    sweep: list[dict[str, float | int]],
    *,
    pr_curve_path: Path,
    csv_path: Path,
) -> None:
    csv_path.write_text(
        "threshold,precision,recall,f1,false_positive_rate,tp,tn,fp,fn\n"
        + "\n".join(
            ",".join(
                str(row[key])
                for key in (
                    "threshold",
                    "precision",
                    "recall",
                    "f1",
                    "false_positive_rate",
                    "tp",
                    "tn",
                    "fp",
                    "fn",
                )
            )
            for row in sweep
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        import matplotlib.pyplot as plt
    except Exception:
        print(f"matplotlib unavailable; wrote PR CSV only: {csv_path}")
        return

    precision = [float(row["precision"]) for row in sweep]
    recall = [float(row["recall"]) for row in sweep]
    thresholds = [float(row["threshold"]) for row in sweep]
    plt.figure(figsize=(7, 5))
    plt.plot(recall, precision, marker="o")
    for x, y, threshold in zip(recall, precision, thresholds):
        plt.annotate(f"{threshold:.2f}", (x, y), fontsize=8)
    plt.xlabel("Recall")
    plt.ylabel("Precision")
    plt.title("Thermal Human Detector Precision-Recall")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(pr_curve_path)
    plt.close()


def convert_to_tflite(model, output_path: Path) -> None:
    import tensorflow as tf

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    tflite_model = converter.convert()
    output_path.write_bytes(tflite_model)


def build_metadata(
    *,
    data: dict[str, np.ndarray],
    args: argparse.Namespace,
    calibration: dict[str, Any],
    test_metrics: dict[str, Any],
    split_report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "git_commit": _git_commit(),
        "data_path": str(args.data.expanduser()),
        "dataset_sample_counts": dict(Counter(data["dataset_names"].tolist())),
        "input_domain_counts": dict(Counter(data["input_domains"].tolist())),
        "source_units_counts": dict(Counter(data["source_units"].tolist())),
        "annotation_type_counts": dict(Counter(data["annotation_types"].tolist())),
        "split_method": args.split_by,
        "split_summary": {
            name: {
                key: value
                for key, value in split.items()
                if key not in {"indices", "source_ids"}
            }
            for name, split in split_report["splits"].items()
        },
        "normalization": {
            "celsius": "clip 0-80 C then divide by 80",
            "image_domain": "robust percentile-normalized to 0-1 during preprocessing",
        },
        "optimal_threshold": calibration["best"]["threshold"],
        "optimal_threshold_metrics": calibration["best"],
        "test_metrics_at_optimal_threshold": test_metrics,
        "input_shape": [HEIGHT, WIDTH, 1],
        "outputs": {
            "presence": "sigmoid confidence 0-1",
            "mask": "32x24 sigmoid segmentation mask",
        },
    }


def _git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


if __name__ == "__main__":
    main()
