# C1.57 Acoustic Evaluation Results — BLOCKED

## A. Authorization and readiness decision

**Actual acoustic evaluation is BLOCKED before data access or inference.** The C1.57 instruction authorizes execution only where the existing protocol's gates pass. It supplies no dataset identifier/path or dataset-specific permission, no verified reference-label evidence, and no approved isolated execution environment. In particular it does not grant access to restricted PLD recordings. No dataset was selected or opened to look for permission or labels.

The researcher confirmed in the C1.57 instruction that the approved SOP1 wording is **“adaptive thermal thresholding.”** This confirmation is recorded as researcher-provided approval information; it resolves the earlier SOP1 phrase conflict for this task without reopening SOP alignment or claiming independent access to the approved manuscript. It does not authorize a recording dataset or establish ground truth/resources. C1.55 and C1.56 are preserved as historical reports.

| Outstanding gate | Evidence checked | Decision / exact missing prerequisite |
|---|---|---|
| Specific dataset permission | Current instruction and C1.55 I / C1.56 L | **BLOCKED:** no dataset/version/path and authorized subset identified; no dataset-owner permission covering reading/decoding/replay/model processing, applicable consent/license/use constraints or data-management scope supplied. PLD is explicitly not automatically authorized. |
| Human-verified ground truth | C1.55 B/I and C1.56 F/L | **NOT VERIFIED:** no approved per-recording human-reviewed labels/transcripts, adjudication references, speaker/session groups or onset annotations supplied for a selected dataset. Existing reports' references to preliminary recordings are not verified labels. |
| Approved environment | C1.55 I and current instruction | **NOT SPECIFIED:** no approved host/device, sandbox launcher/isolation evidence, read-only authorized input/model mounts, network/device denial, output/scratch paths, frozen configuration or dependency/model manifest designated for this run. |
| Resource and service isolation | C1.55 resource requirements | **NOT VERIFIED:** no approved environment in which to verify host/cgroup headroom, hard memory/CPU limits, thermal health, watchdog or absence of unsafe concurrency with production. No claim is made that the current host is unsafe or that a resource check passed. Resource preflight was not invoked after the earlier authorization stop. |
| Replay and metrics | C1.55 A/F/I and C1.56 F/L; replay script presence | Existing `raspberry_pi/kws/replay_eval.py` is present. Documented VAD/revision-trace and F1/accuracy postprocessing gaps remain; no separately verified acoustic analysis outputs exist. These are additional readiness limitations, not the first authorization blocker. |

All authorized documentation and repository checks were completed. Experiment execution stopped at the missing dataset permission gate. The remaining gates describe missing evidence; they were not silently waived or claimed to pass.

## B. Dataset and ground-truth provenance

| Field | C1.57 record |
|---|---|
| Authorized dataset / version / subset / path | NOT SPECIFIED |
| Dataset owner permission and consent/license evidence | NOT SUPPLIED |
| Recording content/hash manifest | NOT ACCESSED / NOT GENERATED |
| Human reference labels, transcript and review/adjudication record | NOT SUPPLIED / NOT VERIFIED |
| Speaker/session grouping, split and trial allocation | NOT SUPPLIED |
| Keyword onset / VAD activity reference timestamps | NOT SUPPLIED |
| Noise conditions, distances, devices and sample format | NOT VERIFIED |
| Acoustic sample count available for valid analysis | [NOT MEASURED] |

No recording contents, private annotation/consent records or model assets were opened, decoded, played, copied, hashed or inferred. No filesystem search of recording directories was used to substitute existence for authorization. No acoustic ground-truth claim is made. References in prior reports to preliminary PLD recordings do not change this decision.

## C. Exact evaluation environment

No acoustic evaluation environment was approved, initialized or used. The following are repository contexts used for safe report/status inspection, not an acoustic execution configuration:

| Context | Path / state |
|---|---|
| Development | `/var/tmp/Project_Pi_C1_43_alarm_fix` |
| Development branch / HEAD | `development/c1-43-c1-47-recognition-safety` / `8a44f109fae8adb4b7daa833c15548b56ccd2452` |
| Evaluation baseline | `/var/tmp/Project_Pi_M3_eval`, `main`, HEAD `8a44f109fae8adb4b7daa833c15548b56ccd2452` |
| Production | `/home/thesis/Project_Pi`, `main`, HEAD `1a5c3095a27421cb4c667ee6caed14169729e774` |
| Actual evaluation host/device and OS | NOT DESIGNATED |
| Evaluation Python/dependencies/native libraries | NOT FROZEN OR LOADED |
| Authorized model versions/checksums/licenses | NOT VERIFIED; no model contents read |
| Environment/config/noise settings snapshots | NOT DESIGNATED for a run |
| OS network/device/filesystem isolation | NOT VERIFIED for a run |
| Host/cgroup headroom, memory/CPU limits, thermal health | NOT ASSESSED for an acoustic run |
| Live-service concurrency safety | NOT ESTABLISHED; no inference started |

No inference command, microphone/thermal access, service query/control, sandbox/Docker configuration or swap/boot change was performed. An existing Git worktree is not evidence of resource or service isolation.

## D. Executed evaluation procedures

Executed only: read C1.55/C1.56 and applicable policy; assess the five outstanding gates against current authorization; confirm existing replay-script presence without importing it; compare prior development-file hashes and Git state; write and verify this blocked-results report.

Not executed: WAV inspection/decoding, listening, label review of private records, model hashing/loading/inference, replay, VAD/KWS acoustic trials, live capture, thermal/system scenarios, production backend calls or alarm activation. No acoustic run directory, events, predictions or resource-preflight record was generated. The prior software regression suite was not rerun.

| Requested evaluation | C1.57 procedure / result |
|---|---|
| A. VAD | BLOCKED; no authorized audio/activity references; complete VAD frame trace remains a documented instrumentation gap |
| B. Vosk distress recognition | BLOCKED; no authorized audio/transcripts |
| C. Snowboy help detection | BLOCKED; no authorized audio/reference detections |
| D. openWakeWord keyword detection | BLOCKED; no authorized audio/model environment |
| E. Combined recognition/fusion | BLOCKED; no recorded independent-engine evidence or valid acoustic event trace |
| F. Partial-to-final Vosk revisions | BLOCKED; raw hypothesis/reset/gap trace unavailable for a run. Current matched-candidate reset means post-reset text is not the previous candidate's final revision, as already documented in C1.55 F. |
| G. Ordinary-speech false alarms | BLOCKED; no human-verified negative trials |
| H. Genuine-distress missed detections | BLOCKED; no human-verified positive trials |
| I. Background-noise sensitivity | BLOCKED; no approved noise-stratified trial allocation/conditions |
| J. Detection latency | BLOCKED; no valid detections, reference onsets or common-clock timing trace |

## E. Confusion matrices

The five templates below are unfilled SOP2 result tables. All counts are **[NOT MEASURED]**, including totals; they are not zero-count experimental outcomes.

### VAD

| Actual Class | Predicted Positive | Predicted Negative | Total |
|---|---|---|---|
| Actual Positive | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] |
| Actual Negative | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] |

### Vosk distress recognition

| Actual Class | Predicted Positive | Predicted Negative | Total |
|---|---|---|---|
| Actual Positive | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] |
| Actual Negative | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] |

### Snowboy help detection

| Actual Class | Predicted Positive | Predicted Negative | Total |
|---|---|---|---|
| Actual Positive | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] |
| Actual Negative | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] |

### openWakeWord keyword detection

| Actual Class | Predicted Positive | Predicted Negative | Total |
|---|---|---|---|
| Actual Positive | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] |
| Actual Negative | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] |

### Combined keyword recognition/fusion

| Actual Class | Predicted Positive | Predicted Negative | Total |
|---|---|---|---|
| Actual Positive | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] |
| Actual Negative | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] |

## F. Performance metrics

| Recognition Component | Evaluation Unit | Number of Samples | TP | FP | TN | FN | Accuracy (%) | Precision (%) | Recall (%) | Specificity (%) | F1-Score | False Positive Rate (%) | False Negative Rate (%) | Evidence Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| VAD | Frame/utterance, grouped by speaker/session; labeling rule pending | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | BLOCKED; no acoustic run |
| Vosk | Exact keyword per utterance; grouped by speaker/session | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | BLOCKED; no acoustic run |
| Snowboy | Help detection per utterance; grouped by speaker/session | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | BLOCKED; no acoustic run |
| openWakeWord | Exact keyword per utterance; grouped by speaker/session | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | BLOCKED; no acoustic run |
| Combined recognition/fusion | Exact-keyword and any-distress outcomes separately per utterance; event boundaries pending | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | BLOCKED; no acoustic run |

No metric was computed from acoustic data. Before future use, follow the direct count formulas in C1.56 F. The known helper returns null F1 when precision or recall is undefined even if `2TP+FP+FN>0`; direct F1 is `2TP/(2TP+FP+FN)`. A zero direct denominator is N/A; a nonzero denominator with TP=0 yields 0. Undefined precision and defined-zero F1 are separate cases. This is the previously established arithmetic rule, not a new C1.57 measurement or repeated investigation. The helper was not modified or used to publish results. A separately verified calculation would be required before reporting actual metrics; it has not been created or certified here.

When data is available, report exact-keyword and any-distress matrices separately, retain speaker/session IDs, and record missing/failed trials. Do not convert missing recognizer output to a true negative or treat a wrong keyword as an exact-keyword success. F1 is dimensionless; percentage columns multiply proportions by 100. Counts and denominator definitions must accompany future estimates.

## G. False-alarm and missed-distress findings

No acoustic false-positive case or missed-distress case was observed or reviewed in C1.57. Both findings are **[NOT MEASURED]**, not “none found.” No claim of noise robustness, improved recall, reduced false alarms or comparable-baseline improvement is supported.

Evidence classes remain distinct:

| Evidence class | Available statement | Scope |
|---|---|---|
| Actual C1.57 acoustic results | [NOT MEASURED] | No acoustic trial executed |
| Prior C1.54 software regressions | Previously reported 333 combined mocked tests passed; 25 focused mapping tests passed | Historical synthetic software evidence only; not rerun, not acoustic sample counts |
| C1.57 blocked work | Dataset permission missing; ground truth/environment/resource gates not verified | No synthetic output substituted for real measurements |

## H. Latency measurements

| Recognition Component | Number of Trials | Mean (ms) | Standard Deviation (ms) | Median (ms) | P90 (ms) | Minimum (ms) | Maximum (ms) | Evidence Status |
|---|---|---|---|---|---|---|---|---|
| VAD | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | BLOCKED; no timing trace |
| Vosk | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | BLOCKED; no timing trace |
| Snowboy | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | BLOCKED; no timing trace |
| openWakeWord | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | BLOCKED; no timing trace |
| Combined recognition/fusion | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | [NOT MEASURED] | BLOCKED; no timing trace |

No onset/detection timestamps exist for a C1.57 run. Future onset-based latency requires a human-verified onset and correct-detection timestamp in the same timebase; start-of-recording latency must be labeled separately. Cross-clock, absent or invalid timestamps cannot yield a latency. Report misses/failures alongside successful-trial latencies; do not substitute software test execution duration.

## I. Statistical validity and limitations

No acoustic sample size, confidence interval, inference, p-value, effect size or accuracy estimate is available. Frames are nested within utterances; utterances may repeat within speakers/sessions. Future grouping/interval methods must follow actual allocation and independence, as already specified in C1.56. Alert episodes require explicit ground-truth trial identity and reviewed boundaries; they cannot be inferred from an invented timeout.

Questionnaire allocation stays **5 IT Professionals + 25 Rescue/Safety Personnel = 30 unique respondents**. Those respondents are not the acoustic sample size. No questionnaire responses or conclusions are reported here. The SOP1 confirmation does not establish measured thermal adaptation or performance.

## J. Independent verification

**RESULTS INDEPENDENTLY VERIFIED: NO.** There are no actual acoustic results to recalculate or independently review. The task's conditional actual-results review/preservation phase was not entered. Prior protocol/alignment reviews remain prior evidence and are not represented as an independent review of new acoustic findings.

This milestone's verification consists of report consistency, preservation of all 31 prior development artifacts, and before/after Git-state comparison. It establishes safe documentation/preservation only; it does not verify ground truth, models, resource readiness or performance.

## K. Remaining blockers and preservation

To revisit execution, the run must have:

1. A specifically identified dataset/version/authorized subset and owner permission for its intended local processing, with applicable consent/license/privacy constraints and evidence storage scope. Restricted PLD needs explicit PLD-specific authorization if selected.
2. Access-authorized human ground truth bound to recording IDs/hashes: labels/transcripts, reviewer/adjudication references, speaker/session grouping and trial/split allocation. Onsets and speech activity boundaries are required for the corresponding latency/VAD measures.
3. An approved execution host, frozen environment/config and authorized immutable models/inputs, output/scratch locations, OS-enforced network/device/storage isolation, and verified resource/service-concurrency safety. Resource checks must pass without bypassing them or modifying swap.
4. Adequate evaluation-only VAD and Vosk/reset/gap traces and an independently checked metric calculation respecting the known F1 rule, before reporting the affected outcomes.

These are outstanding execution prerequisites from the existing protocol, not a reopened SOP investigation or new acceptance thresholds.

Repository verification: production and evaluation HEAD/branch/status are compared before and after report creation; production tracked files remain clean with pre-existing untracked status preserved, and evaluation remains clean. All 31 pre-existing offline development artifacts match saved hashes. The intended sole new worktree path is `docs/C1_57_acoustic_evaluation_results.md`; no existing runtime/source/report is changed. No protected dataset/database content was read or written; no production alert, alarm-authority rule or delivery route was changed. No staging, commit, push, pull, fetch, merge, rebase, reset, clean, deployment, service control, Docker, swap or boot change was performed.

## L. Readiness for C1.58 Runtime Integration

C1.57 supplies a blocked execution record, not acoustic validation evidence for runtime integration. Existing authority, episode, thermal association, transactional/recovery and acoustic-validation blockers are not cleared by the SOP1 wording confirmation. C1.58 cannot be declared integration-ready on the basis of this report.

- **ACOUSTIC EVALUATION EXECUTED: NO**.
- **RESULTS INDEPENDENTLY VERIFIED: NO**.
- **GROUND TRUTH VERIFIED: NO**.
- **RUNTIME INTEGRATION READY: NO**.
- **PRODUCTION DEPLOYMENT READY: NO**.
