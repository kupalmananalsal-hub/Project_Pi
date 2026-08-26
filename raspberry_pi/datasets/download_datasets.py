#!/usr/bin/env python3
from __future__ import annotations

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
ROOT = Path(os.getenv("DATASET_DIR", str(PROJECT_ROOT / "dataset"))).expanduser()

DATASETS = {
    "ms-snsd": {
        "url": "https://github.com/microsoft/MS-SNSD.git",
        "type": "git",
        "path": ROOT / "audio" / "augmentation" / "synthetic_noise" / "MS-SNSD",
        "purpose": "Noise suppression training",
    },
    "fda_thermal": {
        "url": "https://cdrh-rst.fda.gov/dataset-infrared-facial-and-oral-temperatures-human-volunteers",
        "type": "manual",
        "path": ROOT / "thermal" / "raw" / "fda_thermal",
        "purpose": "Human skin temperature baseline",
        "notes": "Download the FDA dataset manually if the site requires form acceptance.",
    },
    "speech_commands": {
        "url": "http://download.tensorflow.org/data/speech_commands_v0.02.tar.gz",
        "type": "download",
        "path": ROOT / "audio" / "real_clips" / "en" / "speech_commands",
        "archive_name": "speech_commands_v0.02.tar.gz",
        "purpose": "Keyword spotting validation",
    },
    "esc50": {
        "url": "https://github.com/karolpiczak/ESC-50.git",
        "type": "git",
        "path": ROOT / "audio" / "augmentation" / "synthetic_noise" / "ESC-50",
        "purpose": "Environmental sound classification",
    },
    "demand": {
        "url": "https://zenodo.org/record/1227121/files/DEMAND.zip",
        "type": "download",
        "path": ROOT / "audio" / "augmentation" / "synthetic_noise" / "DEMAND",
        "archive_name": "DEMAND.zip",
        "purpose": "Noise augmentation",
    },
    "vpqad": {
        "url": "https://github.com/placeholder/VPQAD",
        "type": "manual",
        "path": ROOT / "audio" / "augmentation" / "vpqad",
        "purpose": "Real-world noisy environment recordings for robustness testing",
        "notes": "Provide the final VPQAD source URL in this script before download.",
    },
    "iphd": {
        "url": "https://github.com/placeholder/IPHD",
        "type": "manual",
        "path": ROOT / "thermal" / "raw" / "iphd",
        "purpose": "Thermal human detection with bounding boxes",
        "notes": "Provide the final IPHD source URL in this script before download.",
    },
    "pd_t": {
        "url": "https://github.com/placeholder/PD-T",
        "type": "manual",
        "path": ROOT / "thermal" / "raw" / "pd_t",
        "purpose": "Outdoor thermal person detection",
        "notes": "Provide the final PD-T source URL in this script before download.",
    },
}


def download_all() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    for name, dataset in DATASETS.items():
        print(f"\n==> {name}")
        dataset_path = Path(dataset["path"]).expanduser()
        dataset_path.parent.mkdir(parents=True, exist_ok=True)

        if dataset["type"] == "git":
            _clone_repo(dataset["url"], dataset_path)
            continue

        if dataset["type"] == "manual":
            dataset_path.mkdir(parents=True, exist_ok=True)
            _write_manual_note(name, dataset)
            print(f"Manual step required for {name}: {dataset['notes']}")
            continue

        archive_name = dataset.get("archive_name") or Path(urlparse(dataset["url"]).path).name
        archive_path = ROOT / "archives" / archive_name
        _download_file(dataset["url"], archive_path)
        _extract_archive(archive_path, dataset_path)


def verify_integrity() -> dict[str, dict[str, object]]:
    report: dict[str, dict[str, object]] = {}
    for name, dataset in DATASETS.items():
        dataset_path = Path(dataset["path"]).expanduser()
        exists = dataset_path.exists()
        file_count = 0
        total_bytes = 0
        if exists:
            for item in dataset_path.rglob("*"):
                if item.is_file():
                    file_count += 1
                    total_bytes += item.stat().st_size

        report[name] = {
            "exists": exists,
            "path": str(dataset_path),
            "purpose": dataset["purpose"],
            "type": dataset["type"],
            "file_count": file_count,
            "size_bytes": total_bytes,
        }
    return report


def generate_report() -> Path:
    report = {
        "root": str(ROOT),
        "datasets": verify_integrity(),
    }
    report_path = ROOT / "dataset_inventory.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote dataset inventory to {report_path}")
    return report_path


def _clone_repo(url: str, path: Path) -> None:
    if path.exists():
        print(f"Repository already present at {path}")
        return
    subprocess.run(["git", "clone", "--depth", "1", url, str(path)], check=True)


def _download_file(url: str, destination: Path) -> None:
    if destination.exists():
        print(f"Using existing archive {destination}")
        return

    request = Request(url, headers={"User-Agent": "ProjectPiDatasetDownloader/1.0"})
    with urlopen(request) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)
    print(f"Downloaded {destination.name}")


def _extract_archive(archive_path: Path, destination: Path) -> None:
    if destination.exists() and any(destination.iterdir()):
        print(f"Using existing extracted directory {destination}")
        return

    destination.mkdir(parents=True, exist_ok=True)
    dest_resolved = destination.resolve()

    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                member_path = (dest_resolved / member.filename).resolve()
                if member_path != dest_resolved and dest_resolved not in member_path.parents:
                    raise ValueError(
                        f"Unsafe path in ZIP archive: {member.filename!r}"
                    )
                if member.is_dir():
                    member_path.mkdir(parents=True, exist_ok=True)
                    continue
                member_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, member_path.open("wb") as target:
                    shutil.copyfileobj(source, target)
        return

    if archive_path.suffixes[-2:] == [".tar", ".gz"] or archive_path.suffix == ".tgz":
        with tarfile.open(archive_path, "r:gz") as archive:
            for member in archive.getmembers():
                member_path = (dest_resolved / member.name).resolve()
                if member_path != dest_resolved and dest_resolved not in member_path.parents:
                    raise ValueError(
                        f"Unsafe path in tar archive: {member.name!r}"
                    )
                if member.isdir():
                    member_path.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                member_path.parent.mkdir(parents=True, exist_ok=True)
                with extracted, member_path.open("wb") as target:
                    shutil.copyfileobj(extracted, target)
        return

    raise ValueError(f"Unsupported archive type: {archive_path}")


def _write_manual_note(name: str, dataset: dict[str, object]) -> None:
    dataset_path = Path(dataset["path"]).expanduser()
    note_path = dataset_path / "DOWNLOAD_REQUIRED.txt"
    note_path.write_text(
        "\n".join(
            [
                f"Dataset: {name}",
                f"Purpose: {dataset['purpose']}",
                f"Source: {dataset['url']}",
                f"Notes: {dataset.get('notes', 'Download manually and place files here.')}",
            ]
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    download_all()
    generate_report()
