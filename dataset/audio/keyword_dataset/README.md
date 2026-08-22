# Project Pi openWakeWord Keyword Dataset

This folder is the collection point for real and generated keyword-spotting
data. The repository tracks this README and the pipeline scripts only. Raw
audio, metadata with speaker details, model binaries, split manifests,
predictions, and evaluation outputs are intentionally ignored by Git.

## Keywords

English:

- `help`
- `help me`
- `save me`
- `please help`
- `emergency`
- `rescue`
- `over here`
- `ouch`

Tagalog:

- `tulong`
- `saklolo`
- `tulungan niyo ako`
- `tulungan mo ako`
- `kailangan ko ng tulong`
- `ang sakit`
- `aray`
- `sunog`
- `agai`

## Folder Layout

Run the recorder once with `--init-only` to create the full layout:

```bash
python3 raspberry_pi/kws/record_keyword_dataset.py \
  --dataset-dir dataset/audio/keyword_dataset \
  --speaker-id init \
  --age-group adult \
  --gender unknown \
  --distance-m 1 \
  --noise-condition quiet \
  --init-only
```

Expected structure:

```text
dataset/audio/keyword_dataset/
├── positive/
│   ├── help/
│   ├── help_me/
│   ├── save_me/
│   └── ... all 17 keyword folders
├── negative/
│   ├── random_speech/
│   ├── noise/
│   ├── silence/
│   └── music/
├── augmented/
├── splits/
├── models/
├── predictions/
├── evaluation/
└── metadata.csv
```

## Real Recording Protocol

Use at least five speakers across age groups, genders, accents, and speaking
styles. For each speaker:

- Record 10 samples per keyword.
- Record at 1 m, 2 m, and 3 m when possible.
- Include quiet and noisy conditions.
- Keep each sample between 3 and 5 seconds.
- Save as 16 kHz, 16-bit, mono WAV.

Example Pi command:

```bash
cd ~/Project_Pi
~/kws-env/bin/python raspberry_pi/kws/record_keyword_dataset.py \
  --dataset-dir dataset/audio/keyword_dataset \
  --speaker-id sp01 \
  --age-group adult \
  --gender female \
  --distance-m 1 \
  --noise-condition quiet \
  --samples 10 \
  --seconds 3.5
```

For one keyword only:

```bash
~/kws-env/bin/python raspberry_pi/kws/record_keyword_dataset.py \
  --dataset-dir dataset/audio/keyword_dataset \
  --speaker-id sp01 \
  --age-group adult \
  --gender female \
  --distance-m 2 \
  --noise-condition fan \
  --keyword tulong \
  --samples 10
```

## Negative Samples

Place negative examples under:

- `negative/random_speech/`
- `negative/noise/`
- `negative/silence/`
- `negative/music/`

Target at least 2000 negative clips. They must not contain the deployed
keywords. Keep the same 16 kHz, 16-bit, mono WAV format.

## Synthetic And Augmented Data

Synthetic TTS should be generated outside Git, preferably in Colab:

- English: Azure voices such as `en-US-AriaNeural`, `en-US-GuyNeural`,
  `en-US-AnaNeural`.
- Tagalog: HuggingFace `facebook/mms-tts-tgl`.
- Age simulation: child `+6` semitones, teenager `+2`, adult `0`, elder `-3`.

After real/TTS clips are present, augmentation can be run:

```bash
~/kws-env/bin/python raspberry_pi/kws/augment_keyword_dataset.py \
  --dataset-dir dataset/audio/keyword_dataset \
  --output-dir dataset/audio/keyword_dataset/augmented \
  --copies-per-file 2
```

The augmenter requires optional packages:

```bash
pip install librosa soundfile numpy
```

## Validation

Run validation before training:

```bash
~/kws-env/bin/python raspberry_pi/kws/validate_keyword_dataset.py \
  --dataset-dir dataset/audio/keyword_dataset \
  --json-out dataset/audio/keyword_dataset/evaluation/validation_report.json
```

The validator checks sample rate, channel count, bit depth, duration, clipping,
per-keyword counts, and negative-class counts.

## Training

Create deterministic train/validation/test splits:

```bash
python3 raspberry_pi/kws/train_openwakeword_models.py \
  --dataset-dir dataset/audio/keyword_dataset \
  --manifest-out dataset/audio/keyword_dataset/splits/openwakeword_split.json \
  --manifest-only
```

Run actual openWakeWord training in a prepared Colab/openWakeWord environment:

```bash
python3 raspberry_pi/kws/train_openwakeword_models.py \
  --dataset-dir dataset/audio/keyword_dataset \
  --manifest-out dataset/audio/keyword_dataset/splits/openwakeword_split.json \
  --output-dir dataset/audio/keyword_dataset/models \
  --openwakeword-command "<your-openwakeword-training-entrypoint>"
```

The script does not fabricate training results. If no training command is
provided, it writes the manifest and exits.

## Evaluation

After model inference creates prediction files with `label` and `score`
columns/fields, compute metrics:

```bash
python3 raspberry_pi/kws/evaluate_keyword_models.py \
  --predictions-dir dataset/audio/keyword_dataset/predictions \
  --threshold 0.5 \
  --negative-hours 2.0 \
  --json-out dataset/audio/keyword_dataset/evaluation/model_metrics.json
```

Metrics include true positives, false positives, true negatives, false
negatives, precision, recall, F1 score, false accepts per hour, and a binary
confusion matrix per keyword.
