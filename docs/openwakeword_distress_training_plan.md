# openWakeWord Distress Phrase Training Plan

This plan uses `notebooks/Copy_of_automatic_model_training.ipynb`.
The notebook pipeline is:

1. Install `piper-sample-generator`, openWakeWord, PyTorch, TensorFlow export
   dependencies, and the shared openWakeWord feature models.
2. Download augmentation data: MIT room impulse responses, AudioSet clips, FMA
   music clips, ACAV100M precomputed openWakeWord training features, and the
   false-positive validation feature set.
3. Load `openwakeword/examples/custom_model.yml`, change the phrase-specific
   YAML values, and write `my_model.yaml`.
4. Run `train.py` in three stages: `--generate_clips`, `--augment_clips`, and
   `--train_model`. The trained `.onnx` and `.tflite` files are written under
   `my_custom_model/<model_name>.onnx` and `my_custom_model/<model_name>.tflite`.

## Important Design Choice

For maximum accuracy and easier tuning, train one model per distress phrase.
openWakeWord also supports multiple phrases in one `target_phrase` list, but
that trains one broad binary detector. Use broad grouped models only after the
individual phrase models are measured on the Raspberry Pi.

The system cannot literally detect every unseen distress sentence through
openWakeWord alone. "Any distress keyword" means a maintained vocabulary of
trained distress phrases, plus optional Vosk/STT phrase matching for phrases
not covered by a wake-word model.

## High-Accuracy Common YAML Overrides

Use these values for every phrase unless Colab runtime limits force a smaller
run:

```python
COMMON_OVERRIDES = {
    "n_samples": 50000,
    "n_samples_val": 5000,
    "steps": 50000,
    "target_accuracy": 0.80,
    "target_recall": 0.60,
    "target_false_positives_per_hour": 0.05,
    "max_negative_weight": 2500,
    "augmentation_rounds": 2,
    "background_paths": ["./audioset_16k", "./fma"],
    "background_paths_duplication_rate": [2, 1],
    "rir_paths": ["./mit_rirs"],
    "false_positive_validation_data_path": "validation_set_features.npy",
    "feature_data_files": {
        "ACAV100M_sample": "openwakeword_features_ACAV100M_2000_hrs_16bit.npy",
    },
}
```

If training time is too high, use the minimum serious pass:

```python
COMMON_OVERRIDES.update({
    "n_samples": 20000,
    "n_samples_val": 3000,
    "steps": 30000,
    "augmentation_rounds": 1,
    "target_false_positives_per_hour": 0.10,
    "max_negative_weight": 1500,
})
```

## Phrase Model Matrix

Use these exact `target_phrase` and `model_name` values.

| Priority | target_phrase | model_name |
|:---|:---|:---|
| Core | `["tulong"]` | `tulong` |
| Core | `["help"]` | `help` |
| Core | `["save me"]` | `save_me` |
| Core | `["help me"]` | `help_me` |
| Core | `["please help"]` | `please_help` |
| Core | `["i need help"]` | `i_need_help` |
| Core | `["saklolo"]` | `saklolo` |
| Core | `["tulungan niyo ako"]` | `tulungan_niyo_ako` |
| Core | `["tulungan mo ako"]` | `tulungan_mo_ako` |
| Extended | `["tulungan ako"]` | `tulungan_ako` |
| Extended | `["kailangan ko ng tulong"]` | `kailangan_ko_ng_tulong` |
| Extended | `["iligtas niyo ako"]` | `iligtas_niyo_ako` |
| Extended | `["may emergency"]` | `may_emergency` |
| Extended | `["somebody help"]` | `somebody_help` |
| Extended | `["call ambulance"]` | `call_ambulance` |
| Extended | `["emergency"]` | `emergency` |

Leave `custom_negative_phrases` empty on the first training pass:

```python
config["custom_negative_phrases"] = []
```

Only add custom negatives after Pi testing shows a repeat false activation.

## Colab Notebook Changes

In the setup cell, make the model-resource directory rerunnable:

```python
os.makedirs("./openwakeword/openwakeword/resources/models", exist_ok=True)
```

If a training command using `{sys.executable}` fails in Colab, replace:

```python
!{sys.executable} openwakeword/openwakeword/train.py --training_config my_model.yaml --generate_clips
```

with:

```python
!python openwakeword/openwakeword/train.py --training_config my_model.yaml --generate_clips
```

Do the same for `--augment_clips` and `--train_model`.

## Single-Phrase Manual Run

For one phrase, edit the notebook's config cell like this:

```python
config = yaml.safe_load(open("openwakeword/examples/custom_model.yml", "r").read())

config.update(COMMON_OVERRIDES)
config["target_phrase"] = ["save me"]
config["model_name"] = "save_me"
config["custom_negative_phrases"] = []

with open("my_model.yaml", "w") as file:
    yaml.safe_dump(config, file, sort_keys=False)
```

Then run:

```python
!python openwakeword/openwakeword/train.py --training_config my_model.yaml --generate_clips
!python openwakeword/openwakeword/train.py --training_config my_model.yaml --augment_clips
!python openwakeword/openwakeword/train.py --training_config my_model.yaml --train_model
```

If `my_custom_model/save_me.tflite` is missing after training, run the notebook's
manual ONNX-to-TFLite conversion cell.

## Batch Training Cell

After the data download cells finish once, replace the config/training section
with this batch cell:

```python
DISTRESS_CONFIGS = [
    {"target_phrase": ["tulong"], "model_name": "tulong"},
    {"target_phrase": ["help"], "model_name": "help"},
    {"target_phrase": ["save me"], "model_name": "save_me"},
    {"target_phrase": ["help me"], "model_name": "help_me"},
    {"target_phrase": ["please help"], "model_name": "please_help"},
    {"target_phrase": ["i need help"], "model_name": "i_need_help"},
    {"target_phrase": ["saklolo"], "model_name": "saklolo"},
    {"target_phrase": ["tulungan niyo ako"], "model_name": "tulungan_niyo_ako"},
    {"target_phrase": ["tulungan mo ako"], "model_name": "tulungan_mo_ako"},
    {"target_phrase": ["tulungan ako"], "model_name": "tulungan_ako"},
    {"target_phrase": ["kailangan ko ng tulong"], "model_name": "kailangan_ko_ng_tulong"},
    {"target_phrase": ["iligtas niyo ako"], "model_name": "iligtas_niyo_ako"},
    {"target_phrase": ["may emergency"], "model_name": "may_emergency"},
    {"target_phrase": ["somebody help"], "model_name": "somebody_help"},
    {"target_phrase": ["call ambulance"], "model_name": "call_ambulance"},
    {"target_phrase": ["emergency"], "model_name": "emergency"},
]

def write_config(item):
    config = yaml.safe_load(open("openwakeword/examples/custom_model.yml", "r").read())
    config.update(COMMON_OVERRIDES)
    config["target_phrase"] = item["target_phrase"]
    config["model_name"] = item["model_name"]
    config["custom_negative_phrases"] = []
    yaml_path = f"{item['model_name']}.yaml"
    with open(yaml_path, "w") as file:
        yaml.safe_dump(config, file, sort_keys=False)
    return yaml_path

for item in DISTRESS_CONFIGS:
    yaml_path = write_config(item)
    print(f"Training {item['model_name']} from {item['target_phrase']}")
    !python openwakeword/openwakeword/train.py --training_config "{yaml_path}" --generate_clips
    !python openwakeword/openwakeword/train.py --training_config "{yaml_path}" --augment_clips
    !python openwakeword/openwakeword/train.py --training_config "{yaml_path}" --train_model
```

Run the core models first. Train the extended models after the core models pass
basic Pi testing.

## Optional Broad Safety-Net Models

If advisors require a more general "distress" detector, train these after the
single-phrase models:

```python
{"target_phrase": ["help", "help me", "save me", "please help", "i need help", "somebody help", "call ambulance", "emergency"], "model_name": "distress_en"}
{"target_phrase": ["tulong", "saklolo", "tulungan niyo ako", "tulungan mo ako", "tulungan ako", "kailangan ko ng tulong", "iligtas niyo ako", "may emergency"], "model_name": "distress_tl"}
```

Use a higher runtime threshold for broad models, usually `0.75` to `0.85`,
because they intentionally activate on more phrases.

## Offline Requirement

The initial Colab session downloads repositories, Python packages, Piper voices,
background data, RIR data, and feature `.npy` files. After those files exist in
the runtime or Google Drive, synthetic speech generation, augmentation, training,
ONNX export, and TFLite conversion run locally without external APIs.

For repeatable offline reruns, copy these folders/files to Google Drive:

```text
piper-sample-generator/
openwakeword/
mit_rirs/
audioset_16k/
fma/
openwakeword_features_ACAV100M_2000_hrs_16bit.npy
validation_set_features.npy
```

## Copy Models To The Pi

Copy each finished `.tflite` file to:

```text
/home/thesis/Project_Pi/raspberry_pi/kws/openwakeword_models/
```

Example:

```bash
scp my_custom_model/save_me.tflite thesis@10.156.203.236:/home/thesis/Project_Pi/raspberry_pi/kws/openwakeword_models/
```

Then restart:

```bash
sudo systemctl restart kws-alert.service
sudo journalctl -u kws-alert.service -f
```

The service skips missing files and loads every trained distress model that
exists in the model directory.

## Pi Threshold Tuning

Start with:

```bash
OPENWAKEWORD_WAKE_THRESHOLD=0.65
OPENWAKEWORD_VAD_THRESHOLD=0.50
```

For noisy rooms:

```bash
OPENWAKEWORD_WAKE_THRESHOLD=0.70
OPENWAKEWORD_VAD_THRESHOLD=0.55
```

For weak or distant victim voices:

```bash
OPENWAKEWORD_WAKE_THRESHOLD=0.55
OPENWAKEWORD_VAD_THRESHOLD=0.40
```

Use per-phrase thresholds for phrases that are too sensitive or too strict:

```bash
OPENWAKEWORD_MODEL_THRESHOLDS="tulong=0.55,help=0.70,save me=0.65,tulungan niyo ako=0.60,emergency=0.80"
```

Recommended tuning procedure:

1. Record 20 to 30 positive examples per phrase from each expected speaker.
2. Record at least 30 minutes of negative audio from the deployment area.
3. Start at global threshold `0.65`.
4. Raise a phrase threshold by `0.05` if it false-activates.
5. Lower a phrase threshold by `0.05` if real shouts are missed.
6. Keep VAD near `0.45` to `0.55`; lower it only if weak cries are being gated
   out before openWakeWord can score them.
7. Keep thermal confirmation enabled for final alert confidence so the audio
   detector can be sensitive without causing immediate high-severity alerts.

## Tagalog Accuracy Note

The notebook downloads an English Piper voice by default. That is acceptable for
English phrases, but it may pronounce Tagalog phrases poorly. For best Tagalog
accuracy, validate `tulong`, `saklolo`, and longer Tagalog phrases on real local
voices. If a Tagalog model has low recall, add real local samples through the
manual openWakeWord training workflow or replace the Piper voice with a Tagalog
or Filipino TTS voice if one is available in your Colab setup.
