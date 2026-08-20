#!/usr/bin/env python3
"""Patch or diagnose Blinka lgpio chip selection for Raspberry Pi 5."""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence


RELATIVE_PATH = Path("adafruit_blinka/microcontroller/generic_linux/lgpio_pin.py")
DEFAULT_SYSFS_GPIO_ROOT = Path("/sys/bus/gpio/devices")
DEFAULT_DEV_ROOT = Path("/dev")
DEFAULT_FALLBACK_CHIPS = ()
RP1_LABEL = "pinctrl-rp1"
PATCH_BEGIN = "# PROJECT_PI_DYNAMIC_RP1_GPIO_PATCH_BEGIN"
PATCH_END = "# PROJECT_PI_DYNAMIC_RP1_GPIO_PATCH_END"
GPIOCHIP_RE = re.compile(r"^gpiochip(\d+)$")

StatFunc = Callable[[Path], object]


@dataclass(frozen=True)
class GPIOChipNode:
    chip: int
    path: Path
    major: int
    minor: int


@dataclass(frozen=True)
class GPIOChipInfo:
    sysfs_name: str
    label: str | None
    dev_major: int | None
    dev_minor: int | None
    dev_node: Path | None
    chip: int | None


@dataclass(frozen=True)
class GPIOChipCandidatePlan:
    candidates: list[int]
    override_chip: int | None
    discovered_rp1: int | None
    warnings: list[str]


def parse_gpiochip_number(name: str) -> int | None:
    match = GPIOCHIP_RE.match(name)
    if not match:
        return None
    return int(match.group(1), 10)


def parse_major_minor(value: str | None) -> tuple[int, int] | None:
    if value is None:
        return None
    match = re.match(r"^\s*(\d+):(\d+)\s*$", value)
    if not match:
        return None
    return int(match.group(1), 10), int(match.group(2), 10)


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def stat_major_minor(stat_result: object) -> tuple[int, int] | None:
    rdev = getattr(stat_result, "st_rdev", None)
    if isinstance(rdev, tuple) and len(rdev) == 2:
        return int(rdev[0]), int(rdev[1])
    try:
        return os.major(rdev), os.minor(rdev)  # type: ignore[arg-type, attr-defined]
    except (AttributeError, TypeError, ValueError):
        return None


def iter_gpiochip_nodes(
    dev_root: Path = DEFAULT_DEV_ROOT,
    *,
    stat_func: StatFunc = os.stat,
) -> list[GPIOChipNode]:
    nodes: list[GPIOChipNode] = []
    try:
        paths = sorted(Path(dev_root).glob("gpiochip*"))
    except OSError:
        return nodes

    for path in paths:
        chip = parse_gpiochip_number(path.name)
        if chip is None:
            continue
        try:
            result = stat_func(path)
        except OSError:
            continue
        dev_id = stat_major_minor(result)
        if dev_id is None:
            continue
        major, minor = dev_id
        nodes.append(GPIOChipNode(chip=chip, path=path, major=major, minor=minor))
    return nodes


def scan_sysfs_gpiochips(
    sysfs_root: Path = DEFAULT_SYSFS_GPIO_ROOT,
    dev_root: Path = DEFAULT_DEV_ROOT,
    *,
    stat_func: StatFunc = os.stat,
) -> list[GPIOChipInfo]:
    dev_nodes = {
        (node.major, node.minor): node
        for node in iter_gpiochip_nodes(dev_root, stat_func=stat_func)
    }
    try:
        sysfs_paths = sorted(Path(sysfs_root).glob("gpiochip*"))
    except OSError:
        return []

    chips: list[GPIOChipInfo] = []
    for sysfs_path in sysfs_paths:
        label = read_text(sysfs_path / "label")
        dev_id = parse_major_minor(read_text(sysfs_path / "dev"))
        dev_node = dev_nodes.get(dev_id) if dev_id is not None else None
        chips.append(
            GPIOChipInfo(
                sysfs_name=sysfs_path.name,
                label=label,
                dev_major=dev_id[0] if dev_id is not None else None,
                dev_minor=dev_id[1] if dev_id is not None else None,
                dev_node=dev_node.path if dev_node is not None else None,
                chip=dev_node.chip if dev_node is not None else None,
            )
        )
    return chips


def parse_gpiodetect_output(output: str) -> int | None:
    for line in output.splitlines():
        match = re.search(r"\b(gpiochip\d+)\s+\[([^\]]+)\]", line)
        if not match:
            continue
        if match.group(2).strip() == RP1_LABEL:
            return parse_gpiochip_number(match.group(1))
    return None


def discover_rp1_from_gpiodetect() -> int | None:
    if shutil.which("gpiodetect") is None:
        return None
    try:
        result = subprocess.run(
            ["gpiodetect"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_gpiodetect_output(result.stdout)


def discover_rp1_gpiochip(
    sysfs_root: Path = DEFAULT_SYSFS_GPIO_ROOT,
    dev_root: Path = DEFAULT_DEV_ROOT,
    *,
    stat_func: StatFunc = os.stat,
    use_gpiodetect: bool = True,
) -> int | None:
    for chip in scan_sysfs_gpiochips(sysfs_root, dev_root, stat_func=stat_func):
        if chip.label == RP1_LABEL and chip.chip is not None:
            return chip.chip

    if use_gpiodetect:
        return discover_rp1_from_gpiodetect()
    return None


def parse_override(value: str | None) -> tuple[int | None, str | None]:
    raw = (value or "").strip()
    if not raw:
        return None, None
    if not re.fullmatch(r"\d+", raw):
        return None, f"LGPIO_CHIP={raw!r} is not a non-negative integer; ignoring override"
    return int(raw, 10), None


def gpiochip_node_exists(chip: int, dev_root: Path = DEFAULT_DEV_ROOT) -> bool:
    return (Path(dev_root) / f"gpiochip{chip}").exists()


def unique_ints(values: Iterable[int]) -> list[int]:
    seen: set[int] = set()
    result: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def gpiochip_candidates(
    *,
    override_value: str | None = None,
    sysfs_root: Path = DEFAULT_SYSFS_GPIO_ROOT,
    dev_root: Path = DEFAULT_DEV_ROOT,
    fallback_chips: Sequence[int] = DEFAULT_FALLBACK_CHIPS,
    stat_func: StatFunc = os.stat,
    use_gpiodetect: bool = True,
) -> GPIOChipCandidatePlan:
    warnings: list[str] = []
    candidates: list[int] = []

    override_chip, override_warning = parse_override(override_value)
    if override_warning:
        warnings.append(override_warning)
    elif override_chip is not None:
        if gpiochip_node_exists(override_chip, dev_root):
            candidates.append(override_chip)
        else:
            warnings.append(
                f"LGPIO_CHIP={override_chip} does not exist at "
                f"{Path(dev_root) / f'gpiochip{override_chip}'}; falling back"
            )

    discovered_rp1 = discover_rp1_gpiochip(
        sysfs_root,
        dev_root,
        stat_func=stat_func,
        use_gpiodetect=use_gpiodetect,
    )
    if discovered_rp1 is not None:
        candidates.append(discovered_rp1)

    candidates.extend(fallback_chips)
    return GPIOChipCandidatePlan(
        candidates=unique_ints(candidates),
        override_chip=override_chip,
        discovered_rp1=discovered_rp1,
        warnings=warnings,
    )


def parse_chips(value: str) -> list[int]:
    chips: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            chip = int(item, 10)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"invalid chip id: {item!r}") from exc
        if chip < 0:
            raise argparse.ArgumentTypeError("chip ids must be non-negative")
        chips.append(chip)
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


def replacement_source(fallback_chips: Sequence[int] = DEFAULT_FALLBACK_CHIPS) -> str:
    chips_literal = repr(list(fallback_chips))
    return f"""{PATCH_BEGIN}
_PROJECT_PI_RP1_LABEL = "pinctrl-rp1"
_PROJECT_PI_FALLBACK_GPIOCHIPS = {chips_literal}


def _project_pi_parse_gpiochip_number(name):
    import re as _project_pi_re

    match = _project_pi_re.match(r"^gpiochip(\\d+)$", name)
    if not match:
        return None
    return int(match.group(1), 10)


def _project_pi_gpiochip_nodes():
    import os as _project_pi_os

    nodes = {{}}
    try:
        names = _project_pi_os.listdir("/dev")
    except OSError:
        return nodes
    for name in names:
        chip = _project_pi_parse_gpiochip_number(name)
        if chip is None:
            continue
        path = _project_pi_os.path.join("/dev", name)
        try:
            stat_result = _project_pi_os.stat(path)
            dev_id = (
                _project_pi_os.major(stat_result.st_rdev),
                _project_pi_os.minor(stat_result.st_rdev),
            )
        except (AttributeError, OSError, ValueError):
            continue
        nodes[dev_id] = chip
    return nodes


def _project_pi_discover_rp1_gpiochip_from_sysfs():
    import os as _project_pi_os
    import re as _project_pi_re

    root = "/sys/bus/gpio/devices"
    nodes = _project_pi_gpiochip_nodes()
    try:
        names = sorted(_project_pi_os.listdir(root))
    except OSError:
        return None
    for name in names:
        if _project_pi_parse_gpiochip_number(name) is None:
            continue
        base = _project_pi_os.path.join(root, name)
        try:
            with open(_project_pi_os.path.join(base, "label"), encoding="utf-8") as handle:
                label = handle.read().strip()
        except OSError:
            continue
        if label != _PROJECT_PI_RP1_LABEL:
            continue
        try:
            with open(_project_pi_os.path.join(base, "dev"), encoding="utf-8") as handle:
                dev_text = handle.read().strip()
        except OSError:
            continue
        match = _project_pi_re.match(r"^(\\d+):(\\d+)$", dev_text)
        if not match:
            continue
        chip = nodes.get((int(match.group(1), 10), int(match.group(2), 10)))
        if chip is not None:
            return chip
    return None


def _project_pi_discover_rp1_gpiochip_from_gpiodetect():
    import shutil as _project_pi_shutil
    import subprocess as _project_pi_subprocess
    import re as _project_pi_re

    if _project_pi_shutil.which("gpiodetect") is None:
        return None
    try:
        result = _project_pi_subprocess.run(
            ["gpiodetect"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, _project_pi_subprocess.SubprocessError):
        return None
    for line in result.stdout.splitlines():
        match = _project_pi_re.search(r"\\b(gpiochip\\d+)\\s+\\[([^\\]]+)\\]", line)
        if match and match.group(2).strip() == _PROJECT_PI_RP1_LABEL:
            return _project_pi_parse_gpiochip_number(match.group(1))
    return None


def _project_pi_gpiochip_candidates():
    import os as _project_pi_os

    candidates = []
    raw_override = _project_pi_os.environ.get("LGPIO_CHIP", "").strip()
    if raw_override:
        try:
            override = int(raw_override, 10)
            if override < 0:
                raise ValueError
        except ValueError:
            print(
                "Project Pi warning: LGPIO_CHIP={{!r}} is invalid; "
                "falling back to RP1 discovery".format(raw_override)
            )
        else:
            override_path = "/dev/gpiochip{{}}".format(override)
            if _project_pi_os.path.exists(override_path):
                candidates.append((override, "LGPIO_CHIP"))
            else:
                print(
                    "Project Pi warning: LGPIO_CHIP={{}} does not exist at {{}}; "
                    "falling back to RP1 discovery".format(override, override_path)
                )

    discovered = _project_pi_discover_rp1_gpiochip_from_sysfs()
    if discovered is None:
        discovered = _project_pi_discover_rp1_gpiochip_from_gpiodetect()
    if discovered is not None:
        candidates.append((discovered, "pinctrl-rp1"))

    candidates.extend((chip_id, "fallback") for chip_id in _PROJECT_PI_FALLBACK_GPIOCHIPS)
    unique = []
    seen = set()
    for chip_id, source in candidates:
        if chip_id in seen:
            continue
        seen.add(chip_id)
        unique.append((chip_id, source))
    return unique


def _get_gpiochip():
    last_error = None
    tried = []
    for chip_id, source in _project_pi_gpiochip_candidates():
        tried.append(chip_id)
        try:
            return lgpio.gpiochip_open(chip_id)
        except Exception as exc:
            last_error = exc
            if source == "LGPIO_CHIP":
                print(
                    "Project Pi warning: LGPIO_CHIP={{}} could not be opened: {{}}; "
                    "falling back".format(chip_id, exc)
                )
            continue
    raise RuntimeError("No accessible GPIO chip found; tried {{}}".format(tried)) from last_error
{PATCH_END}
"""


def known_buggy_final_character_parsing(text: str) -> bool:
    return "dev.name[-1]" in text or "name[-1]" in text


def patch_file(
    path: Path,
    fallback_chips: Sequence[int] = DEFAULT_FALLBACK_CHIPS,
) -> str:
    text = path.read_text(encoding="utf-8")
    replacement = replacement_source(fallback_chips)
    if replacement in text:
        return "already patched"

    marker_pattern = re.compile(
        rf"{re.escape(PATCH_BEGIN)}.*?{re.escape(PATCH_END)}\n?",
        re.DOTALL,
    )
    if PATCH_BEGIN in text and PATCH_END in text:
        patched, count = marker_pattern.subn(lambda _match: replacement, text, count=1)
    else:
        function_pattern = re.compile(
            r"^def _get_gpiochip\(\):\n(?:(?:    .*\n)|(?:\s*\n))*",
            re.MULTILINE,
        )
        patched, count = function_pattern.subn(lambda _match: replacement, text, count=1)

    if count != 1:
        raise RuntimeError(f"Could not find _get_gpiochip() in {path}")

    backup = path.with_suffix(path.suffix + ".project-pi.bak")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")
    path.write_text(patched, encoding="utf-8")
    return "patched"


def print_diagnostics(
    *,
    fallback_chips: Sequence[int] = DEFAULT_FALLBACK_CHIPS,
    sysfs_root: Path = DEFAULT_SYSFS_GPIO_ROOT,
    dev_root: Path = DEFAULT_DEV_ROOT,
) -> None:
    print("Detected GPIO device nodes:")
    nodes = iter_gpiochip_nodes(dev_root)
    if nodes:
        for node in nodes:
            print(f"{node.path.name}: major={node.major} minor={node.minor}")
    else:
        print("(none found)")

    print()
    print("GPIO labels found:")
    chips = scan_sysfs_gpiochips(sysfs_root, dev_root)
    if chips:
        for chip in chips:
            name = chip.dev_node.name if chip.dev_node is not None else chip.sysfs_name
            label = chip.label or "(label unavailable)"
            print(f"{name}: {label}")
    else:
        print("(none found)")

    discovered = discover_rp1_gpiochip(sysfs_root, dev_root)
    print()
    print("RP1 GPIO controller:")
    print(f"gpiochip{discovered}" if discovered is not None else "(not discovered)")

    override_value = os.environ.get("LGPIO_CHIP")
    print()
    print("Explicit override:")
    print(f"LGPIO_CHIP={override_value}" if override_value else "(none)")

    plan = gpiochip_candidates(
        override_value=override_value,
        sysfs_root=sysfs_root,
        dev_root=dev_root,
        fallback_chips=fallback_chips,
    )
    for warning in plan.warnings:
        print(f"warning: {warning}")
    print()
    print("Selected chip candidate:")
    print(plan.candidates[0] if plan.candidates else "(none)")
    print(f"Candidate order: {plan.candidates}")

    print()
    print("Blinka lgpio_pin.py candidates:")
    paths = candidate_paths()
    if not paths:
        print(f"(not found under Python prefix {sys.prefix})")
        return
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"{path}: unreadable ({exc})")
            continue
        if PATCH_BEGIN in text and PATCH_END in text:
            state = "Project Pi dynamic patch detected"
        elif known_buggy_final_character_parsing(text):
            state = "known buggy final-character parsing detected"
        else:
            state = "no known Project Pi patch marker or final-character bug detected"
        print(f"{path}: {state}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chips",
        type=parse_chips,
        default=list(DEFAULT_FALLBACK_CHIPS),
        help=(
            "Comma-separated fallback lgpio chip ids to try after LGPIO_CHIP "
            "and dynamic RP1 discovery. No fallback chips are tried unless --chips is supplied."
        ),
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Print GPIO/Blinka diagnostics without modifying installed packages.",
    )
    parser.add_argument(
        "--path",
        action="append",
        type=Path,
        help="Patch this lgpio_pin.py path instead of auto-discovering site-packages.",
    )
    args = parser.parse_args()

    if args.diagnose:
        print_diagnostics(fallback_chips=args.chips)
        return 0

    paths = args.path if args.path else candidate_paths()
    if not paths:
        print(f"Blinka lgpio_pin.py not found under Python prefix {sys.prefix}")
        return 0

    for path in paths:
        state = patch_file(path, args.chips)
        print(f"{path}: {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
