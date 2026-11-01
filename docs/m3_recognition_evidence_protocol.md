# Milestone 3 recognition evidence protocol

Purpose: a trustworthy baseline for missed distress keywords and ordinary-speech
false positives, then a before/after comparison of any correction, measured on
the same recordings. Nothing here has been run yet. No result may be reported
that was not measured; a metric with no samples behind it is reported as N/A.

Steps and their approval levels (see `docs/agent_integrations/policy.md`):

| Step | Level | Authorization |
|---|---|---|
| A. Read-only Pi inspection | 1 | Explicit connection approval |
| B. Recording sessions | 2 | Separate approval, plus participant consent |
| C. Replay on the Pi (stops `kws-alert` while it runs) | 4 | Service-control authorization; or run on another Linux machine with copies of the same models (Level 0) |
| D. Correction and re-measurement | 3 | Reviewed change approval |

## A. Level 1 read-only inspection (Raspberry Pi)

Run as `thesis`. Nothing below writes outside the home directory, restarts a
service, opens the microphone, changes hardware, or prints a token: the API token
lives in `/etc/project-pi/backend.env` (root only, never read here), and the
environment capture keeps engine keys only.

```bash
OUT=~/project-pi-l1-$(date +%Y%m%d-%H%M).txt
{
echo "## 1. Deployed code"
git -C ~/Project_Pi log -1 --format='%H %ad %s' --date=iso
git -C ~/Project_Pi status --short | head -20
git -C ~/Project_Pi branch --show-current

echo "## 2. Active keyword service"
systemctl is-active kws-alert.service kws-alert-vosk.service thermal-backend.service
systemctl is-enabled kws-alert.service kws-alert-vosk.service 2>&1
systemctl show -p MainPID,ActiveEnterTimestamp,NRestarts,ExecMainStatus kws-alert.service

echo "## 3. Effective configuration and overrides (paths only)"
systemctl show -p FragmentPath,DropInPaths,EnvironmentFiles kws-alert.service

echo "## 4. Engines loaded and thresholds (this boot)"
journalctl -u kws-alert.service -b --no-pager | grep -E \
  'openWakeWord ready|per-model thresholds|model files not found|load warnings|unavailable|Vosk ready|Vosk disabled|Snowboy ready|Snowboy disabled|died|Traceback|Error' | tail -40

echo "## 5. ReSpeaker capture device"
arecord -l
cat /proc/asound/cards
fuser -v /dev/snd/* 2>&1 | head -20
[ -f ~/.asoundrc ] && cat ~/.asoundrc

echo "## 6. Health"
uptime
vcgencmd measure_temp 2>/dev/null || cat /sys/class/thermal/thermal_zone0/temp
vcgencmd get_throttled 2>/dev/null
free -m
df -h /
systemctl --failed --no-pager
journalctl -u kws-alert.service -b -p err --no-pager | tail -20

echo "## 7. Deployed openWakeWord models"
ls -l ~/Project_Pi/dataset/audio/openwakeword_models/
sha256sum ~/Project_Pi/dataset/audio/openwakeword_models/*.onnx* 2>/dev/null
} > "$OUT" 2>&1
echo "wrote $OUT"

# Effective engine environment of the RUNNING service (drop-ins and env files
# included), engine keys only. This file is the replay harness's --env-file.
PID=$(systemctl show -p MainPID --value kws-alert.service)
tr '\0' '\n' < "/proc/$PID/environ" \
  | grep -E '^(OPENWAKEWORD|SNOWBOY|VOSK|KWS|NOISE|WAV2VEC2|MIC|DIRECTION)_' \
  > ~/kws-effective-$(date +%Y%m%d).env
```

Review both files before sharing them. Stop and report if `MainPID` is 0 (the
service is not running) or if section 4 shows an engine disabled or a model
missing: the baseline would then describe a degraded detector.

## B. Recordings

### Classes

| Class | Kind | Notes |
|---|---|---|
| `help` | positive | English distress keyword |
| `tulong` | positive | Tagalog distress keyword |
| other approved phrases | positive | Only from the approved 17-phrase inventory |
| `hi`, `hello`, `kamusta` | negative | Requires PR #6, which adds these classes; on `main` the only negative classes are `random_speech`, `noise`, `silence`, `music` |
| genuine silence | negative (`silence`) | The room with nobody speaking, recorded with the real microphone; never digital zeros |
| environmental noise | negative (`noise`) | The defense location's actual sounds (fan, crowd, rain, traffic). The existing 95 `noise` clips are Speech Commands background noise, not this environment; report them separately |
| ordinary Tagalog speech | negative (`random_speech`) | Sentences containing `tulog`, `tuloy`, `araw`, `aral`, `aga`, `agad`, `sunod`, `sundo`, `masakit`: words the current Vosk matcher turns into distress keywords |

### Before collecting, fill in and keep with the data

| Field | Value |
|---|---|
| Consent form version and storage location | |
| Speakers per class (and age/gender mix) | |
| Repetitions per speaker per class | |
| Distances (m) | |
| Noise conditions | |
| Device: ReSpeaker on the Pi (Level 2), or the phone app upload | |
| Who annotates keyword onsets, and how | |

### Per-recording checklist

- [ ] Consent recorded for the speaker; stable anonymous `speaker_id`.
- [ ] 16 kHz, mono, 16-bit PCM, 1.0–5.0 s (the backend's upload validation).
- [ ] Metadata row: path, keyword/class, speaker_id, age_group, gender, distance_m, noise_condition, source=`real`.
- [ ] Positives: keyword onset annotated (seconds from file start) in `onsets.csv` (`path,onset_s`). Without it, latency can only be reported "from recording start".
- [ ] Nobody listens to holdout recordings while tuning.

### Splits, by speaker (no speaker in more than one split)

| Split | Location | Used for |
|---|---|---|
| Development | `positive/`, `negative/` | Investigating failures and choosing a correction |
| Validation | `positive/`, `negative/`, speakers listed in `validation_speakers.txt` | Checking a chosen correction before the final run |
| Physical holdout | `physical_holdout/positive/<keyword>/`, `physical_holdout/negative/<class>/` | Recorded on the Pi with the ReSpeaker in the final configuration; run once, for the final before/after table, never used for tuning. PR #6's tooling already refuses `physical_holdout/` in preparation splits; the replay harness only reads it with `--split holdout` |

## C. Replay (baseline, then after a correction)

**Mandatory isolation before real models run:** use a dedicated disposable process
inside an OS-enforced sandbox with network access disabled (including access to
the host backend), no microphone/audio devices exposed, and read-only code,
model and input mounts. Permit writes only to new replay output and scratch
directories; do not expose production databases, outboxes, status files, home
credentials or restricted data beyond the separately authorized input set. Do
not use privileged containers, host networking or host device mounts. Verify
these boundaries with synthetic probes before real replay. Python socket
patches and offline loader flags are additional safeguards, not a security
sandbox for native libraries or subprocesses. Resource checks do not replace
OS memory/CPU quotas. No Pi replay or service control is authorized by this doc.

```bash
~/kws-env/bin/python raspberry_pi/kws/replay_eval.py \
  --dataset-dir dataset/audio/keyword_dataset \
  --env-file ~/kws-effective-YYYYMMDD.env \
  --noise-config ~/captured-noise.json \
  --evidence-mode preliminary \
  --onsets dataset/audio/keyword_dataset/onsets.csv \
  --out-dir build/kws-replay/baseline-dev
```

- Use `--isolation per-recording` (the default) for independent samples.
- `--require-engines` defaults to all three engines; never disable it for reported numbers.
- Preliminary mode is detection-only, with provisional folder labels and no
  correctness metrics; a completed workflow may exit 0 despite evidence limitations.
- Validated mode requires supported review assertions (below). An invalid
  validated run exits **3**, retains `summary.json`, `events.jsonl` and
  `preliminary_detections.csv`, and withholds correctness metrics and
  `predictions.csv`. Resource/worker aborts exit 3 with `aborted.json`; argument
  errors exit 2. Missing dependencies may terminate before any replay.
- Report only validated runs whose `summary.json` has `run.valid_as_evidence=true`,
  after independently checking label evidence, model coverage and isolation.
- Report the run's commit, configuration and model checksums with the numbers (all in `summary.json` under `run`).

### Container-aware memory gate (C1.12)

`mem_available_mib` now means effective allocation headroom: the minimum of host
`MemAvailable` and `max(0, hard_limit - current_usage)` for **each visible memory
cgroup ancestor**, using that ancestor's own aggregate usage. This includes sibling
consumption at a parent; subtracting only the leaf's usage would overestimate space.
Page cache is not subtracted from usage or assumed reclaimable. Values are not
rounded upward across a safety threshold. Existing preflight/abort limits are unchanged.

The reader resolves `/proc/self/cgroup` through `/proc/self/mountinfo`, including
mount-path escapes, cgroup v2 `memory.max`/`memory.current`, and v1 memory-controller
`memory.limit_in_bytes`/`memory.usage_in_bytes`. It checks every visible ancestor up
to the mount root. Where v1 exposes `memory.memsw.limit_in_bytes` and
`memory.memsw.usage_in_bytes`, their combined memory-and-swap headroom also constrains
the minimum; an incomplete pair fails closed. Without either memsw file, that
optional kernel interface is not assumed available. It prefers the widest applicable
mount in hybrid layouts.
V2 `max` and v1 `-1`/large 64-bit unlimited sentinels impose no finite cap; a zero
limit means zero headroom. V1 usage is kernel-reported approximate accounting, not
an exact allocation guarantee; older 32-bit sentinel values are conservatively
treated as finite limits. Genuine root/inactive v2 cgroups can lack memory controls.

Missing or unreadable discovery/required metrics, malformed values, unmappable paths,
changing membership and explicitly clipped non-root hierarchy mounts make effective
headroom unavailable and fail the required memory gate. The reader uses host-only
memory only after reliable discovery establishes no finite applicable visible cap.
`--skip-resource-checks` remains development-only and cannot produce validated evidence.

**Visibility limit:** a cgroup namespace may conceal host ancestors even when it
presents `/` as the mount root. No in-container reader can reconstruct those hidden
limits or sibling usage. The launcher must independently verify all host-side ancestor
limits and pressure before/during real replay. Do not treat passing visible-cgroup
checks as proof of sufficient host resources. These are sampled guards, not atomic
memory reservations or protection against sudden allocations/OOM. Hard OS limits,
model working-set sizing, and target-device health verification remain mandatory.

Preflight now precedes WAV loading and engine import. A failure exits 3 and saves
`preflight_failed.json` with `valid_as_evidence=false`, limits and the full resource
reading. Its `memory` object records host availability, source, effective bytes,
cgroup paths, each sampled limit/usage/headroom, visibility and discovery failures.
The same reader feeds the runtime watchdog; `summary.json` records its last reading
and sampled minimum headroom. Resource aborts save the failing reading, preflight
and limits in `aborted.json` and exit 3 without correctness metrics.

Interface references: [Linux cgroup v2 memory controller](https://docs.kernel.org/admin-guide/cgroup-v2.html#memory)
and [Linux cgroup v1 memory controller](https://docs.kernel.org/admin-guide/cgroup-v1/memory.html).
These explain kernel accounting; they do not certify this implementation or the Pi.

### Model-content coverage and limits

SHA-256 reads files in 1 MiB blocks. `run.model_content_provenance` records paths,
per-file hashes, a deterministic sorted content-manifest digest, status and issues:

- Vosk: every regular file recursively under the configured `VOSK_MODEL_PATH`,
  including acoustic weights, graph, configuration and vocabulary resources.
  Keys are relative to the model root, so its manifest digest survives relocation.
- Snowboy: each comma-separated `SNOWBOY_MODEL_PATHS` file (or legacy
  `SNOWBOY_MODEL_PATH`) and the configured `SNOWBOY_RESOURCE_PATH` common resource.
- openWakeWord: explicitly selected `OPENWAKEWORD_MODELS`, or discovered `.onnx`
  files from the same configured/default/legacy directory selection as the
  deployed wrapper; includes required `.onnx.data` companion weights.

The deployed default paths are used when those environment keys are absent.
Missing, empty, unreadable or symlinked assets are marked `unverified`; symlink
directories are never traversed. Use immutable regular-file model copies under
separate authorization. Incomplete core model-content provenance invalidates
validated evidence. Hashes are checked again after replay; changes invalidate
the run. These before/after checks do not detect a transient change restored
between checks, so immutable read-only mounts remain mandatory. Scanning twice
costs disk I/O and metadata storage proportional to file count; it does not load
model contents into RAM. No model files are modified or redistributed.

Installed distribution versions are recorded for Vosk, openWakeWord,
ONNX Runtime, NumPy, SciPy, PyTorch, Transformers and PyAudio (`null` means no
distribution metadata was found). Versions do **not** authenticate installed code.
The `unverified_components` list explicitly excludes package/native binary
contents, Snowboy SWIG/native bindings, openWakeWord's bundled embedding,
melspectrogram and VAD assets, wav2vec2 cache/model assets, and OS/drivers/firmware.
This is core model provenance, not complete runtime reproducibility certification.

### Reference-label provenance

For validated mode, every selected metadata row must have `review_status=verified`,
`reviewed_label` matching the positive/negative folder class,
`review_method=human_listening`, and a nonempty `review_evidence` reference to a
supporting local review record. Unknown/unassessed placeholders are rejected.
Existing metadata remains usable in preliminary mode without these new fields.
These are **operator assertions**, not authenticated proof of a human review.
The harness does not open or authenticate the referenced review record. Researchers
must independently establish its identity, recording ID/hash binding, explicit
listening observations, label scope and unresolved disagreements before publication.
Use anonymous local evidence IDs; do not invent reviewer identities, dates or labels.
The summary preserves those assertions and each input audio hash for audit.

Literal distress-keyword presence and emergency intent remain separate judgments:
ordinary context alone does not establish lexical keyword absence. Text transcripts,
fuzzy matches and technical screening cannot supply human-listening provenance.
The existing 54 PLD recordings remain **preliminary-only** until independently
defensible reference labels exist. Do not modify their pilot observations or use
this schema change to promote machine-screened recordings into verified data.
`evidence_status=validated` means the harness's eligibility gates passed; it does
not independently certify ground truth, isolation or scientific publishability.

## D. Reporting

For each run and split, report exactly, with denominators:

- Recording level, exact keyword (primary): TP, TN, FP, FN; precision (TP/(TP+FP)), recall (TP/(TP+FN)), specificity (TN/(TN+FP)), F1, false-positive rate (FP/(FP+TN)), false-negative rate (FN/(FN+TP)). A positive counts only when its own keyword fires: "help" detected as "tulong" is an FN.
- Recording level, any distress (system level): the same metrics for "an alarm was raised", reported alongside, never in place of, the exact-keyword figures.
- Per keyword: one confusion matrix per keyword; a wrongly predicted keyword is that keyword's FP. Report how many positives fired only a wrong keyword.
- Event level: false alarm events in total and per keyword (every repeat counted, so the per-keyword counts sum to the total), and events per hour of negative audio (one negative recording can contain several false alerts).
- Per negative class: recordings, false-positive recordings, false alarm events.
- Latency: median, p90 and max, from keyword onset when annotated; otherwise labelled "from recording start".
- Recordings and distinct speakers per class and split.

Any metric whose denominator is 0 is N/A (`null` in `summary.json`), never 0%.
Mocked-engine tests (`test/test_replay_eval.py`) check the harness only and are
not accuracy measurements.
