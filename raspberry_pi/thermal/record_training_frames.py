#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


DEFAULT_OUTPUT_ROOT = Path.home() / "thesis_dataset" / "thermal" / "recorded"
RUNNING = True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record MLX90640 frames for thermal human detector training."
    )
    parser.add_argument(
        "--label",
        choices=("positive", "negative"),
        required=True,
        help="positive for human-present frames, negative for empty-room/background frames.",
    )
    parser.add_argument("--duration", type=float, default=300.0)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--address", default="0x10")
    parser.add_argument("--refresh-rate-hz", type=int, default=4)
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    output_dir = make_session_dir(args)
    camera = Mlx90640Reader(address=int(str(args.address), 16), refresh_rate_hz=args.refresh_rate_hz)

    metadata = {
        "label": args.label,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": args.duration,
        "interval_seconds": args.interval,
        "address": args.address,
        "refresh_rate_hz": args.refresh_rate_hz,
        "note": args.note,
        "frames": [],
    }

    start = time.monotonic()
    index = 0
    print(f"Recording {args.label} frames to {output_dir}")
    print("Press Ctrl+C to stop early.")
    while RUNNING and (time.monotonic() - start) < args.duration:
        frame = camera.read()
        timestamp = datetime.now(timezone.utc).isoformat()
        frame_path = output_dir / f"frame_{index:06d}.npy"
        np.save(frame_path, frame.astype(np.float32))
        metadata["frames"].append(
            {
                "file": frame_path.name,
                "timestamp": timestamp,
                "min_c": round(float(np.min(frame)), 2),
                "max_c": round(float(np.max(frame)), 2),
                "mean_c": round(float(np.mean(frame)), 2),
            }
        )
        index += 1
        time.sleep(args.interval)

    metadata["stopped_at"] = datetime.now(timezone.utc).isoformat()
    metadata["frame_count"] = len(metadata["frames"])
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )
    print(f"Recorded {metadata['frame_count']} frames.")
    print(f"Metadata: {output_dir / 'metadata.json'}")


def stop(signum, frame) -> None:
    del signum, frame
    global RUNNING
    RUNNING = False


def make_session_dir(args: argparse.Namespace) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_note = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in args.note.strip().lower()
    ).strip("_")
    name = f"{stamp}_{safe_note}" if safe_note else stamp
    output_dir = args.output_root.expanduser() / args.label / name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


class Mlx90640Reader:
    def __init__(self, *, address: int, refresh_rate_hz: int) -> None:
        try:
            import adafruit_mlx90640
            import board
            import busio
        except Exception as exc:  # pragma: no cover - Pi hardware path
            raise RuntimeError(
                "Install adafruit-blinka and adafruit-circuitpython-mlx90640 "
                "inside ~/thermal-env-sys first."
            ) from exc

        i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
        self.mlx = adafruit_mlx90640.MLX90640(i2c, address=address)
        refresh_name = f"REFRESH_{refresh_rate_hz}_HZ"
        self.mlx.refresh_rate = getattr(
            adafruit_mlx90640.RefreshRate,
            refresh_name,
            adafruit_mlx90640.RefreshRate.REFRESH_4_HZ,
        )
        self.buffer = [0.0] * 768

    def read(self) -> np.ndarray:
        while RUNNING:
            try:
                self.mlx.getFrame(self.buffer)
                return np.asarray(self.buffer, dtype=np.float32).reshape(24, 32)
            except ValueError:
                time.sleep(0.02)
        return np.asarray(self.buffer, dtype=np.float32).reshape(24, 32)


if __name__ == "__main__":
    main()
