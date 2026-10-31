#!/usr/bin/env python3
"""Interactive recorder for the Project Pi openWakeWord keyword dataset."""

from __future__ import annotations

import argparse
import sys
import wave
import re
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from keyword_dataset_common import (  # noqa: E402
    DEFAULT_DATASET_DIR,
    KEYWORDS,
    KEYWORD_LANGUAGES,
    metadata_file_lock,
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


def record_wav(path: Path, seconds: float, device: str | int | None = None) -> dict:
    sd = _require_sounddevice()
    actual_device = device if device is not None else sd.default.device[0]
    if isinstance(actual_device, str) and actual_device.isdigit():
        actual_device = int(actual_device)
    capture = dict(sd.query_devices(actual_device, "input"))
    frames = int(SAMPLE_RATE * seconds)
    recording = sd.rec(
        frames,
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        device=actual_device,
    )
    sd.wait()
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(CHANNELS)
        handle.setsampwidth(SAMPLE_WIDTH_BYTES)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(recording.tobytes())
    return {
        "name": capture["name"],
        "max_input_channels": capture["max_input_channels"],
        "selected_device": str(actual_device),
    }


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
    index = (
        max(
            [
                int(p.stem.rsplit("_", 1)[1])
                for p in existing
                if p.stem.rsplit("_", 1)[1].isdigit()
            ],
            default=0,
        )
        + 1
    )
    return keyword_dir / f"{slug}_{speaker_id}_{source}_{index:03d}.wav"


def collect_session(args: argparse.Namespace) -> None:
    dataset_dir = args.dataset_dir.resolve()
    ensure_dataset_layout(dataset_dir)
    metadata_path = dataset_dir / "metadata.csv"

    from recording_provenance import recording_evidence
    from import_keyword_datasets import file_digest, write_provenance

    for field in ("speaker_id", "session_id"):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", getattr(args, field)):
            raise ValueError(field + " must be a stable anonymous ID")
    if (
        not args.consent_reference.strip()
        or not args.recording_device_description.strip()
    ):
        raise ValueError("Consent reference and actual device description are required")
    keywords = KEYWORDS if args.keyword == "all" else [args.keyword]
    for keyword in keywords:
        print(f"\nKeyword: {keyword}")
        for sample_index in range(1, args.samples + 1):
            # Lock name allocation and commit together; never overwrite existing WAVs.
            with metadata_file_lock(metadata_path):
                output_path = next_sample_path(dataset_dir, keyword, args.speaker_id)
                input(
                    f"Press Enter, then say '{keyword}' ({sample_index}/{args.samples})..."
                )
                capture = record_wav(output_path, args.seconds, device=args.device)
                rel_path = output_path.relative_to(dataset_dir).as_posix()
                row = {
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
                }
                print(f"Saved {output_path}. Capture input: {capture['name']}")
                reviewed = (
                    input(
                        "Listen to the saved WAV and check the phrase, language and stated capture device. Type VERIFIED only after checking; Enter leaves it pending: "
                    )
                    == "VERIFIED"
                )
                evidence = recording_evidence(
                    dataset_dir,
                    row,
                    {
                        "expected_sha256": file_digest(output_path),
                        "language": KEYWORD_LANGUAGES[keyword],
                        "session_id": args.session_id,
                        "recording_device": args.recording_device_description,
                        "capture_device": capture,
                        "capture_origin": "pi_recorder",
                        "device_verified": reviewed,
                        "audio_reviewed": reviewed,
                        "reviewer_id": args.reviewer_id or "unknown",
                        "consent_reference": args.consent_reference,
                        "consent_confirmed": True,
                    },
                )
                write_provenance(dataset_dir, rel_path, evidence)
                append_metadata(metadata_path, row)
                print(f"Saved {rel_path}: {evidence['validation_state']}")


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
        "--session-id", default="unknown", help="Stable anonymous collection-session ID"
    )
    parser.add_argument(
        "--recording-device-description",
        default="unknown",
        help="Actual device/model verified against the capture input",
    )
    parser.add_argument(
        "--consent-reference",
        default="",
        help="Anonymous collection consent/authorization record; do not include names",
    )
    parser.add_argument(
        "--reviewer-id",
        default="",
        help="Anonymous reviewer ID for post-recording listening review",
    )
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
