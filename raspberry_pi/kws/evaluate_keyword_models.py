#!/usr/bin/env python3
"""Evaluate keyword model prediction files and write Project Pi metrics JSON."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def _safe_divide(numerator: float, denominator: float) -> float | None:
    # None (JSON null) = not estimable; e.g. recall with no positive samples is unknown, not 0.
    return None if denominator == 0 else round(numerator / denominator, 6)


def compute_binary_metrics(
    predictions: list[dict[str, object]],
    threshold: float,
    negative_hours: float | None = None,
) -> dict[str, object]:
    true_positives = false_positives = true_negatives = false_negatives = 0
    for row in predictions:
        label = int(row.get("label", 0))
        score = float(row.get("score", 0))
        predicted = score >= threshold
        if label == 1 and predicted:
            true_positives += 1
        elif label == 1:
            false_negatives += 1
        elif predicted:
            false_positives += 1
        else:
            true_negatives += 1

    precision = _safe_divide(true_positives, true_positives + false_positives)
    recall = _safe_divide(true_positives, true_positives + false_negatives)
    if precision is None or recall is None:
        f1 = None
    elif precision + recall == 0:
        f1 = 0.0  # both defined and zero: the detector found nothing it should have
    else:
        f1 = round(2 * precision * recall / (precision + recall), 6)
    # Recording-level: false-positive recordings per hour of negative audio. A recording
    # with several false alerts counts once here; event-level rates need event counts.
    false_accepts_per_hour = None
    if negative_hours and negative_hours > 0:
        false_accepts_per_hour = round(false_positives / negative_hours, 6)

    return {
        "threshold": threshold,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "true_negatives": true_negatives,
        "false_negatives": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "specificity": _safe_divide(true_negatives, true_negatives + false_positives),
        "false_positive_rate": _safe_divide(false_positives, false_positives + true_negatives),
        "false_negative_rate": _safe_divide(false_negatives, false_negatives + true_positives),
        "false_accepts_per_hour": false_accepts_per_hour,
        "denominators": {
            "precision": true_positives + false_positives,
            "recall": true_positives + false_negatives,
            "specificity": true_negatives + false_positives,
            "false_positive_rate": false_positives + true_negatives,
            "false_negative_rate": false_negatives + true_positives,
            "negative_hours": negative_hours,
        },
        "confusion_matrix": {
            "actual_positive": {
                "predicted_positive": true_positives,
                "predicted_negative": false_negatives,
            },
            "actual_negative": {
                "predicted_positive": false_positives,
                "predicted_negative": true_negatives,
            },
        },
    }


def load_predictions(path: Path) -> list[dict[str, object]]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("predictions", [])
        return list(data)
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def evaluate_prediction_dir(
    predictions_dir: Path,
    threshold: float,
    negative_hours: float | None,
) -> dict[str, object]:
    results = {}
    for path in sorted(predictions_dir.glob("*")):
        if path.suffix.lower() not in {".json", ".csv"}:
            continue
        keyword = path.stem
        predictions = load_predictions(path)
        results[keyword] = compute_binary_metrics(
            predictions,
            threshold=threshold,
            negative_hours=negative_hours,
        )
    return {"keywords": results}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compute precision/recall/F1/false-accept metrics from held-out "
            "prediction files. Each row must include label and score."
        )
    )
    parser.add_argument("--predictions-dir", type=Path, required=True)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--negative-hours", type=float)
    parser.add_argument("--json-out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = evaluate_prediction_dir(
        args.predictions_dir,
        threshold=args.threshold,
        negative_hours=args.negative_hours,
    )
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote evaluation metrics: {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
