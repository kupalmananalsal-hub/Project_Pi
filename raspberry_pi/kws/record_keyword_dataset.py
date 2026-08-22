#!/usr/bin/env python3
"""Interactive recorder for the Project Pi openWakeWord keyword dataset."""

from __future__ import annotations

import argparse
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from keyword_dataset_common import (  # noqa: E402
    DEFAULT_DATASET_DIR,
    KEYWORDS,
    append_metadata,
    ensure_dataset_layout,
    slugify_keyword,
)

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH_BYTES = 2


def _require_sounddevice():
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise SystemExit(
            "Recording requires the optional 'sounddevice' package. "
            "Install it on the Pi with: ~/kws-env/bin/pip install sounddevice"
        ) from exc
    return sd


def record_wav(path: Path, seconds: float, device: str | int | None = None) -> None:
    sd = _require_sounddevice()
    frames = int(SAMPLE_RATE * seconds)
    recording = sd.rec(
        frames,
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        device=device,
    )
    sd.wait()
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(CHANNELS)
        handle.setsampwidth(SAMPLE_WIDTH_BYTES)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(recording.tobytes())


def next_sample_path(
    dataset_dir: Path,
    keyword: str,
    speaker_id: str,
    source: str = "real",
) -> Path:
    slug = slugify_keyword(keyword)
    keyword_dir = dataset_dir / "positive" / slug
    keyword_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(keyword_dir.glob(f"{slug}_{speaker_id}_{source}_*.wav"))
    index = len(existing) + 1
    return keyword_dir / f"{slug}_{speaker_id}_{source}_{index:03d}.wav"


def collect_session(args: argparse.Namespace) -> None:
    dataset_dir = args.dataset_dir.resolve()
    ensure_dataset_layout(dataset_dir)
    metadata_path = dataset_dir / "metadata.csv"

    keywords = KEYWORDS if args.keyword == "all" else [args.keyword]
    for keyword in keywords:
        print(f"\nKeyword: {keyword}")
        for sample_index in range(1, args.samples + 1):
            output_path = next_sample_path(dataset_dir, keyword, args.speaker_id)
            input(
                f"Press Enter, then say '{keyword}' "
                f"({sample_index}/{args.samples}, {args.seconds:.1f}s)..."
            )
            record_wav(output_path, args.seconds, device=args.device)
            rel_path = output_path.relative_to(dataset_dir).as_posix()
            append_metadata(
                metadata_path,
                {
                    "path": rel_path,
                    "keyword": keyword,
                    "label": keyword,
                    "speaker_id": args.speaker_id,
                    "age_group": args.age_group,
                    "gender": args.gender,
                    "distance_m": args.distance_m,
                    "noise_condition": args.noise_condition,
                    "source": "real",
                    "sample_rate": SAMPLE_RATE,
                    "duration_s": f"{args.seconds:.2f}",
                    "notes": args.notes,
                },
            )
            print(f"Saved {rel_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record real human speech samples for Project Pi keywords."
    )
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--speaker-id", required=True, help="Stable anonymous ID.")
    parser.add_argument("--age-group", required=True, help="child/teen/adult/elder")
    parser.add_argument("--gender", required=True, help="self-described gender label")
    parser.add_argument("--distance-m", required=True, help="microphone distance")
    parser.add_argument(
        "--noise-condition",
        required=True,
        help="quiet/noisy/fan/street/tv/etc.",
    )
    parser.add_argument("--keyword", default="all", choices=["all", *KEYWORDS])
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--seconds", type=float, default=3.5)
    parser.add_argument("--device", help="sounddevice input device id/name")
    parser.add_argument("--notes", default="")
    parser.add_argument(
        "--init-only",
        action="store_true",
        help="create folders and metadata.csv without recording audio",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 1.0")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.seconds < 1 or args.seconds > 5:
        raise SystemExit("--seconds must be between 1 and 5")
    ensure_dataset_layout(args.dataset_dir.resolve())
    if args.init_only:
        print(f"Initialized dataset at {args.dataset_dir.resolve()}")
        return 0
    print(f"Session started {datetime.now(timezone.utc).isoformat()}")
    collect_session(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
