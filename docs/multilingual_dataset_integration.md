# Multilingual dataset preparation

This workflow imports local research data into `dataset/audio/keyword_dataset/`.
It does not change deployed models, alert thresholds, pairing or persistence.
Data, provenance, catalogs, splits and model artifacts are ignored by Git.

## Environment and sources

Install `raspberry_pi/kws/requirements-dataset.txt` in an isolated environment.
Audio decoding uses SoundFile/libsndfile (including Opus), NumPy and SciPy.
This phase prepares data only. No neural training or model deployment is performed.

Sources:

- UP-DSP-PLD: https://mozilladatacollective.com/datasets/cmmxhw46c00tqnw07xyr94zjk
  — CC-BY-NC-4.0 as shown on the source listing. Original session logs stay local;
  importer preserves only transcript and hashed speaker/source identifiers.
- MSWC: https://mlcommons.org/datasets/multilingual-spoken-words/ — CC-BY-4.0.
  Requires source CSV `VALID=True` and nonempty speaker identity. Microset is
  English/Spanish, not Filipino/Cebuano and not the full MSWC corpus.
- Speech Commands v0.02: Google-hosted archive, CC-BY-4.0; SHA-256 pinned to
  TensorFlow Datasets' published checksum:
  https://raw.githubusercontent.com/tensorflow/datasets/master/tensorflow_datasets/datasets/speech_commands/checksums.tsv
  `af14739ee7dc311471de98f5f9d2c9191b18aedfe957f4a6ff791c709868ff58`.

Review source terms before redistributing data or models derived from it. These
scripts do not grant redistribution rights. Retain citations and attribution.
No public recordings or personal metadata are included in this PR. UP-DSP also
requires research-only use and written consent before redistribution or third-party
sharing; dataset ZIP export blocks UP-DSP records. Both sources prohibit attempts
to identify speakers.

## Scan and bounded import

Run from repository root; replace `python` with your environment's Python path.
Catalog scans stream the compressed archive, storing its member index and
transcript annotations in SQLite without extracting the audio tree. Compressed
tar requires sequential reading; a 49 GB archive takes several minutes per pass.
The archive checksum is verified again on import. Traversal, absolute/drive/ADS
paths, links, special files, duplicate members and oversized members are rejected.
Never use `extractall` with these datasets.

```powershell
python raspberry_pi/kws/import_keyword_datasets.py scan --source pld --archive "$env:USERPROFILE\Downloads\1773845964108-up-dsp-pld.tar.gz" --catalog dataset/audio/keyword_dataset/catalogs/pld.sqlite --report dataset/audio/keyword_dataset/reports/pld-scan.json
python raspberry_pi/kws/import_keyword_datasets.py scan --source mswc --archive "$env:USERPROFILE\Downloads\mswc_microset.tar.gz" --catalog dataset/audio/keyword_dataset/catalogs/mswc.sqlite --report dataset/audio/keyword_dataset/reports/mswc-scan.json
python raspberry_pi/kws/import_keyword_datasets.py download-speech-commands --archive dataset/archives/speech_commands_v0.02.tar.gz
python raspberry_pi/kws/import_keyword_datasets.py scan --source speech_commands --archive dataset/archives/speech_commands_v0.02.tar.gz --catalog dataset/audio/keyword_dataset/catalogs/gsc-v2.sqlite --report dataset/audio/keyword_dataset/reports/gsc-scan.json
python raspberry_pi/kws/import_keyword_datasets.py import --archive "$env:USERPROFILE\Downloads\1773845964108-up-dsp-pld.tar.gz" --catalog dataset/audio/keyword_dataset/catalogs/pld.sqlite --per-label 100 --report dataset/audio/keyword_dataset/reports/pld-import.json
```

Repeat the import command for MSWC and Speech Commands using their archive and
catalog paths. `--per-label` caps selected source recordings per language/label;
noise recordings may yield multiple three-second chunks. Speaker round-robin
selection improves diversity. Increasing the cap adds more source clips; an
unchanged source/cap is idempotent. A rerun verifies existing audio checksums.
Catalogs are immutable: a new archive/version requires a new catalog path.

PLD languages are corpus directory labels (`FIL`, `CEB`, `ENG`), not independent
spoken-language verification. Code-switching and prompts in another language can
occur; review these before claiming per-language accuracy. Logs map WAV filenames
to quoted prompts/transcripts. The importer does not turn a sentence containing a
keyword into a positive clip, and excludes such sentences from the negative pool.
Normalization ignores punctuation and accent marks for matching; no translation
or Cebuano synonym is automatically added to the deployed vocabulary.

Audio is decoded, checked for clipping, downmixed to mono, polyphase-resampled
to 16 kHz and written as PCM16. Clips under one second are right-padded; clips
longer than five seconds are rejected unless an explicitly reviewed crop is
provided. Noise is chunked; quiet noise chunks below RMS 0.001 become silence.
Silence is not fabricated from missing speech. Reports retain rejection counts.

## Positive examples and explicit review

Do not record `hello` under the `help` label. The Training screen now has a
positive/negative selector, language selector and explicit negative categories:
`hi`, `hello`, `kamusta`, `helpful`, `healthy`, `helmet`, `random_speech`, `noise`,
`silence`, `music`. Keep the SAME anonymous speaker ID for one person across all
keywords, languages and sessions. New speakers require distinct IDs. Obtain
recording consent; do not use names. Negative labels do not add runtime keywords.
The legacy positive upload remains compatible; older clients may send unknown
language, which must be reviewed before strict training preparation.

For a target inside a PLD sentence, listen to the original audio and record exact
start/end seconds. Create a local JSONL file with one reviewed crop per member:

```json
{"member":"PLD/FIL/REPLACE/REPLACE.wav","transcript":"tulong","start_s":1.2,"end_s":2.5,"audio_reviewed":true,"reviewer_id":"reviewer_01"}
```

This is a template, NOT observed evidence. The command requires the phrase to
occur in the source transcript and rejects unreviewed or invalid time ranges:

```powershell
python raspberry_pi/kws/import_keyword_datasets.py import --archive "$env:USERPROFILE\Downloads\1773845964108-up-dsp-pld.tar.gz" --catalog dataset/audio/keyword_dataset/catalogs/pld.sqlite --reviewed-segments build/reviewed-segments.jsonl --report dataset/audio/keyword_dataset/reports/reviewed-import.json
```

A review manifest replaces automatic selection for that invocation. Source audio
and crop checksums plus reviewer pseudonym and timing are retained locally. It is
a recorded human assertion, not an automatic semantic verifier. Listen-check
source transcript labels as part of final dataset QA; technical WAV validity does
not establish keyword correctness or distress intent.

## Validation and leakage prevention

```powershell
python raspberry_pi/kws/validate_keyword_dataset.py --strict --json-out dataset/audio/keyword_dataset/reports/validation.json
python raspberry_pi/kws/train_openwakeword_models.py --manifest-only
```

Strict validation requires checksums, provenance, supported labels/formats,
anonymous speaker identity for speech, language, source groups and unique PCM.
It rejects missing metadata, orphan WAVs, clipping and inconsistent labels.
Existing legacy recordings without provenance are NOT silently assigned invented
metadata: review/migrate them before strict preparation.

The strict splitter joins records connected by ANY shared speaker, original
recording, duplicate checksum or augmentation parent before assigning train/val/
test. Augmentation inherits parent language, identity and split. Every positive
language/label and every represented negative language requires at least three
independent real groups and coverage in all splits. Insufficient coverage raises
an error. Synthetic examples are train-only. Split selection is deterministic for
an unchanged dataset and seed; adding data requires a new versioned manifest.
Keep your final evaluation set frozen rather than repeatedly changing it.

The old legacy split helper remains for historical tests; the CLI and backend
Prepare training split action use the strict splitter. The backend returns
`model_trained: false`; it never reports manifest generation as neural training.

## Readiness reports and collection

Run `python raspberry_pi/kws/dataset_readiness.py --all-source-summaries` to
write local unified sample metadata, exact-column aggregate inventories, import
summaries, review queues and readiness states under the ignored reports folder.
The negative-only manifest is preparation evidence, not a usable positive model
training split. Missing sample targets are `NOT_SPECIFIED`.

All unreviewed public positive transcript matches are excluded from import.
Manual crops accept `kind: negative` for one of the six hard-negative expressions;
otherwise the default is positive. Preserve word onset/offset context when reviewing.
Add `--dry-run` to an import to preview source selection without writing audio.
Official Speech Commands validation/test assignments are preserved. Unknown-speaker
speech requires review. Near-identical waveform correlation flags gain/shift
variants for review; it is a bounded heuristic, not exhaustive acoustic deduplication.
Physical holdout recordings must stay under `physical_holdout/` and cannot enter
preparation splits. Do not mine negatives against held-out recordings.

Cebuano positives are blocked until competent speakers approve an inventory.
`collect_cebuano_candidate.py` records unapproved candidates outside the training
corpus, under processed/cebuano_candidates. It does not enable a recognition model.
Use consented speakers, anonymous stable speaker/session IDs, and explicit device
records. Public mono downmixes cannot support ReSpeaker direction-of-arrival
research; untouched multichannel source audio remains in the archives. No gain
normalization is applied. ReSpeaker inference preprocessing and streaming
performance still require controlled hardware experiments.

For each missing expression (hi, hello, kamusta, helpful, healthy, helmet), record
multiple consenting speakers in quiet and representative noisy rooms; record the
microphone and session, listen-check the label, and reserve independent speakers
and sessions as an untouched physical holdout. Collect the 17 positives separately.
Do not infer ReSpeaker capture from a folder name or from this software.

The legacy metadata CSV columns remain unchanged; per-file JSON provenance adds
language, source, transcript, timestamps, original format, verification, hashes,
license and ancestry. Unknown metadata remains unknown. The local unified CSV
exports the requested full schema. A locally reviewed recording is an operator
assertion, not automatic proof of emergency intent.

The thesis evaluation cohort remains exactly 5 IT professionals and 25 rescue/
safety personnel. This work does not alter respondent selection or fabricate
Chapter 4 results.
