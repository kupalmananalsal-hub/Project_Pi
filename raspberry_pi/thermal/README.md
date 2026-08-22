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

# Temperature-based model (original)
Environment=THERMAL_HUMAN_MODEL_PATH=/home/thesis/Project_Pi/dataset/thermal/models/thermal_human_shape.tflite
Environment=THERMAL_HUMAN_MODEL_METADATA_PATH=/home/thesis/Project_Pi/dataset/thermal/models/thermal_human_shape_labels.json
Environment=THERMAL_HUMAN_MODEL_THRESHOLD=0.65

# Shape-aware model (new) — optional, auto-detected at default path
Environment=THERMAL_HUMAN_SHAPE_MODEL_PATH=/home/thesis/Project_Pi/dataset/thermal/models/thermal_human_shape.tflite
Environment=THERMAL_HUMAN_SHAPE_LABELS_PATH=/home/thesis/Project_Pi/dataset/thermal/models/thermal_human_shape_labels.json
Environment=THERMAL_HUMAN_SHAPE_THRESHOLD=0.65
```

## Shape-Aware Model

The notebook `notebooks/train_thermal_shape_model.ipynb` trains a lightweight
9-class CNN (`thermal_human_shape.tflite`) that classifies each 32×24 frame as:

| Index | Class | Meaning |
|------:|:------|:--------|
| 0 | `human_full` | Full body visible |
| 1 | `human_partial` | Partial body visible |
| 2 | `human_head` | Head only |
| 3 | `human_torso` | Torso region |
| 4 | `human_hands` | Hands only |
| 5 | `human_feet` | Feet only |
| 6 | `hot_object` | Laptop, cup, heater, etc. |
| 7 | `background` | Warm wall, sun-heated surface |
| 8 | `ambiguous` | Inconclusive |

### False-Positive Suppression Rules

| Shape prediction | Confidence ≥ threshold | Action |
|:-----------------|:----------------------|:-------|
| `hot_object` | ✅ | Force `human_detected = False` |
| `background` | ✅ | Force `human_detected = False` |
| human class (0–5) | ✅ | Boost `confidence_boost`; confirm `human_detected` |
| `ambiguous` | any | Ignore shape; defer to temperature model |
| *(model absent)* | — | Graceful fallback to heuristic only |

### New Payload Fields

These are added to the `/ws/thermal` WebSocket payload alongside the
existing fields (`human_detected`, `body_coverage`, `detected_part`, etc.):

| Field | Type | Description |
|:------|:-----|:------------|
| `thermal_shape_human` | bool | Shape model says human present |
| `thermal_shape_body_part` | str | `full`/`partial`/`head`/`torso`/`hands`/`feet`/`none` |
| `thermal_shape_hot_object` | bool | Confidently identified as hot object |
| `thermal_shape_background` | bool | Confidently identified as background heat |
| `thermal_shape_confidence` | float | Winning class probability (0–1) |
| `thermal_shape_label` | str | Raw class name |
| `thermal_shape_available` | bool | Shape model loaded successfully |
| `thermal_shape_error` | str\|null | Load error message if unavailable |

### Deploy Shape Model Files

Copy the Colab-exported files to the Pi:

```bash
scp thermal_human_shape.tflite thesis@<pi-ip>:~/
scp thermal_human_shape_labels.json thesis@<pi-ip>:~/
ssh thesis@<pi-ip>
mkdir -p ~/Project_Pi/dataset/thermal/models/
mv ~/thermal_human_shape.tflite ~/Project_Pi/dataset/thermal/models/
mv ~/thermal_human_shape_labels.json ~/Project_Pi/dataset/thermal/models/
sudo systemctl daemon-reload
sudo systemctl restart thermal-backend.service
```
