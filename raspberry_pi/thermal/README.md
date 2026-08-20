# Thermal Human Detection Model Pipeline

This folder contains the Project Pi MLX90640 human-detection training and
deployment pipeline.

## Dataset Sources

The scripts expect the datasets under:

```text
dataset/thermal/raw/
```

Configured sources:

- `thermo_presence`: `https://github.com/PUTvision/thermo-presence`
- `mldetection`: `https://iiw.kuleuven.be/onderzoek/eavise/mldetection`
- `skku_thermal_human`: `https://github.com/InfoLab-SKKU/Thermal-Human-Detection`
- `yolov8_thermal`: Kaggle dataset
  `sikdermdsaiful/thermal-images-for-human-detection`

## Download

```bash
python3 raspberry_pi/thermal/dataset_downloader.py
```

Kaggle requires credentials:

```bash
python3 -m pip install kaggle
mkdir -p ~/.kaggle
# put kaggle.json in ~/.kaggle/kaggle.json
chmod 600 ~/.kaggle/kaggle.json
python3 raspberry_pi/thermal/dataset_downloader.py --datasets yolov8_thermal
```

## Preprocess

```bash
python3 -m pip install numpy pillow h5py
python3 raspberry_pi/thermal/preprocess_thermal_datasets.py --dataset all
```

Output:

```text
dataset/thermal/processed/thermal_human_detection.npz
```

The NPZ contains:

- `frames`: `(N, 24, 32)` float32 Celsius frames clipped to 0-80 C
- `masks`: `(N, 24, 32)` binary human masks
- `presence`: `(N,)` binary frame labels
- `coverage`: `(N,)` human mask coverage
- `sources`: source file references
- `source_ids`: source groups used to avoid train/test leakage
- `source_units`: `celsius`, `normalized_image`, or `unknown`
- `input_domains`: `celsius` or `image_domain`

You can preprocess one source at a time:

```bash
python3 raspberry_pi/thermal/preprocess_thermal_datasets.py --dataset thermo_presence
python3 raspberry_pi/thermal/preprocess_thermal_datasets.py --dataset mldetection
python3 raspberry_pi/thermal/preprocess_thermal_datasets.py --dataset skku
python3 raspberry_pi/thermal/preprocess_thermal_datasets.py --dataset yolo
```

## Record Pi-Side Training Frames

Use real MLX90640 frames from the deployment room to reduce false positives.
Record negative samples first: empty room, sun-warmed walls, laptops, chargers,
and other normal heat sources.

```bash
source ~/thermal-env-sys/bin/activate
python /home/thesis/Project_Pi/raspberry_pi/thermal/record_training_frames.py \
  --label negative \
  --duration 1800 \
  --interval 0.5 \
  --note empty_room_backgrounds
deactivate
```

Record positives with a person at different distances, angles, and postures:

```bash
source ~/thermal-env-sys/bin/activate
python /home/thesis/Project_Pi/raspberry_pi/thermal/record_training_frames.py \
  --label positive \
  --duration 600 \
  --interval 0.5 \
  --note person_near_far_angles
deactivate
```

Recorded frames are saved under:

```text
dataset/thermal/recorded/
```

Include them in preprocessing:

```bash
python3 raspberry_pi/thermal/preprocess_thermal_datasets.py --dataset recorded
```

## Train

Train on Colab or a stronger machine:

```bash
python3 -m pip install tensorflow numpy matplotlib
python3 raspberry_pi/thermal/train_thermal_model.py \
  --data dataset/thermal/processed/thermal_human_detection.npz \
  --epochs 40 \
  --batch-size 64 \
  --split-by source_id
```

The exported model is:

```text
dataset/thermal/models/thermal_human_detector.tflite
```

Training also writes:

```text
dataset/thermal/models/split.json
dataset/thermal/models/thermal_human_detector.metadata.json
dataset/thermal/models/thermal_human_detector_metrics.json
dataset/thermal/models/thermal_human_detector_pr_curve.png
```

Copy that file to the same path on the Raspberry Pi.

## Pi Runtime

Install TensorFlow Lite runtime in the backend environment:

```bash
source ~/thermal-env-sys/bin/activate
python -m pip install tflite-runtime
deactivate
```

Restart:

```bash
sudo systemctl restart thermal-backend.service
sudo journalctl -u thermal-backend.service -f
```

If the TFLite model or runtime is missing, `ThermalConfidenceScorer` falls back
to the existing rule-based heuristic.

Runtime environment variables:

```ini
Environment=DATASET_DIR=/home/thesis/Project_Pi/dataset
Environment=THERMAL_HUMAN_MODEL_PATH=/home/thesis/Project_Pi/dataset/thermal/models/thermal_human_detector.tflite
Environment=THERMAL_HUMAN_MODEL_METADATA_PATH=/home/thesis/Project_Pi/dataset/thermal/models/thermal_human_detector.metadata.json
Environment=THERMAL_HUMAN_MODEL_THRESHOLD=0.55
```

Use the threshold from `thermal_human_detector.metadata.json` after calibration.
