# Negative Training Samples — Background Noise

This folder contains negative training data for the Project Pi emergency
alert keyword spotting system. The audio clips in `noise/` are short
household background recordings — not keyword samples — and must **never**
be used as positive training data.

---

## Source

**Google Speech Commands Dataset v0.02**
Author: Pete Warden, Google Brain Team (2018)
URL: <http://download.tensorflow.org/data/speech_commands_v0.02.tar.gz>

The `_background_noise_` folder from this dataset contains six long
recordings of real household sounds:

| Source file | Description |
|---|---|
| `doing_the_dishes.wav` | Dishes being washed and rinsed |
| `dude_miaowing.wav` | Cat vocalisations |
| `exercise_bike.wav` | Stationary bicycle |
| `pink_noise.wav` | Synthetic pink noise |
| `running_tap.wav` | Tap water |
| `white_noise.wav` | Synthetic white noise |

---

## License

The Google Speech Commands Dataset is released under the
[Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)
licence.  You must attribute the dataset when redistributing or publishing
any derivative work.

---

## How to Regenerate

Run the download-and-chunk script from the project root:

```bash
# Download the archive and generate ≥500 clips (default)
python raspberry_pi/kws/download_speech_commands_negatives.py

# Use an already-downloaded archive
python raspberry_pi/kws/download_speech_commands_negatives.py \
    --local-archive /path/to/speech_commands_v0.02.tar.gz

# All options
python raspberry_pi/kws/download_speech_commands_negatives.py \
    --output-dir dataset/audio/keyword_dataset/negative/noise \
    --min-clips 500 \
    --keep-archive \
    --cleanup
```

The script will:
1. Stream-download the ~2.4 GB archive (unless `--local-archive` is given).
2. Extract **only** the `_background_noise_/` folder.
3. Convert every WAV to 16 kHz mono 16-bit PCM.
4. Slice each recording into random 1.0 – 3.0 s chunks with 0.2 s overlap.
5. Reject silent or malformed chunks.
6. Append one row per accepted chunk to `metadata.csv`.
7. The process is idempotent: re-running it skips files that already exist.

---

## Usage in Training

The training manifest builder
([`train_openwakeword_models.py`](../../../../raspberry_pi/kws/train_openwakeword_models.py))
automatically includes **all** files under `negative/` as negative samples
when building the train / val / test split.

Chunks from the same source recording are kept in the **same split**
(grouped by source stem) to prevent acoustic data leakage between partitions.

---

## ⚠️ Important Notes

- These recordings are **negative samples only**. They teach the model to
  ignore household sounds, not to detect emergency keywords.
- Do **not** label any of these files as a keyword or include them in the
  `positive/` folder.
- Git ignores all `.wav` files and `metadata.csv`. The raw audio is never
  committed to the repository. Only this README and the pipeline scripts
  are tracked.

---

## Before / After Evaluation

After retraining with these negatives, compare false-positive and recall
metrics using `raspberry_pi/kws/evaluate_keyword_models.py`:

```bash
# Baseline (before retraining)
python raspberry_pi/kws/evaluate_keyword_models.py \
    --predictions-dir dataset/audio/keyword_dataset/predictions/ \
    --threshold 0.5 \
    --negative-hours <hours_of_negative_audio> \
    --json-out dataset/audio/keyword_dataset/evaluation/baseline.json

# After retraining
python raspberry_pi/kws/evaluate_keyword_models.py \
    --predictions-dir dataset/audio/keyword_dataset/predictions/ \
    --threshold 0.5 \
    --negative-hours <hours_of_negative_audio> \
    --json-out dataset/audio/keyword_dataset/evaluation/with_noise_negatives.json
```

**Acceptance criteria:**
- False accepts per hour must decrease.
- Positive recall must not drop by more than 2.0 percentage points.
