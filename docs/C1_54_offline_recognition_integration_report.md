# C1.54 — Controlled Offline Recognition Integration Harness

**TEST-ONLY VERIFIED: YES**

**RUNTIME INTEGRATION READY: NO**

**PRODUCTION DEPLOYMENT READY: NO**

Implemented a disconnected mapper/harness that accepts synthetic equivalents of
inspected recognition metadata and feeds the unchanged pure C1.53 in-memory contract.
Final focused **25** and combined **333** tests pass. Compatibility demonstrated here
is limited to the declared synthetic/source-shaped interfaces, not live engines,
acoustic performance, a production wire protocol or safe alarm authorization.

Worktree: `/var/tmp/Project_Pi_C1_43_alarm_fix`.
Branch: `development/c1-43-c1-47-recognition-safety`.
HEAD: `8a44f109fae8adb4b7daa833c15548b56ccd2452`.
Date: 2026-11-02. No runtime application, service, backend, schema or Flutter changes.

Plan: add `experiments/offline_recognition_mapper.py`, `test/test_offline_recognition_mapper.py`, and this report only. Use the unchanged C1.53 contract as an in-memory sink. Inspect existing output shapes; use test-first synthetic mappings and source-extracted alias fixtures without importing application entrypoints. No sensors, models, network, store, thermal or authority decisions.

- [x] Verify prior 41/8/10/8 checksum chain, 26 sources and byte-exact preservation of C1.53 (new incremental: 10 artifacts).
- [x] Run prior selected 308 tests.
- [x] Write failing engine-output mapping tests; implement the disconnected mapper.
- [x] Run focused/combined tests and static isolation checks.
- [x] Obtain separate read-only review and fix reproduced experimental/test issues only.
- [x] Recheck sources/backups/Git and complete sections A–J with hashes and readiness.

Rulings: source identity/sequence/generation/candidate/revision/time come from fixtures, never engines or wall-clock guesses. Raw Vosk JSON and selected application metadata are preserved. Configured confidence is not engine confidence. openWakeWord fixtures project metadata and explicitly exclude cleaned audio. Alias precedence comes from a supplied ordered vocabulary, not a new policy. Only the mapper imports the pure experimental contract; no runtime caller is added.

Ledger: 24 tests failed at the absent-mapper assertion before implementation, then
24 passed and the first combined suite passed 332. Separate review reproduced one
valid failure-metadata edge case: `str(RuntimeError())` is empty and was incorrectly
rejected. A new test failed before accepting empty error strings; final focused 25
and combined 333 passed. All corrections were limited to this milestone's artifacts.

## A. Actual engine output mappings

Source below is the current offline candidate; no SDK documentation/recording/model
is treated as new evidence. Inspection does not establish actual engine-version
behavior beyond what application source consumes/produces.

| Interface and exact source | Actually supplied/consumed data | Application-generated data and harness mapping |
|---|---|---|
| Vosk `read_vosk_text`, `raspberry_pi/kws/kws_alert_dual.py:939`; `vosk_worker:1080`, especially `:1124` and `:1183–1192` | `AcceptWaveform` verdict selects `Result` or `PartialResult`. JSON `text`/`partial` strings are consumed; `result`/`partial_result` word metadata, if present in fixtures, remain original data. Current helper flattens finality. | Harness `vosk(meta, raw_json, final=...)` gets the verdict explicitly and preserves raw JSON plus parsed object. It applies supplied source vocabulary to text, retaining partial/final. Confidence is null; word confidences are not aggregated. Current worker's configured scalar/verifier-boosted confidence is application output, not an utterance-confidence field supplied by the JSON. |
| Alias matching `_normalize_vosk_text:909`, `detect_tagalog_keyword:916`, `TAGALOG_KEYWORD_ALIASES:64` in the same file | Normalization strips nonletters within tokens, lowercases, then matches configured whole-token aliases in keyword declaration order. | Tests AST-extract the literal vocabulary and the two pure matching functions without importing the application. Harness uses a copied ordered vocabulary and conforms on all configured aliases plus negative/precedence fixtures. No prefix/fuzzy guessing or new vocabulary. |
| Snowboy `snowboy_worker:1218`, `RunDetection` at `:1249` and submission at `:1260` | Integer positive result selects a configured detector index; zero produces no detection; `-1` is logged as detector error and the worker continues. Source gives no normalized recognition confidence. | Harness `snowboy(meta, result, config=...)` records positive results as non-ASR detection with missing confidence, zero as healthy no-detection, negative codes as gap/unknown without guessing silence/death. Configured index-to-label list and configured alert label are distinct application inputs. Current dispatcher submits the configured alert label and configured confidence, which the harness does not promote into engine evidence. |
| openWakeWord `AudioPreprocessor.process`, `raspberry_pi/kws/audio_preprocessor.py:107`; `_result:226`; KWS `main` loop callsite `:1589` (function begins at `:1308`), `:1622–1658` | Model prediction is processed into application metadata: `available`, `is_speech`, `vad_score`, `scores`, `wake_words`, `error`, and separate `cleaned_audio`. Score rows contain `name`, `raw_name`, `score`, `threshold`. | Harness `openwakeword(meta, metadata, model_name=...)` accepts the six metadata fields only, selects explicit raw model name and preserves all metadata/detection flags. It records present normalized score even when not reported as a detection; it does not choose/recompute thresholds. Missing selected score is missing, not zero. Unavailable is not generation death. |
| Prediction error at `audio_preprocessor.py:127–136` | `Exception` becomes `available=False`, permissive fallback speech/VAD and `error=str(exc)` with empty score/detection lists. The error string can be empty. | Empty string is preserved as valid diagnostic text. Non-string errors, contradictory availability and malformed scores/rows are rejected rather than coerced. Optional disabled/unavailable prediction is not itself proof of engine-session termination. |
| Engine startup/supervision `kws_alert_dual.py main:1490–1518`, `:1563–1567` | Startup may disable optional engines; an exception escaping a worker can lead main to exit on dead-worker detection. Current runtime does not emit this proposed structured observation format. | Harness `failure(meta, engine=..., error=...)` consumes an explicitly supplied fixture lifecycle description. Restart requires `begin_generation` with a new supplied ID. It does not execute exceptions in engines, discover restarts or infer acoustic episode boundaries. |
| Publication/cooldown `CooldownGate.allow:665`; `DetectionDispatcher.submit:742`, `_publish_tulong:777`; `AlertPoster.publish:214` | Gate returns a boolean. Dispatcher/publication methods return None and do not expose the proposed acceptance receipt. Tulong state refresh precedes cooldown rejection in retained runtime. Poster creates fresh alert UUIDs, retries existing queued IDs. | Harness `publication_receipt` records a supplied outcome/reason only. Test AST-extracts the real gate with a synthetic clock to produce a rejection; it does not infer publication success from None or invoke the dispatcher/poster. Rejection cannot alter candidate/generation evidence or refresh a veto. |

IDs, producer, generation, candidate, revision, sequence, supplied aware timestamp,
clock domain and capture range come entirely from explicit fixture context. Engines
do not supply that full contract today. They are not auto-generated by the harness.
Model-label mapping and threshold values are application configuration, not recognized
ground truth or an emergency policy.

## B. New experimental adapter design

New files only:

1. [`experiments/offline_recognition_mapper.py`](../experiments/offline_recognition_mapper.py)
2. [`test/test_offline_recognition_mapper.py`](../test/test_offline_recognition_mapper.py)
3. This report, `docs/C1_54_offline_recognition_integration_report.md`.

The single `OfflineRecognitionHarness` composes the unchanged C1.53 `EvidenceLedger`.
It imports only json, math and the pure experimental contract. Methods are
`begin_generation`, `snapshot`, `vosk`, `snowboy`, `openwakeword`, `failure` and
`publication_receipt`. There are no clock reads, SDK/application imports, device
constructors, I/O, threads, subprocesses, publication callbacks or policy decisions.

Each mapping constructs a detached record, calls `validate_observation`, then applies
the in-memory ledger's order/revision/identity checks. Mapping/schema/conflict failures
occur before ledger mutation. Caller/returned objects cannot alter retained evidence.
Raw JSON strings are identity-bearing; even a whitespace change under a previously
accepted observation ID conflicts, while unchanged retries are idempotent. Duplicate
JSON keys and nonfinite constants are rejected instead of silently changing evidence.

Fixture metadata requires exactly observation/producer/generation/candidate identities,
source sequence/revision, observed_at/clock_domain and capture_range. Controls require
null revision, and detections require their explicit consecutive revision. No missing
context is filled from system time, source guessing, a UUID generator or a timeout.

Raw evidence layout is explicit:

- Vosk: exact `raw_json`, parsed `engine_output`, supplied `application_context`.
  Finality comes from the supplied AcceptWaveform verdict, not text or score heuristics.
- Snowboy: integer `engine_output` and copied application label/confidence `config`.
  `keyword` describes the configured detector label; the application alert label is
  retained separately and is never dispatched. An out-of-range positive index is
  rejected rather than using the runtime's alert-label fallback for unknown evidence.
- openWakeWord: complete **metadata projection** as `engine_output`, selected model
  identity and `reported_detection`. The parameter excludes `cleaned_audio`, NumPy
  arrays and raw waveform samples; it is not a drop-in whole `process()` result/SDK
  output adapter. Projection must be explicit in any future separately reviewed caller.
- Failure: supplied JSON error description and explicit fixture lifecycle tag. This
  does not claim current runtime already produces structured failure observations.

The harness never creates episodes, classifications, alert events, backend requests,
persisted receipts, thermal associations or audible authority. Source-key/sequence
snapshot order remains the C1.53 deterministic representation, not global acoustic time.

## C. Synthetic integration scenarios

| Required scenario | Executed outcome |
|---|---|
| Partial tulong followed by final tulog | Raw partial/final data retained under the same candidate; two revisions; ordinary final label null. Partial publication is not invoked. |
| Genuine partial-only tulong | Stipulated positive fixture remains partial with missing utterance confidence; no final or authority fabricated. Real acoustic ground truth is not established. |
| Final distress | Existing alias matching yields the configured label; word confidence/timing metadata stay raw, application configured confidence stays separate. |
| Snowboy help without confidence | Positive detector index becomes help detection with null confidence; configured .95 fixture value is retained only as context. |
| openWakeWord score/detection metadata | Raw model key, resolved name, score, threshold, VAD and application detection list are retained. Below-threshold score remains score data, not an alert. |
| Vosk ordinary speech plus independent help | Snowboy and openWakeWord help each survive the ordinary Vosk revision. All 12 valid engine interleavings have identical final snapshots. |
| Failure/restart | Explicit failure leaves retained evidence, blocks same-generation recognition and accepts a separately declared new generation. A logged Snowboy error code/unavailable prediction alone does not imply generation death. |
| Repeated/out-of-order observations | Exact duplicate leaves snapshots unchanged; source reordering and invalid candidate revision fail atomically. No automatic episode creation or release. |
| Missing/malformed score | Absent selected model/score becomes missing, preserving prior evidence. Boolean/string/nonfinite/out-of-domain score and contradictory/doubled rows reject without mutation. No silence or zero is invented. |
| Publication rejection | Real AST-extracted cooldown gate rejects under a synthetic clock; a supplied rejected receipt changes only the receipt journal. It does not reproduce a runtime receipt API that does not exist. |
| Conflicting immutable identity | Changed raw JSON under the same ID conflicts. Existing C1.53 typed JSON identity tests remain green. |
| Input/output mutation | Mutating supplied score lists, source capture range, returned record/raw payload or snapshots does not change ledger state. |
| Empty exception text | `error=str(RuntimeError())` is accepted, copied unchanged and represented as unavailable/missing rather than rejected or reinterpreted as healthy. |

No engine, model, microphone, restricted recording, actual capture or physical alarm
was exercised. Vocabulary/cooldown extraction compiles only the inspected pure nodes
with fixture dependencies, not module startup. These tests establish software shape/
identity compatibility on declared data; they do not establish engine guarantees.

## D. Contract compatibility findings

**Compatible within the tested subset:** explicit Vosk partial/final text and opaque
word metadata; detector-only Snowboy labels without confidence; the application's
openWakeWord metadata projection with finite normalized model scores; explicit failure,
missing/unavailable state, source identity/revision ordering and independent evidence.

**Important differences/limitations:**

- Runtime flattens Vosk finality and applies configured/verifier confidence. The mapper
  preserves finality and missing engine confidence instead. It does not aggregate word
  scores, run a verifier or claim a calibrated sentence confidence. It requires the explicit
  text field corresponding to the supplied finality verdict; it does not emulate the
  runtime helper's permissive opposite-field/empty fallback for malformed or incomplete
  JSON. Coverage is the declared result subset, not all possible SDK payloads.
- Runtime Snowboy dispatch may use configured alert label even when a detector label
  differs or its index is outside the label list. The mapper preserves the detector
  mapping and rejects unknown positive indices. This stricter validation is not a
  runtime change or proof that those inputs never occur.
- Nonpositive Snowboy codes are preserved without importing undocumented SDK meaning.
  Negative values mark a gap/unknown diagnostic, not proven silence or process failure.
- Actual `AudioPreprocessor.process` includes an audio array. Only its non-audio metadata
  projection is accepted. Unsupported raw SDK arrays/types/scores need a separately
  reviewed mapping; no array or calibration conversion is invented here.
- Selected score rows missing their score use explicit missing state rather than the
  runtime's possible coercion/default behavior. Successful empty lists or VAD-gated
  absence do not prove a negative observation for every configured keyword.
- The supplied application detection flag is retained; the mapper checks corresponding
  row identities/scores/threshold metadata, not a complete model/VAD/threshold-policy
  equivalence proof. It does not rerun or choose recognition thresholds or turn a
  reported detection into truth or authority.
- `recorded`/duplicate in the dependency ledger means memory only. There is no storage,
  network, transactional receipt, durable generation identity, crash/replay protocol
  or real concurrent scheduling. Rejected raw input is not a durable pending queue.

Therefore this harness is **not** a production adapter, event publisher or proof that
the current recognition architecture is safe to activate with new semantics. The
compatibility gaps are documented, not hidden by changing C1.53 or runtime code.

## E. Baseline and final test totals

| Run | Tests | Failures / errors | Skips / expected failures / unexpected successes |
|---|---:|---:|---:|
| Prior selected baseline | **308** | **0 / 0** | **0 / 0 / 0** |
| New tests before mapper existed | 24 | 24 / 0, expected absent-mapper assertions | 0 / 0 / 0 |
| Initial focused implementation | 24 | 0 / 0 | 0 / 0 / 0 |
| First combined selection | 332 | 0 / 0 | 0 / 0 / 0 |
| Review empty-error reproduction | 1 | 1 / 0, expected failure | 0 / 0 / 0 |
| Final focused mapper suite | **25** | **0 / 0** | **0 / 0 / 0** |
| Final combined selection | **333** | **0 / 0** | **0 / 0 / 0** |

Final combined duration was 14.084 seconds, not an acoustic/emergency latency result.
The focused suite uses no database fixtures. The unchanged selected prior suites use
only fresh synthetic temporary stores/outboxes; no production database or queues.

Focused command:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest test.test_offline_recognition_mapper -q
```

Combined selection, from the development worktree (omit only the new module for 308):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest \
  test.test_offline_recognition_mapper test.test_pure_observation_contract \
  test.test_disconnected_observation_adapter test.test_runtime_safety_blockers \
  test.test_alarm_authority_contract test.test_vosk_hypothesis_revision \
  test.test_recognition_defect_remediation test.test_episode_rearming_review \
  test.test_keyword_rearming_prototype test.test_kws_event_id test.test_keyword_fusion \
  test.test_kws_live_paths test.test_kws_recognition_regression test.test_alert_decision \
  test.test_alert_trace test.test_alert_publication \
  test.test_alert_delivery.DeliveryStorageTest.test_restart_retains_full_envelope_and_uuid \
  test.test_alert_delivery.DeliveryStorageTest.test_concurrent_duplicate_and_conflicting_uuid \
  test.test_alert_delivery.DeliveryStorageTest.test_independent_acks_survive_restart \
  test.test_alert_delivery.DeliveryStorageTest.test_replay_policy_boundaries \
  test.test_alert_delivery.DeliveryStorageTest.test_recovery_cursor_ignores_presentation_but_respects_confirmation_and_age
```

Actual invocations load these exact unittest names, capture diagnostics in memory and
disable bytecode. Default temporary fixtures were redirected below the offline
worktree; explicit ROOT fixtures also stayed there and cleaned themselves. Audit guards
rejected network/DNS, subprocesses, production file access, model/recording extensions
and SQLite outside the worktree. No broad discovery or application startup occurred.
Expected malformed-policy fixture warnings do not indicate changed deployed settings.

## F. Independent reviewer findings

A separate read-only reviewer inspected actual source shapes, mapper and tests, using
pure `python -B` probes without writes, stores, model/network/device/service access.

**P2, reproduced and repaired:** the mapper originally required every non-null error
string to be nonempty. Current `AudioPreprocessor.process` catches arbitrary exceptions
and returns `error=str(exc)`; `RuntimeError()` therefore creates a legitimate empty
string. The reviewer reproduced atomic rejection of that valid unavailable result.

A new source-shaped test first failed. The mapper now validates string-or-null errors,
preserving empty text unchanged. Independent recheck confirmed missing/unavailable
mapping, preserved empty text and atomic rejection of non-string error values. No
remaining material code issues were found. Only this milestone's experimental/test
files changed for the repair. Final suite counts and preservation checks were run by
the implementer, not claimed as reviewer-run suites. The reviewer also read the final
report and checked mapper/test hashes, finding no material discrepancy in the scope,
evidence or readiness claims. Minor source-anchor corrections were applied to this
report only. No extra suites or file/Git writes were performed by the reviewer.

## G. Runtime and delivery isolation verification

Static checks examined all tracked **30 application Python files** under `raspberry_pi/`
and **67 Flutter Dart files** under `lib/`: no reference to the mapper, no application
Python import from `experiments`, no production entrypoint or service hook added.
The new module imports only json/math and the unchanged pure experimental contract.
Its focused AST test rejects direct dynamic execution/import, filesystem, network,
clock-read and publication calls. No callback or transport is accepted by the harness.

Byte-for-byte preservation of **197 pre-existing tracked Python/Dart/Markdown files**
includes KWS entrypoints, backend `AlertIn`/schema/API/AlertStore, SQLite live-poll/replay
delivery and every Flutter file. No migration, application configuration, service,
packaging initializer or entrypoint was added. No actual application code invokes the
mapper. Its outputs can reach only the in-memory contract in the executed harness.

This is a checked-tree isolation statement, not a security sandbox against a future
caller manually misrouting JSON. Observation `record_type` is not an alarm safety flag:
existing legacy/backend/Flutter consumers can act on ordinary alert-shaped data.
Do not put these observations into the live alert store or any live/poll/replay/legacy/
WebSocket/Flutter channel. The harness has no mechanism to do so, and no current
production alert database receives its outputs. No siren/notification lifecycle was
called or changed; no existing alarm/thermal/manual/ACK/replay policy was altered.

## H. Backup and Git preservation

Phase 0 passed before implementation. All prior sealed manifests, complete membership,
source inventories and retained byte-exact recovery files were verified. Original
26 artifacts remain intact, including the three C1.53 files checked against their
completion SHA-256 values. The earlier failed backup was preserved too.

| Backup | Artifact checksums | SHA-256 of SHA256SUMS |
|---|---:|---|
| `/home/thesis/offline-work-backups/C1_48_R_20261102T011740.344081Z` | 41 | `ee49731c9348f23b65d5df6d67871075bc7a15ca1206f57d3922428ebd4b0772` |
| `/home/thesis/offline-work-backups/C1_51_incremental_20261102T014123.101687Z` | 8 | `c217a060934c96c87bd15fced50c0ede3d744f37d67c3c5dee3928b1c772600a` |
| `/home/thesis/offline-work-backups/C1_52_incremental_20261102T020020.894305Z` | 10 | `aace26d4a970bbcf7fdd7a6698b9c413c1ef4db6ccadddc050d1c329ce49866d` |
| `/home/thesis/offline-work-backups/C1_53_incremental_20261102T021726.563255Z` | 8 | `1b154f50c5e10a973ae7b1d19494b30c5a31a78914f398526c5f235a6e35c243` |
| **New C1.53 preservation:** `/home/thesis/offline-work-backups/C1_54_incremental_20261102T023613.561649Z` | **10** | `430510051aac14291e26ac1ca7ad8a12603b328f2cfd321058a3930f7e1ab401` |

The new backup contains a raw three-file archive, metadata/inventory/HEAD/status,
complete 26-file preflight inventory, verification, restoration instructions and
retained `verified-recovery/`. Recovered files match path/type/mode/size/SHA-256 and
original bytes. Files and directory metadata were flushed before phase 0 passed.
Restore via its `RESTORE.md` into a NEW empty target using standard-library binary
tar extraction, exact inventory membership and metadata/hash comparison. No network
or Git operation is needed. These are local changed-file snapshots, not full Git
history or off-host redundancy. No old artifact was replaced/deleted.

Final checks repeat sealed-manifest completeness, all 26 source artifacts, 197 tracked
source hashes, original tracked binary diff, HEAD/ref/index/status and ignored/untracked
inventory. Exactly three C1.54 files are new; none of the prior module/reference/test/
report files changed. No staged changes, new ignored fixture directories or bytecode.

| New file | Bytes | SHA-256 |
|---|---:|---|
| `experiments/offline_recognition_mapper.py` | 10299 | `a69a371e73c05b6ff3a917426de933f429bfac9d335ec86de79b8b95efa5de3e` |
| `test/test_offline_recognition_mapper.py` | 15741 | `dfd1fd1aad03e9b8cb5b867f849686c9a1dc1e72b3ac9c8822818125c58027c2` |

This report is the third file; its complete-file SHA-256 is recorded in the completion
receipt to avoid a self-referential checksum. Current C1.54 files are not covered by
the earlier sealed snapshots and should be preserved before subsequent edits.

| Checkout | Verified unchanged state |
|---|---|
| Production `/home/thesis/Project_Pi` | `main`, `1a5c3095a27421cb4c667ee6caed14169729e774`; tracked clean; original index/status; four pre-existing untracked model/database paths inventoried only, contents not opened. |
| Evaluation `/var/tmp/Project_Pi_M3_eval` | `main`, `8a44f109fae8adb4b7daa833c15548b56ccd2452`; clean, unchanged index/status. |
| Offline worktree | Requested branch and baseline HEAD/index; original candidate changes intact plus exactly three C1.54 additions. |

All Git reads use explicit checkout paths and optional locks disabled. No ancestor
discovery operation under `/home/thesis`, ref/config change, staging, commit/push,
pull/fetch/merge/rebase/reset/clean, deployment, service restart, swap/Docker/boot
change, microphone/model invocation or restricted recording/production database/
credential/queue access occurred. Backup writes were limited to the new incremental
directory; implementation/test/report additions stayed in the development worktree.

## I. Remaining acoustic and alarm-authority blockers

Shape-compatible synthetic inputs do not establish real ASR revisions, partial-only
recall, ordinary-speech false activation, confidence calibration, VAD/endpoint/reset
effects, capture drops or time-to-alarm. None of those metrics is measured here.
Source-associated engine names do not imply independent acoustic errors.

The live partial-authority/cross-engine veto/rejected-veto-refresh and missing
thermal-triggered escalation risks remain unchanged. Provisional speech authority,
voice/thermal association lifetime, episode end/release and distinct spoken-repeat
eligibility remain **UNRESOLVED**. No confidence threshold, confirmation timeout,
new thermal decision or emergency authorization policy was selected.

In-memory fixture IDs and ordering are not trusted runtime generation/capture provenance,
crash recovery, concurrent processing, transactional speech history or durable receipts.
Application-shaped mapping is not complete raw SDK support. Any production bridge must
meet C1.52's structural shadow isolation, atomic history/intent, immutable event IDs,
independent evidence, ACK/replay/manual/critical and device acceptance gates. A green
mapper cannot waive those gates or authorize live audio/service experiments.

## J. Recommended next milestone

**C1.55 — Acoustic and controlled emergency validation protocol, documentation first.**
The next substantial evidence gap is empirical, not another claim from more mocks.
Prepare a separately reviewable protocol with approved provenance/consent, frozen
code/model/config identifiers, speaker/session-separated data, declared ground truth
and denominators, contextual negatives, all existing vocabulary/variants, interrupted/
partial-only and repeated/overlapping distress, actual result/reset traces and engine
failure/capture-gap cases. Preserve the C1.54 files first.

Predeclare recall/false-activation/time-to-alert criteria, uncertainty reporting,
sampling sufficiency and rescue/safety review before measuring or tuning. All numeric
limits are **UNRESOLVED** here. Include controlled thermal association and device
notification/audio/recovery scenarios as distinct later experiments. Hardware use,
new recordings, restricted data or model inference require explicit separate permission;
this milestone grants none. Do not add another transport/dispatcher/authority integration
merely because synthetic tests pass. Thesis results/conclusions must distinguish actual
measurements from these software contract checks.

Final status: **TEST-ONLY VERIFIED: YES. RUNTIME INTEGRATION READY: NO.
PRODUCTION DEPLOYMENT READY: NO.**
