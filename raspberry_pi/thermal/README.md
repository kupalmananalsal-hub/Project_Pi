# Thermal Human Detection Model Pipeline

This folder contains the Project Pi MLX90640 human-detection training and
deployment pipeline.

## Dataset Sources

The scripts expect the datasets under:

```text
~/thesis_dataset/thermal/raw/
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
python3 raspberry_pi/thermal/preprocess_thermal_datasets.py
```

Output:

```text
~/thesis_dataset/thermal/processed/thermal_human_detection.npz
```

The NPZ contains:

- `frames`: `(N, 24, 32)` float32 Celsius frames clipped to 0-80 C
- `masks`: `(N, 24, 32)` binary human masks
- `presence`: `(N,)` binary frame labels
- `coverage`: `(N,)` human mask coverage
- `sources`: source file references

## Train

Train on Colab or a stronger machine:

```bash
python3 -m pip install tensorflow numpy scikit-learn
python3 raspberry_pi/thermal/train_thermal_model.py \
  --data ~/thesis_dataset/thermal/processed/thermal_human_detection.npz \
  --epochs 40 \
  --batch-size 64
```

The exported model is:

```text
raspberry_pi/thermal/models/thermal_human_detector.tflite
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
Environment=THERMAL_HUMAN_MODEL_PATH=/home/thesis/Project_Pi/raspberry_pi/thermal/models/thermal_human_detector.tflite
Environment=THERMAL_HUMAN_MODEL_THRESHOLD=0.55
```
