#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(
    os.getenv("PROJECT_PI_ROOT", Path(__file__).resolve().parents[2])
).expanduser()
DATASET_DIR = Path(os.getenv("DATASET_DIR", str(PROJECT_ROOT / "dataset"))).expanduser()
DEFAULT_OUTPUT_ROOT = DATASET_DIR / "thermal" / "recorded"
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
    parser.add_argument(
        "--address",
        default="0x33",
        help="MLX90640 I2C address. Default: 0x33.",
    )
    parser.add_argument("--refresh-rate-hz", type=int, default=4)
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    output_dir = make_session_dir(args)
    camera = Mlx90640Reader(address=int(str(args.address), 16), refresh_rate_hz=args.refresh_rate_hz)
    print(f"Initialised MLX90640 at address {format_i2c_address(camera.address)}.")
    print("Waiting 1.0s for the I2C bus and camera to stabilise...")
    time.sleep(1.0)
    warm_up_camera(camera)

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
    read_error = None
    while RUNNING and (time.monotonic() - start) < args.duration:
        try:
            frame = camera.read()
        except RuntimeError as exc:
            read_error = exc
            print(f"Camera read failed during recording: {exc}")
            print_camera_troubleshooting(camera.address)
            break
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
    if read_error is not None:
        raise SystemExit(1)


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


def format_i2c_address(address: int) -> str:
    return f"0x{address:02x}"


def warm_up_camera(camera: "Mlx90640Reader", attempts: int = 5) -> None:
    failures = 0
    print(f"Warming up camera with {attempts} frame reads...")
    for attempt in range(1, attempts + 1):
        try:
            camera.read()
            print(f"Warm-up frame {attempt}/{attempts} OK.")
        except RuntimeError as exc:
            failures += 1
            print(f"Warm-up frame {attempt}/{attempts} failed: {exc}")
            time.sleep(0.2)

    if failures == attempts:
        print("Camera not responding. Check I2C connection and power.")
        print_camera_troubleshooting(camera.address)
        raise SystemExit(1)


def print_camera_troubleshooting(address: int) -> None:
    address_text = format_i2c_address(address)
    print(f"Expected MLX90640 address: {address_text}")
    print("Run `i2cdetect -y 1` and verify the camera appears at that address.")
    print("Troubleshooting:")
    print("- Check that the Grove connector is firmly seated on the ReSpeaker HAT.")
    print("- Check that the jumper wires are securely connected to the camera.")
    print("- Try powering the ReSpeaker HAT with an external Micro USB cable.")
    print(f"- Run `i2cdetect -y 1` to verify the camera is detected at address {address_text}.")


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

        self.address = address
        i2c = busio.I2C(board.SCL, board.SDA, frequency=400000)
        self.mlx = adafruit_mlx90640.MLX90640(i2c, address=address)
        refresh_name = f"REFRESH_{refresh_rate_hz}_HZ"
        self.mlx.refresh_rate = getattr(
            adafruit_mlx90640.RefreshRate,
            refresh_name,
            adafruit_mlx90640.RefreshRate.REFRESH_4_HZ,
        )
        self.buffer = [0.0] * 768

    def read(self, max_consecutive_failures: int = 100) -> np.ndarray:
        failures = 0
        while RUNNING:
            try:
                self.mlx.getFrame(self.buffer)
                return np.asarray(self.buffer, dtype=np.float32).reshape(24, 32)
            except (ValueError, RuntimeError, OSError) as exc:
                failures += 1
                if failures % 10 == 0:
                    print(
                        "Warning: MLX90640 read failed "
                        f"{failures}/{max_consecutive_failures} consecutive times: {exc}"
                    )
                if failures >= max_consecutive_failures:
                    raise RuntimeError(
                        "MLX90640 did not return a frame after "
                        f"{failures} consecutive read failures."
                    ) from exc
                time.sleep(0.02)
        return np.asarray(self.buffer, dtype=np.float32).reshape(24, 32)


if __name__ == "__main__":
    main()
