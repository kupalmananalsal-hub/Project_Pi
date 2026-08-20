# Project Pi Dataset Layout

All local training data and deployable model artifacts live under this `dataset/`
folder. Runtime services should use these paths through environment variables or
`raspberry_pi/config/dataset_paths.yaml` instead of hardcoded legacy locations.

## Thermal

- `thermal/raw/` - downloaded third-party thermal datasets.
- `thermal/recorded/` - MLX90640 frames recorded from the Raspberry Pi.
- `thermal/processed/` - generated NPZ/JSONL training datasets and reports.
- `thermal/models/` - deployable thermal detector artifacts.

The backend service uses:

```text
DATASET_DIR=/home/thesis/Project_Pi/dataset
THERMAL_HUMAN_MODEL_PATH=/home/thesis/Project_Pi/dataset/thermal/models/thermal_human_detector.tflite
THERMAL_HUMAN_MODEL_METADATA_PATH=/home/thesis/Project_Pi/dataset/thermal/models/thermal_human_detector.metadata.json
```

## Audio

- `audio/real_clips/` - real recorded keyword and non-keyword clips.
- `audio/tts_clips/` - generated text-to-speech keyword clips.
- `audio/augmentation/` - RIRs, background audio, music, and synthetic noise.
- `audio/processed/` - generated manifests and processed audio.
- `audio/openwakeword_models/` - deployable openWakeWord `.onnx` and
  `.onnx.data` model pairs.

The KWS service uses:

```text
DATASET_DIR=/home/thesis/Project_Pi/dataset
OPENWAKEWORD_MODEL_DIR=/home/thesis/Project_Pi/dataset/audio/openwakeword_models
```

## Git Tracking Policy

Raw downloaded datasets, recordings, generated clips, augmentation corpora, and
processed training outputs are ignored by Git. Runtime model artifacts under
`thermal/models/` and `audio/openwakeword_models/` are tracked because the Pi
needs them after `git pull`.

The legacy runtime paths are kept as compatibility symlinks on Linux:

```text
raspberry_pi/thermal/models -> ../../dataset/thermal/models
raspberry_pi/kws/openwakeword_models -> ../../dataset/audio/openwakeword_models
```
