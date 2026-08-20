#!/usr/bin/env python3
"""Patch Adafruit Blinka's lgpio chip selection for Raspberry Pi 5."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


RELATIVE_PATH = Path("adafruit_blinka/microcontroller/generic_linux/lgpio_pin.py")


def parse_chips(value: str) -> list[int]:
    chips: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        chips.append(int(item, 10))
    if not chips:
        raise argparse.ArgumentTypeError("at least one chip id is required")
    return chips


def candidate_paths() -> list[Path]:
    candidates: list[Path] = []
    for entry in [*sys.path, str(Path(sys.prefix) / "lib")]:
        if not entry:
            continue
        base = Path(entry)
        direct = base / RELATIVE_PATH
        if direct.exists():
            candidates.append(direct)
        for site_dir in base.glob("python*/site-packages"):
            nested = site_dir / RELATIVE_PATH
            if nested.exists():
                candidates.append(nested)
    return sorted(set(candidates))


def replacement_source(chips: list[int]) -> str:
    chips_literal = repr(chips)
    return (
        "def _get_gpiochip():\n"
        "    last_error = None\n"
        f"    for chip_id in {chips_literal}:\n"
        "        try:\n"
        "            return lgpio.gpiochip_open(chip_id)\n"
        "        except Exception as exc:\n"
        "            last_error = exc\n"
        "            continue\n"
        f"    raise RuntimeError(\"No accessible GPIO chip found in {chips_literal}\") from last_error\n"
    )


def patch_file(path: Path, chips: list[int]) -> bool:
    text = path.read_text(encoding="utf-8")
    replacement = replacement_source(chips)
    pattern = re.compile(r"^def _get_gpiochip\(\):\n(?:(?:    .*\n)|(?:\s*\n))*", re.MULTILINE)

    if replacement in text:
        return False

    patched, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"Could not find _get_gpiochip() in {path}")

    backup = path.with_suffix(path.suffix + ".project-pi.bak")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
    path.write_text(patched, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chips",
        type=parse_chips,
        default=[11, 4, 0],
        help="Comma-separated lgpio chip ids to try, in order.",
    )
    args = parser.parse_args()

    paths = candidate_paths()
    if not paths:
        print(f"Blinka lgpio_pin.py not found under Python prefix {sys.prefix}")
        return 0

    for path in paths:
        changed = patch_file(path, args.chips)
        state = "patched" if changed else "already patched"
        print(f"{path}: {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
