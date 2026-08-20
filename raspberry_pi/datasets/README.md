# Thesis Dataset Pipeline

This folder contains helper scripts for downloading and preprocessing the
datasets used by the Raspberry Pi 5 emergency alert thesis project.

## Scripts

- `download_datasets.py`
  - clones Git-based datasets
  - downloads archive-based datasets
  - creates manual-download placeholders for sources that require form access
  - writes `dataset/dataset_inventory.json`
- `preprocess_thermal.py`
  - resamples thermal frames to the MLX90640 format (`32x24`)
  - extracts temperature statistics
  - generates JSONL training rows with coverage labels
- `preprocess_audio.py`
  - resamples audio to `16 kHz` mono WAV
  - creates noisy/clean speech pairs at multiple SNR levels
  - generates a keyword dataset manifest

## Default Dataset Root

```text
Project_Pi/dataset
```

## Example Usage

Download and inventory:

```bash
python3 raspberry_pi/datasets/download_datasets.py
```

Thermal preprocessing:

```bash
python3 raspberry_pi/datasets/preprocess_thermal.py
```

Audio preprocessing:

```bash
python3 raspberry_pi/datasets/preprocess_audio.py
```

## Notes

- Some public datasets use landing pages or access agreements instead of direct
  archive links. For those, `download_datasets.py` creates a
  `DOWNLOAD_REQUIRED.txt` file in the target folder.
- The preprocessing scripts are intentionally format-tolerant so they can be
  adapted once the final thesis dataset structure is fixed.
