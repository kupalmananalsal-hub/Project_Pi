#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(
    os.getenv("PROJECT_PI_ROOT", Path(__file__).resolve().parents[2])
).expanduser()
DATASET_DIR = Path(os.getenv("DATASET_DIR", str(PROJECT_ROOT / "dataset"))).expanduser()
ROOT = DATASET_DIR / "thermal"
RAW_ROOT = ROOT / "raw"

DATASETS: dict[str, dict[str, str]] = {
    "thermo_presence": {
        "type": "git",
        "url": "https://github.com/PUTvision/thermo-presence.git",
        "path": "raw/thermo_presence",
        "purpose": "MLX90640 32x24/24x32 frames with annotated person centers.",
    },
    "mldetection": {
        "type": "download",
        "url": "https://iiw.kuleuven.be/onderzoek/eavise/mldetection/dataset-tar.gz",
        "archive_name": "mldetection_dataset.tar.gz",
        "path": "raw/mldetection",
        "purpose": "MLX90640 32x24 frames with person bounding boxes.",
    },
    "skku_thermal_human": {
        "type": "git",
        "url": "https://github.com/InfoLab-SKKU/Thermal-Human-Detection.git",
        "path": "raw/skku_thermal_human",
        "purpose": "32x24 thermal human detection data and trained-model examples.",
    },
    "yolov8_thermal": {
        "type": "kaggle",
        "kaggle_dataset": "sikdermdsaiful/thermal-images-for-human-detection",
        "path": "raw/yolov8_thermal",
        "purpose": "Thermal/infrared human images with YOLO-format boxes.",
        "notes": "Requires Kaggle credentials in ~/.kaggle/kaggle.json.",
    },
}


def main() -> None:
    global ROOT, RAW_ROOT

    parser = argparse.ArgumentParser(description="Download Project Pi thermal datasets.")
    parser.add_argument(
        "--datasets",
        nargs="*",
        default=list(DATASETS),
        help="Dataset keys to download. Defaults to all configured datasets.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Dataset root. Defaults to Project_Pi/dataset/thermal.",
    )
    args = parser.parse_args()

    ROOT = args.root.expanduser()
    RAW_ROOT = ROOT / "raw"
    RAW_ROOT.mkdir(parents=True, exist_ok=True)

    selected = _selected_datasets(args.datasets)
    for name, dataset in selected.items():
        print(f"\n==> {name}")
        target = _dataset_path(dataset)
        target.parent.mkdir(parents=True, exist_ok=True)

        dataset_type = dataset["type"]
        if dataset_type == "git":
            _clone_repo(dataset["url"], target)
        elif dataset_type == "download":
            archive_name = dataset.get("archive_name") or Path(
                urlparse(dataset["url"]).path
            ).name
            archive_path = ROOT / "archives" / archive_name
            _download_file(dataset["url"], archive_path)
            _extract_archive(archive_path, target)
        elif dataset_type == "kaggle":
            _download_kaggle_dataset(dataset, target)
        else:
            raise ValueError(f"Unknown dataset type for {name}: {dataset_type}")

    _write_inventory(selected)


def _selected_datasets(keys: list[str]) -> dict[str, dict[str, str]]:
    unknown = sorted(set(keys) - set(DATASETS))
    if unknown:
        raise KeyError(f"Unknown datasets: {unknown}. Available: {sorted(DATASETS)}")
    return {key: dict(DATASETS[key]) for key in keys}


def _dataset_path(dataset: dict[str, str]) -> Path:
    relative = Path(dataset["path"])
    if relative.is_absolute():
        return relative
    return ROOT / relative


def _clone_repo(url: str, target: Path) -> None:
    if (target / ".git").exists():
        print(f"Repository already exists: {target}")
        return
    if target.exists() and any(target.iterdir()):
        print(f"Directory already exists and is not empty: {target}")
        return
    subprocess.run(["git", "clone", "--depth", "1", url, str(target)], check=True)


def _download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        print(f"Archive already exists: {destination}")
        return

    request = Request(url, headers={"User-Agent": "ProjectPiDatasetDownloader/1.0"})
    with urlopen(request) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)
    print(f"Downloaded {destination}")


def _extract_archive(archive_path: Path, destination: Path) -> None:
    if destination.exists() and any(destination.iterdir()):
        print(f"Extracted directory already exists: {destination}")
        return

    destination.mkdir(parents=True, exist_ok=True)
    suffixes = archive_path.suffixes
    if archive_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(destination)
        return

    if suffixes[-2:] == [".tar", ".gz"] or archive_path.suffix.lower() == ".tgz":
        with tarfile.open(archive_path, "r:gz") as archive:
            archive.extractall(destination)
        return

    raise ValueError(f"Unsupported archive type: {archive_path}")


def _download_kaggle_dataset(dataset: dict[str, str], target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        print(f"Kaggle dataset directory already contains files: {target}")
        return

    if shutil.which("kaggle") is None:
        _write_download_note(
            target,
            [
                "Install the Kaggle CLI first:",
                "  python -m pip install kaggle",
                "Then place kaggle.json at ~/.kaggle/kaggle.json.",
                "After that, rerun dataset_downloader.py.",
            ],
        )
        return

    subprocess.run(
        [
            "kaggle",
            "datasets",
            "download",
            "-d",
            dataset["kaggle_dataset"],
            "-p",
            str(target),
            "--unzip",
        ],
        check=True,
    )


def _write_download_note(target: Path, lines: list[str]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    note = target / "DOWNLOAD_REQUIRED.txt"
    note.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Manual download note written: {note}")


def _write_inventory(datasets: dict[str, dict[str, str]]) -> None:
    inventory = {
        "root": str(ROOT),
        "datasets": {
            name: {
                **dataset,
                "path": str(_dataset_path(dataset)),
                "exists": _dataset_path(dataset).exists(),
                "file_count": sum(
                    1 for path in _dataset_path(dataset).rglob("*") if path.is_file()
                )
                if _dataset_path(dataset).exists()
                else 0,
            }
            for name, dataset in datasets.items()
        },
    }
    output = ROOT / "dataset_inventory.json"
    output.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print(f"\nWrote inventory: {output}")


if __name__ == "__main__":
    main()
