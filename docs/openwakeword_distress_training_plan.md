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

## Stable Colab Workflow

Use this workflow instead of the older direct `!python train.py ...` cells. It
prevents the notebook from continuing after a failed stage and removes stale
feature caches before augmentation.

Start from a fresh runtime when a phrase has already failed:

1. In Colab, choose **Runtime > Disconnect and delete runtime**.
2. Reconnect with a GPU runtime.
3. Run the notebook environment setup and data download cells.
4. Do not run `--augment_clips` unless `--generate_clips` finishes without a
   traceback.

In the setup cell, keep the model-resource directory rerunnable:

```python
os.makedirs("./openwakeword/openwakeword/resources/models", exist_ok=True)
```

After the environment setup cell, run this single compatibility/preflight cell:

```python
!pip install -q soundfile

import importlib
import inspect
import subprocess
import sys
from pathlib import Path

def patch_deep_phonemizer_torch_load():
    import dp.model.model as dp_model

    path = Path(inspect.getfile(dp_model))
    text = path.read_text()
    old = "checkpoint = torch.load(checkpoint_path, map_location=device)"
    new = "checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)"

    if old in text and new not in text:
        path.write_text(text.replace(old, new))
        print(f"Patched deep-phonemizer torch.load: {path}")
    else:
        print(f"deep-phonemizer patch already present or not needed: {path}")

def patch_torchaudio_info():
    import torchaudio

    path = Path(inspect.getfile(torchaudio))
    text = path.read_text()
    marker = "# Project Pi torchaudio.info compatibility patch"
    patch = r'''

# Project Pi torchaudio.info compatibility patch
if "info" not in globals():
    class AudioMetaData:
        def __init__(
            self,
            sample_rate,
            num_frames,
            num_channels=1,
            bits_per_sample=0,
            encoding="UNKNOWN",
        ):
            self.sample_rate = sample_rate
            self.num_frames = num_frames
            self.num_channels = num_channels
            self.bits_per_sample = bits_per_sample
            self.encoding = encoding

    def info(uri, format=None, buffer_size=4096, backend=None):
        del format, buffer_size, backend
        import soundfile as _sf

        metadata = _sf.info(str(uri))
        return AudioMetaData(
            sample_rate=int(metadata.samplerate),
            num_frames=int(metadata.frames),
            num_channels=int(metadata.channels),
            bits_per_sample=0,
            encoding=str(metadata.format or "UNKNOWN"),
        )
'''

    if marker not in text:
        path.write_text(text + patch)
        print(f"Patched torchaudio.info fallback: {path}")
    else:
        print(f"torchaudio.info patch already present: {path}")

    importlib.reload(torchaudio)
    if not hasattr(torchaudio, "info"):
        raise RuntimeError("torchaudio.info patch failed in current process")

patch_deep_phonemizer_torch_load()
patch_torchaudio_info()

feature_downloads = {
    "validation_set_features.npy": (
        "https://huggingface.co/datasets/davidscripka/openwakeword_features/"
        "resolve/main/validation_set_features.npy"
    ),
    "openwakeword_features_ACAV100M_2000_hrs_16bit.npy": (
        "https://huggingface.co/datasets/davidscripka/openwakeword_features/"
        "resolve/main/openwakeword_features_ACAV100M_2000_hrs_16bit.npy"
    ),
}

for output_path, url in feature_downloads.items():
    if not Path(output_path).exists():
        print(f"Downloading missing feature file: {output_path}")
        subprocess.run(
            ["wget", "-q", "--show-progress", "-O", output_path, url],
            check=True,
        )

required_paths = [
    "openwakeword/openwakeword/train.py",
    "openwakeword/examples/custom_model.yml",
    "piper-sample-generator/models/en_US-libritts_r-medium.pt",
    "validation_set_features.npy",
    "openwakeword_features_ACAV100M_2000_hrs_16bit.npy",
]
missing = [path for path in required_paths if not Path(path).exists()]
if missing:
    raise FileNotFoundError(f"Missing setup/data files: {missing}")

subprocess.run(
    [
        sys.executable,
        "-c",
        "import torchaudio; assert hasattr(torchaudio, 'info'); print('subprocess torchaudio.info OK')",
    ],
    check=True,
)
print("Colab preflight OK.")
```

Then create `my_model.yaml` for exactly one phrase. Use smoke-test settings
first. After one phrase successfully exports `.tflite`, switch
`SMOKE_TEST = False` for high-accuracy training.

```python
import yaml

PHRASE = ["help"]
MODEL_NAME = "help"
SMOKE_TEST = True

def build_overrides(smoke_test):
    return {
        "n_samples": 1000 if smoke_test else 50000,
        "n_samples_val": 1000 if smoke_test else 5000,
        "steps": 10000 if smoke_test else 50000,
        "target_accuracy": 0.60 if smoke_test else 0.80,
        "target_recall": 0.25 if smoke_test else 0.60,
        "target_false_positives_per_hour": 0.20 if smoke_test else 0.05,
        "max_negative_weight": 1000 if smoke_test else 2500,
        "augmentation_rounds": 1 if smoke_test else 2,
        "background_paths": ["./audioset_16k", "./fma"],
        "background_paths_duplication_rate": [2, 1],
        "rir_paths": ["./mit_rirs"],
        "false_positive_validation_data_path": "validation_set_features.npy",
        "feature_data_files": {
            "ACAV100M_sample": "openwakeword_features_ACAV100M_2000_hrs_16bit.npy",
        },
    }

COMMON_OVERRIDES = build_overrides(SMOKE_TEST)

config = yaml.safe_load(open("openwakeword/examples/custom_model.yml", "r").read())
config.update(COMMON_OVERRIDES)
config["target_phrase"] = PHRASE
config["model_name"] = MODEL_NAME
config["custom_negative_phrases"] = []

with open("my_model.yaml", "w") as file:
    yaml.safe_dump(config, file, sort_keys=False)

print(f"Configured {MODEL_NAME}: {PHRASE}, smoke_test={SMOKE_TEST}")
```

Run this helper cell once. It reads `model_name` from `my_model.yaml`, so it
works for `tulong`, `help`, `save_me`, and every other phrase without editing
hard-coded paths.

```python
import shutil
import subprocess
import sys
from math import gcd
from pathlib import Path

import numpy as np
import yaml
from scipy.io import wavfile
from scipy.signal import resample_poly

MODEL_ROOT = Path("/content/my_custom_model")

def load_training_config():
    return yaml.safe_load(open("my_model.yaml", "r").read())

def model_name():
    return load_training_config()["model_name"]

def model_dir():
    return MODEL_ROOT / model_name()

def reset_model_outputs():
    name = model_name()
    for path in [
        MODEL_ROOT / name,
        MODEL_ROOT / f"{name}.onnx",
        MODEL_ROOT / f"{name}.tflite",
        MODEL_ROOT / f"{name}.pt",
    ]:
        if path.is_dir():
            shutil.rmtree(path)
            print(f"Removed folder: {path}")
        elif path.exists():
            path.unlink()
            print(f"Removed file: {path}")
    model_dir().mkdir(parents=True, exist_ok=True)
    print(f"Reset model output folder: {model_dir()}")

def clear_feature_cache():
    for file in model_dir().glob("*features*.npy"):
        file.unlink()
        print(f"Removed feature cache: {file.name}")

def run_stage(stage):
    print(f"Running stage: {stage} for {model_name()}")
    subprocess.run(
        [
            sys.executable,
            "openwakeword/openwakeword/train.py",
            "--training_config",
            "my_model.yaml",
            f"--{stage}",
        ],
        check=True,
    )

def check_and_fix_sample_rate(target_sr=16000):
    wavs = list(model_dir().rglob("*.wav"))
    if not wavs:
        raise FileNotFoundError(f"No WAV clips found in {model_dir()}")

    fixed = 0
    bad = []
    for wav_path in wavs:
        sr, audio = wavfile.read(str(wav_path))
        if sr != target_sr:
            divisor = gcd(sr, target_sr)
            audio_f32 = audio.astype(np.float32)
            audio_16k = resample_poly(
                audio_f32,
                target_sr // divisor,
                sr // divisor,
                axis=0,
            )
            audio_16k = np.clip(audio_16k, -32768, 32767).astype(np.int16)
            wavfile.write(str(wav_path), target_sr, audio_16k)
            fixed += 1

        verify_sr, _ = wavfile.read(str(wav_path))
        if verify_sr != target_sr:
            bad.append(str(wav_path))

    print(f"WAV files checked={len(wavs)}, fixed={fixed}, remaining_bad={len(bad)}")
    if bad:
        raise ValueError("Some WAV files are still not 16 kHz:\n" + "\n".join(bad[:10]))

def verify_generated_clips():
    wavs = list(model_dir().rglob("*.wav"))
    if not wavs:
        raise FileNotFoundError(f"Generation failed: no WAV files in {model_dir()}")
    print(f"Generated WAV clips: {len(wavs)}")

def verify_feature_files():
    required = [
        "positive_features_train.npy",
        "positive_features_test.npy",
    ]
    missing = [name for name in required if not (model_dir() / name).exists()]
    if missing:
        existing = sorted(path.name for path in model_dir().glob("*features*.npy"))
        raise FileNotFoundError(
            f"Augmentation did not finish. Missing: {missing}. Existing: {existing}"
        )

    for name in required:
        data = np.load(model_dir() / name, mmap_mode="r")
        print(f"{name}: shape={data.shape}")

def verify_exported_model():
    name = model_name()
    exported = [
        MODEL_ROOT / f"{name}.tflite",
        MODEL_ROOT / f"{name}.onnx",
    ]
    found = [path for path in exported if path.exists()]
    if not found:
        raise FileNotFoundError(f"No exported .tflite or .onnx found for {name}")
    for path in found:
        print(f"Exported: {path} ({path.stat().st_size / 1024:.1f} KB)")

def run_full_pipeline():
    reset_model_outputs()
    run_stage("generate_clips")
    verify_generated_clips()
    check_and_fix_sample_rate()
    clear_feature_cache()
    run_stage("augment_clips")
    verify_feature_files()
    run_stage("train_model")
    verify_exported_model()
```

Run the full phrase pipeline with one command:

```python
run_full_pipeline()
```

If this cell fails, fix the exact error shown before running the next stage. Do
not manually continue to augmentation or training after a failed stage.

## Single-Phrase Run

For each phrase, edit only these values in the config cell:

```python
PHRASE = ["save me"]
MODEL_NAME = "save_me"
SMOKE_TEST = True
```

Run `run_full_pipeline()`. After the smoke test exports a model, run the same
phrase again with:

```python
SMOKE_TEST = False
```

Then recreate `my_model.yaml` and run `run_full_pipeline()` again for the final
high-accuracy model.

## Batch Training Cell

Batch training can consume many Colab hours. Use it only after one phrase has
completed successfully with the stable workflow. It reuses `build_overrides()`
and `run_full_pipeline()` from the cells above.

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

def configure_phrase(item, smoke_test=True):
    config = yaml.safe_load(open("openwakeword/examples/custom_model.yml", "r").read())
    config.update(build_overrides(smoke_test))
    config["target_phrase"] = item["target_phrase"]
    config["model_name"] = item["model_name"]
    config["custom_negative_phrases"] = []

    with open("my_model.yaml", "w") as file:
        yaml.safe_dump(config, file, sort_keys=False)

    print(f"Configured {item['model_name']}: {item['target_phrase']}")

for item in DISTRESS_CONFIGS:
    configure_phrase(item, smoke_test=True)
    run_full_pipeline()
```

Run the core models first. Train the extended models after the core models pass
basic Pi testing. For final models, rerun the loop with `smoke_test=False`.

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
scp my_custom_model/save_me.tflite thesis@10.118.136.32:/home/thesis/Project_Pi/raspberry_pi/kws/openwakeword_models/
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
