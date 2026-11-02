# C1.55 Acoustic Validation Protocol and Evidence Readiness

**Status:** protocol review draft; no acoustic or model evaluation was run.

## Scope and decisions

This document defines a reproducible path from synthetic regression checks to future authorized acoustic, thermal, and delivery evaluation. It records existing source interfaces and protocol constraints without opening recording or model contents. It does not authorize microphone access, model inference, device interaction, alert activation, or deployment.

- **PROTOCOL READY: NO** — the measurement framework is drafted, but the exact five thesis Statements of the Problem (SOPs) were not available in the permitted documents, and approval-dependent protocol fields remain unfilled. The document is ready for supervisor/ethics review, not for data collection.
- **ACOUSTIC EVALUATION AUTHORIZED: NO** — no separate microphone/recording/model-evaluation authorization was supplied for this milestone.
- **RUNTIME INTEGRATION READY: NO** — observation mapping and replay remain disconnected from production alert paths.
- **PRODUCTION DEPLOYMENT READY: NO**.

Unknown sample sizes, measured results, confidence intervals, acceptance targets, alarm thresholds, episode boundaries, and association durations remain placeholders or explicitly unresolved. None are inferred from mocked tests or training configuration.

## A. Existing evidence inventory

| Area | Existing interface or artifact | What it establishes | Limit and evidence state |
|---|---|---|---|
| Vosk | `raspberry_pi/kws/kws_alert_dual.py`: `read_vosk_text` (939–942), `detect_tagalog_keyword` (916–932), `vosk_worker` (1080–1192) | `AcceptWaveform` selects a JSON `text` or `partial` result. The worker matches aliases in either text and submits a candidate. | The worker supplies `config["confidence"]`; it is not a Vosk utterance confidence. The worker resets after a matching candidate. The current replay event trace does not retain the raw partial/final JSON history. Runtime is source-inspected only. |
| Snowboy | `snowboy_worker` (1218–1267) | `RunDetection` returns an integer; positive values map to an index in configured keywords, zero is no detection, and `-1` is logged as an error. | The application supplies the submitted alert keyword and configured confidence; this is not a Snowboy probability score. A native detector and actual model assets were not invoked or inspected. |
| openWakeWord and VAD | `raspberry_pi/kws/audio_preprocessor.py`: `process`, `_result`, `to_metrics`; `kws_alert_dual.py` (1616–1657) | The application exposes `available`, `is_speech`, `vad_score`, `scores`, `wake_words`, `error`; score rows contain `name`, `raw_name`, `score`, and `threshold`. Detection publication occurs for score rows meeting configured thresholds while speech is active. | Thresholds and phrase names include application configuration. The score is not evidence of calibrated probability. `replay_eval.py` records model score rows, but not a complete per-frame VAD trace. No openWakeWord inference or model-file read occurred. |
| Keyword inventory | `raspberry_pi/kws/keyword_dataset_common.py` (`KEYWORDS`, `NEGATIVE_CLASSES`, `METADATA_COLUMNS`); `kws_alert_dual.py` alias mapping | The data tooling defines 17 keyword phrases and negative classes `random_speech`, `noise`, `silence`, `music`; metadata supports speaker, distance, noise condition, source, sample rate, and duration. | Freeze the exact current alias/keyword inventory and commit before a run. Preserve the project policy's 17 deployed English/Tagalog phrases. Any inventory discrepancy must be reviewed before collection; do not silently expand or normalize labels. |
| KWS replay | `raspberry_pi/kws/replay_eval.py`; tests in `test/test_replay_eval.py` | The CLI can replay WAV recordings through `kws_alert_dual.main`, isolate per recording, record posted events/scores, packet drops, pacing, resource checks, and model/config provenance. The test file uses fake engines and synthetic fixtures. | The real replay path loads actual local engines and reads WAV content when run. `EventRecorder` replaces `AlertPoster` and discards event extras; it does not exercise a real backend, Flutter delivery, physical audio, or durable end-to-end recovery. This script was not run. |
| Replay evidence policy | `docs/m3_recognition_evidence_protocol.md` | Defines preliminary versus validated mode, label-review assertions, speaker-separated development/validation/physical-holdout splits, model/config provenance, network and filesystem isolation, resource gates, and event/recording metrics. It says the existing 54 PLD recordings are preliminary-only. | The protocol's mention is not independent verification that files are present or correctly labeled. No recording files or contents were inspected. `review_status` fields are operator assertions; researchers must independently inspect and bind their supporting human-review records before publication. |
| Model training | `docs/openwakeword_distress_training_plan.md`; `docs/m3_recognition_evidence_protocol.md` | Describes model training/configuration and model provenance expected for future runs. | Training YAML target values are not measured results or thesis acceptance criteria. No model names, bytes, hashes, or inference results were collected for this task; actual installed/available asset versions remain **UNVERIFIED**. |
| Thermal recognition | `raspberry_pi/thermal/thermal_confidence.py`, `test/test_thermal_confidence.py`, `raspberry_pi/thermal/README.md` | Thermal frame scoring and thermal-model tests/documentation exist. | These do not demonstrate voice-to-thermal association, advisory reevaluation, a new critical event, or safe audible authority. No thermal sensor/model was accessed. |
| Backend and Flutter | `raspberry_pi/backend/main.py`; `test/test_alert_delivery.py`, `test/test_alert_publication.py`, Flutter alert delivery/runtime tests | Existing mocked tests cover backend idempotency/delivery and Flutter state/recovery components. | The KWS replay recorder stops at the publication boundary. Mocked component tests do not prove that a physical Flutter device receives, presents, acknowledges, or audibly plays a critical alarm. |
| Metric implementation | `raspberry_pi/kws/evaluate_keyword_models.py:12–81`, `replay_eval.py:888–960` | Existing helper computes TP/FP/TN/FN, precision/recall/specificity/FPR/FNR and an F1 value; replay adds event counts/rates and latency. | It does not emit accuracy or accuracy/F1 denominator fields. Its F1 implementation returns `null` whenever precision or recall is undefined, while the direct formula below may be defined as zero. It is not sufficient as-is for the complete C1.55 result table; an isolated postprocessor or separately reviewed evaluator update is required before a run. |
| Dependencies | `raspberry_pi/backend/requirements.txt`, `test/requirements-delivery.txt`, `replay_eval.py` imports and runtime provenance code | The backend requirements include unpinned runtime dependencies; delivery tests exactly pin FastAPI/httpx and specify a minimum `python-multipart` version. Replay dynamically imports the KWS application and records selected installed distribution versions. | No dedicated pinned KWS evaluation lockfile was found in the inspected paths. Future replay must freeze the interpreter and exact installed package/native-component provenance; the source-level requirements alone do not establish the environment. |
| Thesis/SOP source | Permitted repository documentation and thesis-document filenames under `/home/thesis` | The shared policy fixes the planned questionnaire cohort at exactly **5 IT Professionals + 25 Rescue/Safety Personnel = 30 respondents**. | No thesis manuscript containing the exact five SOP statements was found. No measurement-to-SOP mapping can responsibly be asserted until those exact statements are supplied from the approved manuscript. Respondents are not audio speakers, recordings, sessions, or trials. |

Relevant current replay details: `replay_eval.py` requires `--dataset-dir`, one of `--env-file`/`--unit`, `--noise-config`, and a new `--out-dir`; it supports `--evidence-mode preliminary|validated`, `--split dev|holdout`, `--onsets`, and `--isolation per-recording|continuous`. Validated mode requires human-review metadata assertions and withholds correctness metrics on invalid runs. `read_wav` requires uncompressed 16 kHz mono 16-bit PCM. The existing replay gap and lead-in are harness playback parameters; they are not voice/thermal association windows or emergency episode boundaries.

The replay process has Python-level network guards, offline loader flags, scratch paths, model/config hash records, engine-load checks, and resource checks. These are useful controls, but the existing protocol correctly requires an OS-enforced, network-disabled sandbox with no microphone, backend, credentials, or production data; read-only code/model/input mounts; controlled output/scratch; and OS resource limits. Python guards alone are not a security boundary.

The replay harness itself uses the Python standard library, then imports the runtime KWS module. The runtime has eager dependencies on NumPy, PyAudio, Requests, and Vosk; openWakeWord is loaded by the audio preprocessor; Snowboy is loaded through its native/SWIG binding; and the optional wav2vec2 verifier can use PyTorch/Transformers or ONNX Runtime/Transformers depending on configuration. The backend `requirements.txt` is not a pinned KWS evaluation environment, and Flutter dependencies are managed separately through its Dart package manifest/lock. Freeze the exact active dependency branch, Python/OS image, package and native versions before evaluation; presence in requirements is not evidence that a component is installed or used.

## B. Ground-truth requirements

No sample is “verified” merely because its folder or metadata says positive/negative. Before a future dataset contributes to an accuracy claim, retain an auditable, privacy-protected evidence record bound to the recording ID and content hash.

### Positive and negative labels

- Positive labels must identify the exact spoken keyword/phrase, its transcript, word onset (and offset if measured), and whether the recording is a lexical keyword trial or an approved distress-intent scenario. Lexical presence and emergency intent are separate labels.
- Use only the approved vocabulary for the primary comparison. Preserve the 17 deployed English/Tagalog phrases; a Cebuano extension needs a separately reviewed vocabulary and verified positive data.
- Negative ordinary-speech trials should include approved non-distress speech, including documented near-pairs already implicated in the matcher (for example `tulog` versus `tulong`). Also stratify real silence, environmental noise, and music where these are in scope. Digital zeros are not a substitute for recorded silence.
- The existing protocol identifies 95 Speech Commands `noise` clips as background noise rather than the defense location's environment. If retained, report them separately from environment-specific negatives.
- Do not ask participants to simulate panic, injury, or a real emergency without separate ethics/safety approval and a reviewed script. Stop a trial on participant discomfort.

### Speakers, sessions, and conditions

- Use pseudonymous `speaker_id`, `session_id`, `recording_id`, and `trial_id`; keep the identity key separate under the approved data custodian.
- Record consent form/version, collection authority, language/accent as approved, microphone/device and firmware, placement, distance, session, environment/noise condition, sample rate, encoding, duration, gain/configuration, and any exclusions. Record environmental measurements only when a suitable calibrated instrument and approved procedure exist; otherwise describe the condition without inventing a numeric value.
- Capture multiple independent speakers and sessions. Repeated utterances from one person are clustered observations, not independent participants. Split development, validation, and final holdout by speaker (and document session separation) so that one speaker cannot leak across splits. Do not tune thresholds or modify the model/configuration on holdout data.
- Freeze the recording/trial allocation and sample-size rationale before collection: `[SPEAKERS / SESSIONS / TRIALS BY CLASS: NOT YET APPROVED]`. Do not infer a sample size from the 30 questionnaire respondents.

### Annotation and adjudication

- At least one trained human annotator must listen to each sample under the approved procedure and record exact words, keyword onset/offset where measurable, speech activity, label scope, and uncertainty. A second independent reviewer adjudicates disagreements; preserve both initial annotations and the adjudication result.
- Store `review_status`, `reviewed_label`, `review_method`, and a nonempty, access-controlled `review_evidence` reference, as required by the validated replay schema. Bind the evidence to the pseudonymous recording ID and SHA-256. Keep raw audio, consent, identity, and review records access-controlled and outside code, reports, and public backups.
- Labels may be `ambiguous`/`unresolved`; exclude these from primary binary denominators, report their count and reasons, and include them only in a separately predeclared sensitivity analysis. Never recode missing/ambiguous ground truth as negative.
- Freeze class definitions, transcript convention, onset convention, reviewer/adjudicator workflow, disagreement handling, exclusion rules, and any confidence-interval method before evaluation. Unknown values stay `[NOT YET APPROVED]` until the investigator/supervisor approves them.

## C. Recognition validation methodology

1. **Preregister the question and unit.** Obtain exact SOP wording, select primary outcomes, specify target population/conditions, inclusion/exclusion rules, sample-size rationale, confidence-interval method, and acceptance decision owner before collection. Separate research hypotheses from safety release gates.
2. **Freeze the system.** Record source HEAD and dirty patch hash, alias/keyword manifest, environment/config hash, preprocessing/noise settings, Python and OS, engine/package/native versions, model file manifest hashes, sample-rate/chunking settings, and hardware. Do not tune during a scored holdout run. Missing model/component provenance invalidates the run as evidence.
3. **Validate data first.** Check consent and label provenance, format, duration, path safety, content hash, speaker/session split, duplicate recordings, missing metadata, and that no holdout speaker appears in development or validation. Do not replace originals during format conversion; use separately hashed copies if conversion is authorized.
4. **Run synthetic software regression separately.** Use fake engines and deterministic observations for parser mappings, revision/cancellation, missing scores, engine failure, duplicate identity, thermal transitions, backend replay, and Flutter state. Label these results *synthetic regression evidence*. They are not included in acoustic confusion matrices or system performance estimates.
5. **Run the fixed acoustic replay only after authorization.** On an isolated evaluation host, run the existing `raspberry_pi/kws/replay_eval.py` at real-time speed and with required engines, read-only approved inputs/models, network disabled, isolated scratch outputs, frozen config, and resource preflight/watchdog enabled. Preserve `summary.json`, `events.jsonl`, predictions/detections CSV, per-run manifest, and abort/preflight records. Do not use `--skip-resource-checks` for evidence. Stop on missing engine, incomplete provenance, packet drops, invalid evidence, worker leakage, resource abort, or changed input/config/model hash.
6. **Use development data for diagnosis only.** Any code/config change creates a new source/config identity. Re-run development/validation as authorized; leave final holdout sealed until the candidate is fixed. Then run the holdout once for the declared comparison. Report every attempted run, including invalid/aborted runs, and why it was excluded.
7. **Report paired comparisons.** For a before/after change, use the same authorized recordings, labels, splits, devices, and fixed environment. Keep per-recording predictions to support paired analysis. Do not present a numerical improvement unless denominators, uncertainty, and valid evidence gates are included.

### Required collection strata

Predefine and report, without assuming counts, each approved keyword; ordinary speech/near-pairs; real silence; environmental noise; music if in scope; distance/orientation; device and placement; quiet/noisy environment; and any approved speech style or overlap condition. Record unavailable strata as unavailable rather than synthesizing favorable coverage.

## D. Confusion matrix and measurement definitions

For a declared binary target and evaluation unit, let `positive` mean the reference label is present and `predicted positive` mean the system emitted the predeclared target detection for that unit:

| Reference / prediction | Predicted positive | Predicted negative |
|---|---:|---:|
| Reference positive | TP | FN |
| Reference negative | FP | TN |

Use these definitions exactly:

| Measure | Formula | Denominator / rule |
|---|---|---|
| Accuracy | `(TP + TN) / (TP + FP + TN + FN)` | N/A if total is zero. |
| Precision (positive predictive value) | `TP / (TP + FP)` | N/A if `TP + FP = 0`. |
| Recall / sensitivity | `TP / (TP + FN)` | N/A if `TP + FN = 0`. |
| Specificity | `TN / (TN + FP)` | N/A if `TN + FP = 0`. |
| F1 | `2 * TP / (2 * TP + FP + FN)` | N/A if denominator is zero. |
| False-positive rate | `FP / (FP + TN)` | N/A if `FP + TN = 0`. |
| False-negative rate | `FN / (FN + TP)` | N/A if `FN + TP = 0`. |

The direct F1 formula is authoritative. For example, if `TP=0, FP=0, FN>0`, precision is N/A but F1 is `0` because `2TP + FP + FN > 0`; similarly F1 is `0` when `TP=0, FP>0, FN=0`. The current `compute_binary_metrics` implementation instead returns null if precision or recall is null, so its F1 field does not implement this protocol's edge-case rule. It also omits accuracy and explicit accuracy/F1 denominators; it does return denominators for several other rates. Before any authorized scored run, an isolated analysis implementation must produce the table below from saved predictions and be checked against hand-calculated edge cases. Do not change the live detector or use current summary output as if it contained these required fields.

Report integer counts and each denominator beside every rate. Use `N/A` in tables and `null` in JSON when a denominator is zero or required labels/timestamps are unavailable; never replace undefined with zero. Keep missing/unavailable engine output distinct from a negative result. Report exclusions and label-missing counts separately.

### Units and valid interpretations

| Unit | Operational definition | Metrics that are meaningful | Independence caveat |
|---|---|---|---|
| Frame | A fixed VAD/thermal frame under the frozen window/hop and annotation convention. The convention is `[TO BE PREREGISTERED]`. | TP/FP/TN/FN, accuracy, precision, recall, specificity, F1, FPR/FNR for frame classification. | Adjacent frames are strongly dependent. Do not treat frame count as independent participant/sample count. The present replay output does not emit all VAD frame decisions; an isolated harness trace extension is required before VAD metrics can be computed. |
| Utterance/recording | One predeclared recording/trial with one reference class and an exact target keyword. A recording is counted once for recording-level metrics, regardless of repeated events. | Binary metrics for VAD utterance-level activity if labels exist; exact-keyword and any-distress matrices; first-correct-keyword latency. | Multiple utterances per speaker/session are clustered. Exact-keyword and any-distress results are separate: a wrong keyword is a miss for the expected keyword and a false positive for the emitted keyword. |
| Speaker/session | A grouping/stratum of utterances from a pseudonymous speaker/session. | Counts per stratum and macro-averaged utterance metrics may be reported if declared. | Do not silently convert a speaker into a single positive/negative sample. Any speaker-level binary rule must be defined before data collection. Use speaker/session-clustered uncertainty analysis. |
| Alert episode/trial | An independently ground-truthed scripted trial or predeclared event unit, not a time window inferred after looking at alerts. | Event-level false alert count/rate, duplicate alert count, escalation/delivery outcomes, and latency when clocks/identity are available. | Emergency episode boundary and rearm logic are **UNRESOLVED**. Until approved, use scripted trial IDs for controlled tests; do not merge/split events by an invented silence timeout. |

For each exact keyword, run one-versus-rest classification. A positive sample for keyword `help` that fires only `tulong` is an FN for `help` and an FP for `tulong`. Also report an any-distress system-level matrix, but never substitute it for exact-keyword results. The existing replay `summarize` already follows these separate conventions at recording level.

### Required results table headers

**Recording/frame confusion table:**

`run_id, split, unit, target, class_or_condition, n_reference_positive, n_reference_negative, TP, FP, TN, FN, accuracy, accuracy_denominator, precision, precision_denominator, recall, recall_denominator, specificity, specificity_denominator, F1, F1_denominator, FPR, FPR_denominator, FNR, FNR_denominator, CI_method, CI_level, CI_lower, CI_upper, missing_ground_truth_n, excluded_n, exclusion_reasons`

**Latency table:**

`run_id, split, latency_type, target, recording_or_trial_id, reference_onset_timestamp, detection_timestamp, clock_domain, latency_ms, timing_source, timestamp_valid, missing_reason`

Report detection latency as `t(first correct target detection) - t(reference onset)` only when both times share a validated clock/timebase. If onset is absent, report onset-based latency `N/A`; the existing replay's separate “from recording start” measure may be reported as such, never relabeled onset latency. For streaming/delivery, retain capture, decision, publish, backend receive/persist, client receive, presentation, acknowledgement, and physical audio timestamps separately. Do not subtract timestamps from different clock domains without a measured synchronization mapping.

For a nonempty latency vector, report count, median, p90, and maximum. To match the current replay implementation, p90 is the sorted order statistic at index `floor(0.9 * (n - 1))`; freeze this convention for paired comparisons. For an empty vector, report count `0`, median/p90/max `N/A`, and the reason (no detection, no onset, invalid clock mapping, or no eligible trials).

**Event and delivery table:**

`run_id, trial_id, reference_episode_id, observation_ids, candidate_ids, original_advisory_event_id, critical_event_id, backend_event_id, event_classification, publish_attempt_n, unique_logical_event_n, duplicate_delivery_n, replay_attempt_n, thermal_observation_id, thermal_positive_reference, t_thermal, t_critical_accepted, escalation_latency_ms, backend_persisted, client_received, Flutter_state, acknowledged, audible_output_verified, clock_domain, missing_reason`

Count duplicate alerts against predeclared trial/episode ground truth. Distinguish retrying the same immutable backend event ID (one logical event, multiple attempts) from emitting multiple event IDs for one reference episode. Report both counts; do not infer an episode boundary from retries. Advisory-to-critical escalation latency is `t(accepted distinct critical-classification event) - t(associated positive thermal observation)` only when both observations are explicitly linked by an approved rule and timestamps share a clock. If identity or timestamp is absent, report N/A and the reason.

Use these exact event counts: `same_id_retry_duplicates = sum(max(0, attempts_for_each_immutable_event_id - 1))`; `logical_episode_duplicates = sum(max(0, accepted_distinct_event_ids_mapped_to_reference_episode - approved_expected_logical_events_for_that_episode))`. The latter is N/A until an approved policy defines the expected logical event count and mapping from event to reference episode. Report raw attempts and unique IDs even when it is N/A. For false-alarm event rate, `false_alarm_events_per_hour = false_alarm_event_count / eligible_negative_audio_seconds * 3600`; it is N/A when eligible negative exposure is zero or unavailable. These are different measures: retry duplicates do not automatically count as new logical emergency alerts.

**Run/evidence manifest:**

`run_id, start_utc, finish_utc, source_head, dirty_patch_sha256, engine_name, engine_version, native_component_version, model_manifest_sha256, config_sha256, vocabulary_sha256, dataset_manifest_sha256, split_manifest_sha256, preprocessing_version, noise_config_sha256, python_version, OS_image, hardware_id_pseudonym, sample_rate, chunk_and_frame_config, replay_speed, isolation_mode, network_denied, devices_denied, input_mount_read_only, model_mount_read_only, resource_limits, resource_preflight, engine_load_status, packet_drops, worker_shutdown_status, evidence_mode, valid_as_evidence, invalid_reasons, reviewer_id_pseudonym`

## E. False-alarm and missed-distress protocol

- **False alarm:** a system distress alert emitted for a human-adjudicated negative trial. Report false-positive recordings and false-alarm events separately. Report event count by negative class and per hour of negative audio, using total eligible negative duration as the denominator. One recording may contain multiple events; neither metric replaces the other.
- **Missed distress:** no detection of the exact expected keyword in a verified positive trial. Also report any-distress detection and wrong-keyword-only cases. A wrong distress phrase does not count as an exact-keyword hit.
- **Ordinary speech:** include the near-pairs in existing remediation documentation and other approved natural speech; annotate literal phrase presence and emergency intent separately. Ordinary context containing the literal keyword is not automatically a lexical negative. Human adjudicators must apply the preregistered label scope.
- **Silence/noise/music:** real room silence means nobody speaking, not digital zero samples. Keep environmental noise collected at the authorized test location distinct from downloaded/background corpora. Document the condition and exposure duration.
- **Thresholds and operating point:** freeze the deployed model/config thresholds for the baseline and holdout. If a threshold is a study variable, select it on development data, preregister the selection method, and report the full curve/operating point. Existing training-plan targets and helper defaults are not evidence of accepted performance or alarm authority.
- **Uncertainty:** report an approved interval method and level `[TO BE PREREGISTERED]`; for repeated utterances, account for speaker/session clustering. Do not present a narrow interval from treating correlated frames or repeated utterances as independent.

## F. Partial/final revision assessment

The current Vosk worker submits exact alias matches from both `text` and `partial` fields, then resets after a matched candidate. The C1.54 synthetic mapper can represent the supplied final/partial status and preserve raw JSON, but it is not wired to the replay harness or service. Current replay event logging does not expose the sequence of hypotheses that led to a publication.

Before acoustic measurement, extend only the disconnected evaluation trace (not runtime alarm behavior) to capture a monotonic/input-audio timestamp, input packet sequence, raw hypothesis payload, `text` versus `partial` source field, recognizer candidate/session identity, revision order, `AcceptWaveform` final/partial result, explicit `Reset()` calls and reasons, capture gaps/queue drops, engine failure/recovery boundaries, and publication decision receipt for each input chunk. Keep a copy of the original input and trace hashes under approved access controls. The trace must not add or change publication, suppression, or alarm authority.

The current worker calls `recognizer.Reset()` at `kws_alert_dual.py:1190` immediately after submitting a matched candidate. Therefore, if a partial match triggers this path, a later hypothesis after that reset is a new recognizer context, not a final revision of the prior candidate. Report that same-candidate partial-to-final transition as unavailable for the current worker path; do not join post-reset text to the earlier candidate. Measuring a counterfactual no-reset recognizer would be a separate, evaluation-only design and cannot be presented as the current runtime's behavior.

Assess these cases as separate evidence questions:

| Scenario | Required observation | Interpretation |
|---|---|---|
| Partial `tulong` later revised to final `tulog` | Ordered partial and final payloads, exact ground-truth transcript/onset, any event emitted at each stage | Measures revision and false-publication behavior. Does not decide whether a provisional partial may authorize an alarm. |
| Genuine partial-only `tulong` | Authorized sample ends before recognizer finalization; retain partial observations and determine whether the lexical keyword was spoken | Measures partial recognition coverage. Alarm authority remains **UNRESOLVED** pending a separately approved safety policy and human-factors evidence. |
| Final distress hypothesis | Full utterance, final payload, expected keyword and independent engine observations | Measures final exact-keyword behavior and end-to-end software mapping; does not prove emergency intent. |
| Independent Snowboy/openWakeWord help during ordinary Vosk text | Preserve each engine observation separately and time-order them in the trace | Verify one source cannot cancel another source's evidence; alarm episode classification remains separate. |

Freeze engine versions, parser, aliases, config, and acoustic conditions for the primary run. Report partial-only, revised, final, and absent hypotheses separately, with denominators and missing traces. Do not report recognition latency from a recognizer emission when the ground-truth onset or clock mapping is unavailable.

## G. Thermal escalation and alert delivery requirements

### Thermal and episode evidence

Thermal model frame classification and voice recognition require their own ground truth and confusion matrices. Combined escalation evaluation additionally requires a controlled trial manifest with explicit `trial_id`, `voice_observation_id`, `thermal_observation_id`, advisory event ID, and any distinct critical-classification event ID. Preserve the original advisory identity; a later escalation, if authorized by a reviewed policy, must be traceable as a distinct immutable event. Replay of an event ID must remain idempotent.

Run synthetic software tests first for positive thermal evidence after an advisory, unchanged/replayed thermal evidence, missing thermal observations, concurrent orderings, temporary backend disconnection, and restart. These test event contracts only. A live thermal/voice association window, episode end/rearm condition, critical authority rule, and treatment of conflicting evidence are **UNRESOLVED**. No time window or new event authority is selected here.

Actual controlled emergency-scenario validation requires separate ethics/safety approval, a reviewed non-harmful scenario script, consenting participants where applicable, a calibrated/identified thermal device, isolated test backend/storage, a dedicated test client, and a safe alarm-output plan. Never simulate an actual emergency response or contact rescue services as part of a test.

### Delivery, interruption, Flutter, and restart

Test delivery in an isolated sandbox with a disposable backend database and test-only Flutter client. Record separately: KWS publication attempt; backend receive, validation, persist and idempotency outcome; polling/WebSocket/replay; client receipt; Flutter critical/advisory state; acknowledgement; and physical audio output if it is separately authorized and measured. An application-level presented/acknowledged state is not proof that a siren was audible.

Inject disconnection before and after backend persistence, retry the same event ID, retry conflicting payloads, restart backend and client, and compare recovered logical events and acknowledgements to the trial manifest. Require no lost accepted event, no duplicate logical event, and no authority upgrade by reusing an immutable advisory ID under the approved event contract. Any test requiring audible critical output is BLOCKED until the authority rule, test device, output isolation, and explicit approval exist.

## H. Thesis SOP alignment

No permitted thesis document with the exact wording of the five SOPs was located. The rows below are an explicit gap register, not invented or paraphrased SOPs.

| Thesis item | Exact approved wording | Candidate measurements assignable only after text is available | Status |
|---|---|---|---|
| SOP 1 | **NOT FOUND — exact manuscript wording required** | `[UNMAPPED]` | BLOCKED |
| SOP 2 | **NOT FOUND — exact manuscript wording required** | `[UNMAPPED]` | BLOCKED |
| SOP 3 | **NOT FOUND — exact manuscript wording required** | `[UNMAPPED]` | BLOCKED |
| SOP 4 | **NOT FOUND — exact manuscript wording required** | `[UNMAPPED]` | BLOCKED |
| SOP 5 | **NOT FOUND — exact manuscript wording required** | `[UNMAPPED]` | BLOCKED |

Once the exact approved statements are available, map each measure to the relevant SOP verbatim and cite its planned table/result. Do not alter SOP wording to fit available metrics.

Keep the planned system-evaluation questionnaire cohort exactly **5 IT Professionals**, **25 Rescue/Safety Personnel**, **30 respondents total**. Questionnaire design, respondent eligibility, consent, and results are a distinct human-participant evaluation. Do not use those 30 respondents as the number of audio speakers, acoustic trials, independent sessions, or thermal scenes. No questionnaire result is reported in C1.55.

Maintain three separate evidence classes in the thesis:

1. **Engineering regression evidence:** mocked/unit/integration tests; report test count and scope, never accuracy or acoustic performance.
2. **System performance evidence:** authorized, human-labeled recordings/thermal trials and real system measurements with denominator, provenance, uncertainty, and test conditions.
3. **System evaluation questionnaire:** the fixed 30-person cohort and its instrument/statistical analysis, reported separately from technical trials.

## I. Authorization and execution readiness

| Gate | Required before the corresponding activity | Current state |
|---|---|---|
| SOP and preregistration | Approved exact five SOP statements; supervisor-approved mapping; study question, sample-size rationale, conditions, exclusions, analysis and decision criteria frozen | **BLOCKED** — SOP text not found; values/criteria not approved |
| Human participants and audio | Applicable institutional/ethics review, informed consent, privacy/storage/retention plan, non-harmful script, approved operator and recording location | **BLOCKED** — no authorization in this task |
| Existing private audio | Dataset owner authorization, consent/label provenance, allowed-use/license confirmation, hashes and human adjudication | **BLOCKED** — no recording contents inspected; existing documentation calls the 54 PLD set preliminary-only |
| Model execution | Authorized local model copies and license, exact version/hash manifest, no network access or hub download, immutable read-only mount | **BLOCKED** — no assets read or inference run; availability/provenance unverified |
| Hardware | Isolated test Pi/ReSpeaker/thermal hardware or approved equivalent; no production service/device ownership conflict; no microphone/sensor access until specifically authorized | **BLOCKED** |
| OS/resource isolation | Unprivileged sandbox; network disabled; no audio devices/backend/credentials/production data; read-only source/model/input; isolated output; OS-enforced memory/CPU limits; verified host and cgroup headroom; thermal/health monitoring | **BLOCKED** — no sandbox or resource execution configured for real evaluation |
| Replay command and evidence | Freeze Python environment; use `raspberry_pi/kws/replay_eval.py` with `--evidence-mode validated`, required engines, approved `--env-file` or `--unit`, frozen `--noise-config`, authorized `--dataset-dir`, annotated `--onsets`, speaker-separated split, and new empty `--out-dir`; real-time speed; resource checks enabled | **BLOCKED** — command not run; values/paths must be supplied in an approved run manifest |
| Instrumentation gaps | Add isolated trace collection for VAD frame decisions and Vosk hypothesis revision history; verify trace completeness with synthetic tests before real data | **BLOCKED** — current replay records OWW model scores/events but not complete VAD frames/raw Vosk revisions |
| Backend/Flutter | Disposable backend store and isolated test client, test credentials, no production route; policy for event identity and authority approved; safe output mute/measurement plan | **BLOCKED** — KWS replay substitutes an event recorder and stops before live delivery |
| Independent review | Reviewer receives frozen protocol, anonymized manifests/results, exact scripts/config, exclusion log, and analysis; review methods and conclusions before thesis inclusion | **BLOCKED** — protocol review requested for this milestone; no experiment result exists |

Exact future evaluation entry points are the existing `raspberry_pi/kws/replay_eval.py` and `raspberry_pi/kws/evaluate_keyword_models.py`; synthetic replay coverage is `test/test_replay_eval.py`. The latter calculator consumes prediction files and computes binary metrics; it does not validate labels or create evidence, and it does not yet satisfy this protocol's full metric table/F1 edge rules. A separately reviewed, isolated postprocessing step is therefore a pre-run gate. Backend and Flutter software checks use their existing targeted test suites under the disposable test environment. No script in this protocol was invoked against recordings, models, production services, or production storage.

Resource safety is a hard stop: use the replay script's preflight and watchdog without `--skip-resource-checks`; independently verify host-side limits and pressure because a container may not see ancestor limits. Do not change swap, Docker, boot, system service, or filesystem settings to make a run pass. A failed or unavailable resource reading means no run. Record every preflight/abort artifact and do not report performance metrics from an aborted or invalid run.

Data handling: store consent and identity records separately from pseudonymous recordings; encrypt/access-control the approved data store; restrict copies and retention; log access; do not place raw audio, participant identity, credentials, model assets, or production alerts in Git, this report, or general backups. Keep report outputs limited to aggregate or pseudonymous evidence. Honor dataset licenses and the project's restrictions on private audio and third-party sharing.

## J. Safety acceptance gates and next authorized experiment

| Gate | Evidence required | Pass/fail rule | Current state |
|---|---|---|---|
| Partial `tulong` revised to `tulog` | Authorized recording, human transcript/onset, ordered raw Vosk partial/final trace, publication/event trace | Every hypothesis and revision is traceable; no evidence is silently overwritten. Alarm action is not assessed until provisional authority policy is approved. | BLOCKED: no audio/trace; authority UNRESOLVED |
| Genuine partial-only distress | Consent-cleared positive trial ending without a final result, exact transcript/onset and partial trace | Report exact-keyword detection separately from any alarm action. No pass criterion for provisional alarm authority exists. | BLOCKED: no authorized sample; authority UNRESOLVED |
| Independent Snowboy/openWakeWord help | Per-engine observations and event order with Vosk ordinary text; synthetic regressions, then authorized audio | One engine's revision/failure cannot erase another engine's evidence; all sources and missing scores remain explicit. | Synthetic contract covered in prior test-only work; acoustic validation BLOCKED |
| Repeated scores / duplicate alerts | Score trace, stable observation/event IDs, scripted trial ID, backend receive/replay ledger | Retries of same immutable ID stay one logical event; extra distinct event IDs are counted. Episode-level duplicate classification requires a preregistered trial/episode rule. | Software mock tests exist; actual episode rule UNRESOLVED |
| Thermal-positive escalation | Thermal reference labels, thermal observation and original advisory IDs, approved distinct critical event, common-clock timestamps | Escalation is attributable to explicit evidence; unchanged/replayed frames do not fabricate logical events under the approved contract. No association duration or critical authority inferred. | BLOCKED: no authorized scenario; association/authority UNRESOLVED |
| Missing recognizer output | Explicit unavailable/missing/failure records and input-trial ledger | Missing output is never counted as a true negative; report missing count and cause. | Synthetic contract only; real engine-failure behavior not evaluated |
| Engine failure/recovery | Versioned generation/session trace, failure/restart injection in sandbox, retained evidence ledger | Failure differs from healthy no-detection; recovery starts a traceable generation and does not erase earlier observations. | Synthetic tests exist; hardware reliability BLOCKED |
| Backend interruption/replay | Disposable store/network fault injection; event IDs, retries, persisted and acknowledged records | Same ID is idempotent; delivery/recovery outcome is traceable; no classification upgrade by mutating immutable identity. | Existing mocked tests only; end-to-end test BLOCKED |
| Flutter critical presentation/acknowledgement | Dedicated test client, isolated backend, approved test alarm policy; receipt/state/ack logs; physical output check only if approved | Separate client receipt, presentation, acknowledgement, and audible verification. UI state alone is not audible proof. | BLOCKED: no approved authority/output scenario |
| Restart recovery | Backend and client restart at preregistered points; disposable persistent store and replay log | Accepted logical events and acknowledgements recover without loss or duplication; unresolved items remain visibly unresolved and do not become critical by recovery. | Component mocks exist; integrated recovery BLOCKED |

Evidence that could inform **provisional alarm authority** includes independently adjudicated partial-only positives, ordinary-speech near-pair negatives, revision sequences, false activation consequences, missed distress consequences, and controlled human-factors review. It cannot be decided from recognition recall alone.

Evidence that could inform **episode boundaries/rearming** includes controlled repeated utterances, pauses, distinct speaker/session events, overlapping independent engines, and repeated detector scores, with raw timestamps and ground-truth trial identities. It must be assessed against operational consequences and a reviewed policy; this protocol assigns no silence timeout.

Evidence that could inform **voice-to-thermal association duration** includes synchronized, ground-truth voice and thermal events across controlled positive/negative sequences and relevant conditions, with explicit competing/crossing events and latency distributions. A duration is a policy decision, not something inferred from current synthetic fixtures.

Evidence that could inform **new critical-event authorization** includes validated independent evidence, event identity/idempotency semantics, controlled replay/restart/concurrency tests, and approved emergency safety/human-factors review. A new event ID alone is not evidence of a new emergency.

### Recommended next authorized experiment

First obtain the approved thesis manuscript's exact five SOP statements and supervisor/ethics decisions. Complete the preregistration fields (sample-size rationale, consent/data handling, label/adjudication procedure, conditions/splits, confidence-interval method, inclusion/exclusion rules, and outcome criteria) without using unseen holdout results to tune the system. Add and synthetic-test **evaluation-only** VAD-frame and Vosk-revision trace collection; keep it disconnected from runtime publication. Then seek separate authorization for a small, supervised development-only acoustic pilot on an isolated non-production machine using consented participants, the frozen 17-phrase vocabulary, approved ordinary-speech negatives, and authorized model copies. The pilot must be explicitly labeled feasibility/label-quality work, not final performance evidence; no recording count or pass threshold is set here. Only after the pilot and independent protocol review should a separately authorized held-out evaluation be scheduled.

## K. C1.55 preservation and verification record

### Prior chain and source preservation

The sealed chain was verified before this report was created:

| Backup | Verified contents |
|---|---|
| `C1_48_R_20261102T011740.344081Z` | 41 checksummed artifacts; original archive 17/17; byte-exact raw recovery 17/17; tracked patch recovery 3/3. Manifest SHA-256 `ee49731c9348f23b65d5df6d67871075bc7a15ca1206f57d3922428ebd4b0772`. |
| `C1_51_incremental_20261102T014123.101687Z` | 8 checksums; C1.50 additions 2/2 archived and restored. Manifest SHA-256 `c217a060934c96c87bd15fced50c0ede3d744f37d67c3c5dee3928b1c772600a`. |
| `C1_52_incremental_20261102T020020.894305Z` | 10 checksums; C1.51 additions 3/3 archived and restored. Manifest SHA-256 `aace26d4a970bbcf7fdd7a6698b9c413c1ef4db6ccadddc050d1c329ce49866d`. |
| `C1_53_incremental_20261102T021726.563255Z` | 8 checksums; C1.52 report 1/1 archived and restored. Manifest SHA-256 `1b154f50c5e10a973ae7b1d19494b30c5a31a78914f398526c5f235a6e35c243`. |
| `C1_54_incremental_20261102T023613.561649Z` | 10 checksums; C1.53 additions 3/3 archived and restored. Manifest SHA-256 `430510051aac14291e26ac1ca7ad8a12603b328f2cfd321058a3930f7e1ab401`. |
| `C1_54_learning_20261102T025752.403628Z` | 9 checksums plus detached checksum of `SHA256SUMS`; C1.54 source files 3/3 exact in archive and recovery. Manifest SHA-256 `51891e6ded8a1b3fa469cb53675cde38d73fd7704275c2a6d2fa1c5d4b12baf5`. |

All 29 unique C1.43–C1.54 source artifacts match their recorded size, SHA-256, and mode. A new incremental C1.54 source backup was created before inspection/writing:

`/home/thesis/offline-work-backups/C1_55_preflight_C1_54_20261102T063454.436832Z`

It contains an 8-entry `SHA256SUMS`, detached manifest checksum `cf75043f3b7cdfcca0359a408d918ce0fed3969cc9b3675a2a9e270f0c79fc4f`, archive `C1_54-artifacts.tar`, inventory, checkout snapshot, restore instructions, and byte-exact `verified-recovery/` copies of all three C1.54 files. The archive and recovery bytes/modes matched 3/3.

### Access and repository boundaries

- No recording was opened, decoded, played, copied, or content-inspected. No model asset was opened, hashed, loaded, or inferred. Only source code, safe documentation, filenames, schemas, test names, and backup metadata were read.
- No production database or alert history was accessed. No production/evaluation file was written. No service, hardware, microphone, Docker, swap, boot, or filesystem setting was changed.
- Baseline offline branch/HEAD: `development/c1-43-c1-47-recognition-safety` at `8a44f109fae8adb4b7daa833c15548b56ccd2452`. Evaluation is clean at the same HEAD. Production tracked files were clean at its independent `main` HEAD `1a5c3095a27421cb4c667ee6caed14169729e774`; its pre-existing untracked status was left untouched. The offline source tree contained the same 29 artifacts as the verified chain before this report; no application runtime file was edited.
- No tests or evaluation scripts were run in C1.55. C1.54's prior recorded result is 333 mocked combined tests passed, 25 focused mapping tests passed, with no remaining material reviewer finding. These remain software-only evidence, not acoustic measurements.
- A separate read-only protocol reviewer found and independently reproduced the F1 edge-case mismatch in the existing helper, corrected dependency wording for `python-multipart`, and identified the Vosk reset/capture-gap trace limitation. Those points are addressed above; the reviewer found no remaining material issue and confirmed the cited backup-manifest hashes. The reviewer did not inspect audio/model contents, access production storage, run replay/inference/tests, or modify files.
- No Git staging, commit, push, fetch, pull, merge, rebase, reset, or clean was performed.

