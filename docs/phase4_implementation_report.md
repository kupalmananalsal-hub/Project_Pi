# Phase 4 implementation and observed data readiness

Development baseline: `b982348c5034fb8aed0f3883b00932b132c1c06e`.
Branch: `phase4/multilingual-dataset-integration`. This is dataset preparation,
not model training, deployment, or physical-device certification.

## Outcome

Implemented streaming archive catalogs/imports, deterministic audio conversion,
private provenance sidecars, transcript candidate mining, reviewed segment import,
strict validation, grouped splits, readiness reports and negative recording in the
existing Training UI/API. Existing 17 distress labels remain unchanged. Cebuano
has a separate empty approved inventory and an unapproved candidate recorder.

The actual local positive directory `dataset/audio/keyword_dataset/positive/`
contains **zero WAV files**. No positive speaker, session or ReSpeaker capture
can be verified. All 17 deployed classes and Cebuano are
`INSUFFICIENT_POSITIVES`; no class is ready for an experiment. Positive-dependent
training preparation was not performed.

The active public corpus contains **563 samples**: 468 ordinary-speech negatives
and 95 noise clips. These passed format, provenance, transcript screening, exact
checksum and near-duplicate checks. “Verified” in the aggregate source reports
means those automated checks against source labels, **not human listening or
recognition accuracy**. Public corpus language labels are retained; code-switching
and incorrectly labeled prompts require human review before per-language claims.

See the exact-column tables:

- [Dataset inventory](phase4_dataset_inventory.csv)
- [Import summary, source hashes and restrictions](phase4_import_summary.csv)
- [Training readiness for every keyword](phase4_training_readiness.csv)
- [Commands, schema compatibility and review workflow](multilingual_dataset_integration.md)

## Actual source processing

All three archives were physically accessible on this Windows workstation.
UP-DSP: 48,991,661,969 bytes; MSWC Microset: 612,495,518 bytes;
Speech Commands v0.02: 2,428,923,189 bytes. Archives remain untouched and ignored
by Git. Catalog scans stream compressed members without extracting whole trees.
The source inventory counts regular files, excluding directory entries.

UP-DSP imported 280 initial clips. Two exact duplicates were quarantined outside
the active corpus, leaving 278. Reimport reports those two duplicates plus two
clipped files and 18 clips longer than five seconds as rejections. MSWC imported
97, rejecting two clipped and one resampling-clipped recording. Speech Commands
imported 93 spoken words and 95 noise chunks; nine clipping rejections occurred
at source/chunk processing. Counts are not a claim that every rejected source
would produce one sample. All reruns reused existing identities without duplicate
metadata. Selected imports were bounded to 100 source recordings per language,
kind and label; noise sources can generate multiple chunks.

The full Speech Commands archive was downloaded because this supplied tar format
is sequential; only selected audio was imported. Its SHA-256 matches the pinned
TensorFlow Datasets checksum. Original official word splits are retained; all 95
noise clips currently belong to train. **There is no noise validation/test coverage
and no imported genuine silence class.** No silence was fabricated.

No exact standalone distress phrase or requested hard-negative label was found
in the UP-DSP/MSWC eligible metadata. UP-DSP longer transcripts have 441 distress
phrase matches and 36 hard-negative matches: 477 candidate rows from 476 distinct
recordings. None was promoted to a verified positive or hard-negative clip.
Timestamps and competent human listening are still needed. Candidate labels in
Cebuano-directory recordings are not an approved Cebuano distress vocabulary.

All six priority hard-negative expressions are currently MISSING as verified
isolated clips: hi, hello, kamusta, helpful, healthy, helmet. The private review
queue and recording checklist support their collection. MSWC Spanish records
remain Spanish in the catalog and were not imported as English.

## Validation and splits

Strict validation: 563 indexed WAVs, 563 passing, zero current validation failures,
zero current near-duplicate flags. Two exact duplicates were detected and
quarantined earlier; original archives were preserved. Near-duplicate detection
uses waveform correlation and is a review heuristic, not exhaustive proof.

The local negative-only manifest assigns **428 train / 57 validation / 78 test**
with seed 1337. Speaker, session, source-recording, duplicate and augmentation
links are joined before splitting; official split conflicts fail rather than
silently breaking independence. Unknown speech speakers require review. The
manifest is **not** a positive-model training manifest. No physical holdout has
been supplied. Reserved physical holdout paths cannot enter preparation splits
or downloadable dataset exports.

Readiness requires verified labels and provenance, clean leakage checks, at least
three independent real groups per positive language/class, language-matched
negatives, held-out positive coverage and verified hard negatives. Minimum sample
counts are not specified, so missing sample counts are NOT_SPECIFIED. Meeting
these structural gates would permit an experiment, not prove adequate accuracy.

Private detailed artifacts stay under the ignored keyword dataset directory:
`reports/sample_inventory.csv`, `reports/readiness.json`, `reports/validation.json`,
source review queues, source catalogs, provenance and
`splits/negative_only_split.json`. Only anonymous aggregate reports are committed.

## Verification

| Command/suite | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| `python -m unittest test.test_keyword_dataset_pipeline` | 14 | 0 | 0 | 0 |
| `python -m unittest test.test_keyword_fusion` | 18 | 0 | 0 | 0 |
| `python -m unittest test.test_alert_decision` | 49 | 0 | 0 | 0 |
| `python -m unittest test.test_multilingual_dataset` | 19 | 0 | 0 | 0 |
| `python -m unittest discover -s test -p "test_*.py"` | 230 | 0 | 0 | 3 |
| `flutter test` | 71 | 0 | 0 | 0 |

Python used the isolated `build/phase3-test-env/Scripts/python.exe` environment.
Three existing Linux filesystem permission checks were skipped on Windows.
Dart analysis of the changed Training files and new widget test passed. Synthetic
fixture tests verify software behavior, not speech recognition performance.

## Remaining blockers and boundaries

- Provide consented, labeled positive recordings with real speaker/session/device
  evidence. Do not infer ReSpeaker capture from this software or folder names.
- Listen-review public candidate clips and validate language/word boundaries.
  Collect missing hard negatives, genuine silence, and independent noise holdouts.
- Obtain competent-speaker approval and sufficient positives for Cebuano.
- Supply a separate untouched physical holdout. No new Pi/Android/ReSpeaker
  experiment was performed in this implementation.
- A controlled baseline detector pass was NOT RUN: openWakeWord is unavailable in
  this test environment. Mining here searches transcripts, not model scores.
- No neural model was trained or deployed in this phase. No accuracy improvement
  is claimed. Deployed models, thresholds, alert policy, thermal/manual controls,
  Phase 3 delivery behavior and Flutter emergency presentation were not changed.
- The original archives, private metadata and audio are excluded from Git.
  `.cursor/` is preserved. No automatic merge into main is authorized here.

UP-DSP's [source terms](https://mozilladatacollective.com/datasets/cmmxhw46c00tqnw07xyr94zjk)
include research-only use and prohibit redistribution/third-party sharing without
written consent, beyond the displayed CC-BY-NC-4.0 label. Its records are blocked
from downloadable dataset ZIP export. [MSWC](https://mlcommons.org/datasets/multilingual-spoken-words/)
is CC-BY-4.0 and prohibits attempts to identify speakers. Source notices remain
local with provenance; aggregate tables contain no participant identifiers.

## Exact changed files

- `.gitignore`
- `docs/multilingual_dataset_integration.md`
- `docs/phase4_dataset_inventory.csv`
- `docs/phase4_implementation_report.md`
- `docs/phase4_import_summary.csv`
- `docs/phase4_training_readiness.csv`
- `lib/providers/training_provider.dart`
- `lib/screens/training_screen.dart`
- `lib/services/pi_api_service.dart`
- `raspberry_pi/backend/main.py`
- `raspberry_pi/config/cebuano_dataset_inventory.json`
- `raspberry_pi/kws/augment_keyword_dataset.py`
- `raspberry_pi/kws/collect_cebuano_candidate.py`
- `raspberry_pi/kws/dataset_integrity.py`
- `raspberry_pi/kws/dataset_readiness.py`
- `raspberry_pi/kws/download_speech_commands_negatives.py`
- `raspberry_pi/kws/import_keyword_datasets.py`
- `raspberry_pi/kws/keyword_dataset_common.py`
- `raspberry_pi/kws/requirements-dataset.txt`
- `raspberry_pi/kws/train_openwakeword_models.py`
- `raspberry_pi/kws/validate_keyword_dataset.py`
- `test/test_multilingual_dataset.py`
- `test/test_training_api.py`
- `test/training_negative_screen_test.dart`
