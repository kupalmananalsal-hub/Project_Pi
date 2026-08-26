#!/usr/bin/env python3
"""Capture raw MLX90640 frames as append-only CSV training data."""

from __future__ import annotations

import argparse
import csv
import os
import signal
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


FRAME_SIZE = 768
FIELD_NAMES = [
    "timestamp",
    "session_id",
    "label",
    "scene_type",
    "notes",
] + [f"temperature_{index}" for index in range(FRAME_SIZE)]
RUNNING = True


def default_output() -> Path:
    project_root = Path(
        os.getenv("PROJECT_PI_ROOT", Path(__file__).resolve().parents[2])
    ).expanduser()
    dataset_root = Path(os.getenv("DATASET_DIR", str(project_root / "dataset"))).expanduser()
    return dataset_root / "thermal" / "negative" / "thermal_backgrounds.csv"


def append_frame(
    output_path: Path,
    frame: Iterable[float],
    label: str,
    scene_type: str,
    notes: str,
    session_id: str,
    timestamp: str,
) -> None:
    values = list(frame)
    if len(values) != FRAME_SIZE:
        raise ValueError(f"Expected {FRAME_SIZE} temperatures, received {len(values)}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not output_path.exists() or output_path.stat().st_size == 0
    row = {
        "timestamp": timestamp,
        "session_id": session_id,
        "label": label,
        "scene_type": scene_type,
        "notes": notes,
    }
    row.update({f"temperature_{index}": value for index, value in enumerate(values)})
    with output_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELD_NAMES)
        if needs_header:
            writer.writeheader()
        writer.writerow(row)
        handle.flush()
        os.fsync(handle.fileno())


def stop(signum: int, frame: object) -> None:
    del signum, frame
    global RUNNING
    RUNNING = False


class Mlx90640Reader:
    """Lazy hardware adapter so --help and CSV helpers work off-Pi."""

    def __init__(self, address: int, refresh_rate_hz: int) -> None:
        try:
            import adafruit_mlx90640
            import board
            import busio
        except Exception as exc:
            raise RuntimeError(
                "Install adafruit-blinka and adafruit-circuitpython-mlx90640 "
                "in the Pi thermal environment."
            ) from exc

        self.buffer = [0.0] * FRAME_SIZE
        i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
        self.sensor = adafruit_mlx90640.MLX90640(i2c, address=address)
        refresh_name = f"REFRESH_{refresh_rate_hz}_HZ"
        self.sensor.refresh_rate = getattr(
            adafruit_mlx90640.RefreshRate,
            refresh_name,
            adafruit_mlx90640.RefreshRate.REFRESH_4_HZ,
        )

    def read(self) -> list[float]:
        self.sensor.getFrame(self.buffer)
        return self.buffer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture raw 32x24 MLX90640 thermal background frames into CSV."
    )
    parser.add_argument("--label", required=True, help="Label, e.g. hot_room, laptop, sunlight")
    parser.add_argument("--scene_type", required=True, help="Scene category, e.g. bedroom or office")
    parser.add_argument("--notes", default="", help="Optional session notes")
    parser.add_argument("--output", type=Path, default=default_output())
    parser.add_argument("--interval", type=float, default=0.5, help="Seconds between captures")
    parser.add_argument("--address", type=lambda value: int(value, 0), default=0x33)
    parser.add_argument("--refresh-rate-hz", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    global RUNNING
    args = parse_args()
    if args.interval < 0:
        raise SystemExit("--interval must be non-negative")

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    session_id = uuid.uuid4().hex
    started = time.monotonic()
    valid_frames = 0
    dropped_frames = 0

    try:
        reader = Mlx90640Reader(args.address, args.refresh_rate_hz)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Capturing label={args.label!r}, scene_type={args.scene_type!r}")
    print(f"Appending frames to {args.output}")
    print("Press Ctrl+C to stop.")
    while RUNNING:
        try:
            frame = reader.read()
        except ValueError as exc:
            dropped_frames += 1
            if dropped_frames == 1 or dropped_frames % 10 == 0:
                print(f"Skipped dropped MLX90640 frame ({dropped_frames}): {exc}")
            time.sleep(min(max(args.interval, 0.02), 0.2))
            continue
        except (OSError, RuntimeError) as exc:
            dropped_frames += 1
            if dropped_frames == 1 or dropped_frames % 10 == 0:
                print(f"Skipped thermal read failure ({dropped_frames}): {exc}")
            time.sleep(min(max(args.interval, 0.02), 0.2))
            continue

        append_frame(
            args.output,
            frame,
            args.label,
            args.scene_type,
            args.notes,
            session_id,
            datetime.now(timezone.utc).isoformat(),
        )
        valid_frames += 1
        if valid_frames % 10 == 0:
            print(f"Captured {valid_frames} valid frames; dropped {dropped_frames}.")
        if args.interval:
            time.sleep(args.interval)

    elapsed = time.monotonic() - started
    print("Session stopped.")
    print(f"Duration: {elapsed:.1f} seconds")
    print(f"Valid frames: {valid_frames}")
    print(f"Dropped frames: {dropped_frames}")
    print(f"Label: {args.label}")
    print(f"Session ID: {session_id}")


if __name__ == "__main__":
    main()
