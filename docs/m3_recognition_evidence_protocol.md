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

```bash
~/kws-env/bin/python raspberry_pi/kws/replay_eval.py \
  --dataset-dir dataset/audio/keyword_dataset \
  --env-file ~/kws-effective-YYYYMMDD.env \
  --onsets dataset/audio/keyword_dataset/onsets.csv \
  --out-dir build/kws-replay/baseline-dev
```

- Use `--isolation per-recording` (the default) for independent samples.
- `--require-engines` defaults to all three engines; never disable it for reported numbers.
- Report only runs whose `summary.json` has `"valid_as_evidence": true`.
- Report the run's commit, configuration and model checksums with the numbers (all in `summary.json` under `run`).

## D. Reporting

For each run and split, report exactly, with denominators:

- Recording level: TP, TN, FP, FN; precision (TP/(TP+FP)), recall (TP/(TP+FN)), specificity (TN/(TN+FP)), F1, false-positive rate (FP/(FP+TN)), false-negative rate (FN/(FN+TP)).
- Event level: false alarm events and events per hour of negative audio (one negative recording can contain several false alerts).
- Per negative class: recordings, false-positive recordings, false alarm events.
- Latency: median, p90 and max, from keyword onset when annotated; otherwise labelled "from recording start".
- Recordings and distinct speakers per class and split.

Any metric whose denominator is 0 is N/A (`null` in `summary.json`), never 0%.
Mocked-engine tests (`test/test_replay_eval.py`) check the harness only and are
not accuracy measurements.
