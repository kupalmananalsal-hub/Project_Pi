#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np


WIDTH = 32
HEIGHT = 24
DEFAULT_DATA = Path.home() / "thesis_dataset" / "thermal" / "processed" / "thermal_human_detection.npz"
DEFAULT_OUTPUT_DIR = Path("raspberry_pi/thermal/models")
DEFAULT_TFLITE = DEFAULT_OUTPUT_DIR / "thermal_human_detector.tflite"


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
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    import tensorflow as tf

    tf.random.set_seed(args.seed)

    data = load_dataset(args.data.expanduser())
    splits = make_splits(
        len(data["frames"]),
        validation_split=args.validation_split,
        test_split=args.test_split,
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

    metrics = evaluate_presence(model, test_ds)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    keras_path = args.output_dir / "thermal_human_detector.keras"
    tflite_path = args.output_dir / "thermal_human_detector.tflite"
    metrics_path = args.output_dir / "thermal_human_detector_metrics.json"

    model.save(keras_path)
    convert_to_tflite(model, tflite_path)

    payload = {
        "metrics": metrics,
        "data": str(args.data.expanduser()),
        "history": {
            key: [float(value) for value in values]
            for key, values in history.history.items()
        },
    }
    metrics_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(json.dumps(metrics, indent=2))
    print(f"Saved Keras model: {keras_path}")
    print(f"Saved TFLite model: {tflite_path}")
    print(f"Saved metrics: {metrics_path}")


def load_dataset(path: Path) -> dict[str, np.ndarray]:
    archive = np.load(path, allow_pickle=True)
    frames = archive["frames"].astype(np.float32)
    masks = archive["masks"].astype(np.float32)
    presence = archive["presence"].astype(np.float32)

    if frames.ndim != 3 or frames.shape[1:] != (HEIGHT, WIDTH):
        raise ValueError(f"frames must have shape (N, {HEIGHT}, {WIDTH}), got {frames.shape}")
    if masks.shape != frames.shape:
        raise ValueError(f"masks must match frames shape, got {masks.shape}")

    frames = np.clip(frames, 0.0, 80.0) / 80.0
    masks = (masks > 0.5).astype(np.float32)
    presence = presence.reshape(-1, 1)
    return {"frames": frames, "masks": masks, "presence": presence}


def make_splits(
    n_samples: int,
    *,
    validation_split: float,
    test_split: float,
    seed: int,
) -> dict[str, np.ndarray]:
    indices = np.arange(n_samples)
    rng = np.random.default_rng(seed)
    rng.shuffle(indices)

    test_count = int(n_samples * test_split)
    val_count = int(n_samples * validation_split)
    test = indices[:test_count]
    val = indices[test_count : test_count + val_count]
    train = indices[test_count + val_count :]
    return {"train": train, "val": val, "test": test}


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


def evaluate_presence(model, dataset) -> dict[str, float]:
    y_true: list[float] = []
    y_pred: list[float] = []

    for frames, targets in dataset:
        predictions = model.predict(frames, verbose=0)
        y_true.extend(targets["presence"].numpy().reshape(-1).tolist())
        y_pred.extend(predictions["presence"].reshape(-1).tolist())

    y_true_arr = np.asarray(y_true, dtype=np.int32)
    y_pred_arr = (np.asarray(y_pred, dtype=np.float32) >= 0.5).astype(np.int32)

    tp = int(np.sum((y_true_arr == 1) & (y_pred_arr == 1)))
    tn = int(np.sum((y_true_arr == 0) & (y_pred_arr == 0)))
    fp = int(np.sum((y_true_arr == 0) & (y_pred_arr == 1)))
    fn = int(np.sum((y_true_arr == 1) & (y_pred_arr == 0)))

    accuracy = (tp + tn) / max(len(y_true_arr), 1)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = (2 * precision * recall) / max(precision + recall, 1e-6)

    return {
        "accuracy": round(float(accuracy), 4),
        "precision": round(float(precision), 4),
        "recall": round(float(recall), 4),
        "f1": round(float(f1), 4),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def convert_to_tflite(model, output_path: Path) -> None:
    import tensorflow as tf

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    tflite_model = converter.convert()
    output_path.write_bytes(tflite_model)


if __name__ == "__main__":
    main()
