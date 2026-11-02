# C1.58-INT-MERGE — Combined backend integration report

Project: IoT-Based Thermal-Acoustic Human Detection System.  
Date: 2026-11-02. Isolated source integration and synthetic software verification only.

**The Windows source and preserved Pi reliability work are integrated in one isolated
candidate. The combined backend run passed: 512 passed, 0 failed, 0 errors,
1 skipped, 0 expected failures, 0 unexpected successes.** Remote mute remains
disabled by default with no production lease duration. Deployment is not authorized.

## Candidate, transfer verification and ancestry

Exact integration checkout:

`/home/thesis/integration-candidates/C1_58_INT_MERGE_20261102T111558Z`

Local branch: `integration/c1-58-pi-windows`. The final tree is recorded as a local
two-parent integration commit, preserving both source histories. Its exact commit
ID and tree ID are recorded in `candidate-commit.txt` and
`completion-verification.json` in the audit directory below. No GitHub merge or
push occurred. This repository has its own `.git`; it is not a worktree sharing
the production/evaluation Git directory.

Incoming bundle:

`/home/thesis/offline-work-backups/incoming/Project_Pi-c158-resident-interoperability-9b4f023.bundle`

Verified SHA-256:

`8be166714ffd379b31035208da87a47d21f1f326f3f1a62b9ae4505653f21f85`

The file exists and matches the requested hash. `git bundle verify` succeeded in
an empty isolated bare repository and reported complete history. The advertised
branch resolves to the exact requested commit. The bundle was cloned locally
without checkout into the new repository, then the reviewed target was checked out.
`git fsck --full` succeeded. No import touched the production repository.

Verified source ancestry:

```text
b6a2a20ded8df62cefb7ef6616710cbfdca140cf  common parent
├─ 3921112b4365732e5d3bb461b2a382d5c905091a  Windows UI
│  └─ 0419f5d86e1479d43ba5f4e7aaaf21d318aac385  Resident interoperability
│     └─ 9b4f02305f4040aa27cb7ca666442c644036a38d  requested Windows target
└─ 8a44f109fae8adb4b7daa833c15548b56ccd2452  Pi replay-evaluation safeguards
   + preserved uncommitted Pi C1.43–58 development
```

Pi's shallow checkout did not initially expose parent objects locally. A local
Pi-base bundle was created without modifying its checkout and imported only into
the scratch repository; Windows supplied the shared ancestor objects. Git then
confirmed the common parent above. Neither source tip is substituted for the other.

Audit/recovery directory:

`/home/thesis/offline-work-backups/C1_58_INT_MERGE_20261102T111558Z/`

It retains transfer checks, ancestry, source differences, reconciliation records,
raw recovery copies, logs, exact test selections, dependency versions, independent
review findings, final inventory/checksums and a local final candidate bundle.

## Pi preservation

All **11 earlier checksum manifests, covering 223 entries**, verified before source
reconciliation. The earlier 32-file archive/raw recovery and nine C1.58 completion
files also verified. A new checkpoint preserves **37 current development files**,
including every tracked modification, untracked report/helper/test/experiment and
the previous integration preflight report. It includes raw files, archive members,
hashes/modes, tracked/staged/unstaged binary patches, HEAD preimages and Git state.

The original Pi worktree remains at `8a44f109` on
`development/c1-43-c1-47-recognition-safety`, with its original four tracked
modifications, 33 untracked development files and no staged changes. Its 37 file
hashes, patches, branch, HEAD and status match the pre-integration checkpoint.

The retained C1.58 behavior includes:

- Per-source accepted `tulong` timestamps, independent Snowboy/openWakeWord/Vosk
  evidence, no text-hint veto, no rejected-submission correlation mutation, exact
  whole-token aliases and existing cooldown/confirmation parameters.
- Shielded duplicate HTTP waiters; owner cancellation releases the in-flight
  claim and wakes/cancels waiters; continued threaded insertion remains deduplicated.
- Durable SQLite event IDs/envelopes/fingerprints, immutable duplicate responses,
  per-caregiver ACKs, restart recovery and existing critical replay rules.
- All earlier regression/reference helpers and disconnected experiments. Experimental
  observation modules were not connected to runtime alarm authority.
- Pi's committed replay provenance, resource/isolation and evidence safeguards,
  including its large replay-evaluation test expansion.

## Reconciliation and conflicts resolved

The Windows branch changes 44 paths from the common parent. Pi's committed tip
changes three paths, followed by its preserved 37 development artifacts. Integration
was assembled file by file against the common parent; no full branch merge was
applied over the original dirty Pi worktree.

Four files contained contributions from both sources:

| File | Reconciliation |
|---|---|
| `raspberry_pi/backend/main.py` | Windows scoped Resident/Main routes and audio mute metadata plus Pi cancellation/shield/claim-cleanup fixes |
| `raspberry_pi/kws/kws_alert_dual.py` | Windows capture/worker epoch fencing plus Pi dispatcher evidence fixes and exact aliases; additional timer race fixes below |
| `raspberry_pi/kws/replay_eval.py` | Pi's complete evaluation safeguards plus Windows' explicit remote-mute disable during replay |
| `test/test_replay_eval.py` | Both test sets; Windows mocked `_run_once` return updated to Pi's pacing dictionary, and model paths made explicitly synthetic |

These hunks combined without textual conflict markers. Semantic conflicts still
required reproduction and correction; a clean textual combination was not treated
as verification. The other committed Pi document and all original development
artifacts were retained. Windows Main/Resident Flutter, Android flavors and UI
files remain byte-identical to the imported Windows commit.

Integration changes over Windows affect 45 paths including this report: 44 source,
test and preserved-document paths plus the report. The complete inventory below
covers 84 paths relative to the common parent, including preserved additions.
Machine-readable inventories and binary diffs provide exact bytes and boundaries.

## API compatibility and safety contracts

| Interface / concern | Integrated behavior and evidence |
|---|---|
| Genuine alert APIs | Existing `/api/alerts`, `/api/alerts/manual`, response shape, same-ID fingerprint conflicts and durable storage remain compatible. Resident TEST gestures do not call the genuine manual endpoint. |
| Main API authentication | Existing required-mode bearer and fail-closed configuration remain. Main TEST state/ACK routes independently validate the Main bearer and explicit TEST mode. |
| Resident authorization | Exact `POST /api/resident/control` uses `X-Resident-Id` plus a separate Resident verifier/secret. It requires effective API mode `required` and TEST mode. Main credentials cannot substitute for scoped Resident credentials, and Resident credentials cannot call real alerts or Main controls. |
| Caregiver delivery | `/ws/alerts?protocol=2` retains per-installation authentication, instance/cursor replay, identity/sequence-bound ACKs and independent confirmations. |
| Single/double TEST commands | `keyword_test` / `full_test` produce separate `test-...` IDs, `is_test=true`, `source=resident_test`, command ID, sequence, session and boot identity. Same-command retries reuse identity; conflicts/stale sequences/old sessions are rejected. |
| TEST lifecycle | Bounded ephemeral control store is separate from real SQLite history and real outboxes. Acceptance, Main presentation and user acknowledgement remain distinct; restart invalidates TEST sessions/events. Real emergency replay remains durable. |
| Main presentation/output | Windows source checks explicit TEST identity/type, persists claimed test IDs, requires local foreground TEST output authorization, and keeps real emergency output ownership/preemption. Flutter behavior was reviewed statically but not rerun on this Pi. |
| Remote mute configuration | TEST mode + explicit enable + finite positive administrator-supplied maximum + safe IPC + authenticated session + fresh valid worker ACK are required. Missing/invalid values leave capability unavailable. No default production duration or enabled service configuration was added. |
| Server-owned hold | Lease binds backend boot, Resident session, worker UUID and lease ID. Acquisition is not reported as actual mute until KWS acknowledges the capture boundary. Duplicate/stale/foreign/reordered commands are tested. |
| Recognition suspension/resumption | Capture/worker locks, packet epochs, queue drains, recognizer reset, delayed-candidate cancellation and fenced publication prevent old buffered recognition from becoming a fresh accepted event. Failed ACK writes reject that hold and resume recognition after one fenced transition frame. |
| Recovery and unaffected alerts | Explicit release/disconnect, worker-enforced expiry, session replacement and backend/worker restart are tested. Authorized outboxes, real manual/critical delivery and thermal processing remain separate from recognition mute. |

Every duration used for an enabled mute in this run is a **synthetic fixture value**.
The existing two-second ACK freshness, five-second contact window and 300-second
critical replay window are not production mute lease approvals. No service was
launched with remote mute enabled, and no real recognition session was muted.

## Independent review and fixes

Two independent read-only reviewers examined actual combined source, not just
handoff reports. They reproduced failures using synthetic IPC, clocks, recognizers
and manual timers. Neither edited source or accessed production resources.

| Finding | Candidate correction and regression |
|---|---|
| FIFO request/ACK could block `open()` before file-type validation | Nonblocking, no-follow IPC open; bounded FIFO regression proves prompt invalid-data return |
| Fresh malformed ACK advertised mute availability and could raise missing-worker error | Validate worker identity, nonnegative integer epoch, Boolean state, finite timestamp/freshness and required active identities before capability/acquisition |
| Huge numeric timestamps or excessively nested JSON escaped malformed-input handling | Overflow-safe finite-number validation and recursion rejection in IPC, credentials and control-body parsing |
| ACK write failure repeatedly reset/dropped frames while claiming fail-open | Latch the failed lease, advance epoch/unmute once, return authoritative post-ACK state; succeeding frames resume without reactivating that failed hold |
| Stale delayed recognition consumed cooldown before final epoch rejection | Serialize validation/state/publication under capture gate, consistently gate → dispatcher; reject stale context before any cooldown/correlation change |
| Already-running canceled timer could consume a replacement candidate early | Bind each callback to its scheduled payload identity; obsolete callbacks leave replacement timer/payload untouched |

The ten review tests were rerun against retained pre-fix source: **0 passed,
8 failed methods, 2 errored methods**, with 13 failed assertion/subtest entries.
Fixed source was restored byte-exactly. Final focused review: **10 passed,
0 failures/errors/skips/expected failures**. One reviewer independently repeated
that ten-test pass; the other independently verified the timer race and ACK-failure
frame sequence. Both final reviews found no remaining blocker within their source
scope. Their findings and limits are retained in `independent-review.md`.

## Actual combined regression results

The final single combined process executes the candidate's source, not the original
Pi tree. Counts are test methods; subtest assertion entries are reported separately
in JSON and are not subtracted twice from pass totals.

| Run | Passed | Failed | Errors | Skipped | Expected failures | Unexpected successes |
|---|---:|---:|---:|---:|---:|---:|
| Initial expanded integration discovery, 495 methods | 458 | 3 | 33 | 1 | 0 | 0 |
| Pre-fix source review reproduction, 10 methods | 0 | 8 | 2 | 0 | 0 | 0 |
| Final review-focused, 10 methods | 10 | 0 | 0 | 0 | 0 | 0 |
| Focused ASGI/control/worker integration, 30 methods | 30 | 0 | 0 | 0 | 0 | 0 |
| **Final combined backend suite, 513 methods** | **512** | **0** | **0** | **1** | **0** | **0** |

Rows overlap and must not be added as independent coverage. The final run took
65.121 seconds. The sole skip is the pre-existing Milestone 1–2 alternate-checkout
comparison requiring `PROJECT_PI_M1M2_KWS_DIR`; that legacy checkout was not supplied.
None of the current Resident or optional ASGI cases was skipped.

The initial discovery run was not a pass. Guards blocked default audio-status,
model-path and firmware-subprocess access in expanded fixtures. The Windows replay
mock also used the older return shape. Fixtures now use an isolated shared-status
path, explicit synthetic model paths/pacing data and synthetic firmware readings.
No guard was relaxed to permit live model, audio, service or network execution.
The original unittest output reported four failed assertion/subtest entries across
three failed methods; corrected method counts and raw counters are both retained.

Final suite composition:

| Group | Methods | Final outcome |
|---|---:|---|
| Original C1.58 Pi selection | 351 | All passed; contains the retained 333 baseline |
| Previous integration-preflight contract tests | 12 | All passed; now repository-relative and retained in candidate |
| Backend smoke | 24 | All passed |
| Existing real ASGI delivery/auth/replay | 16 | All passed; previously skipped for missing dependencies |
| Windows Resident control and routes | 19 | All passed |
| Windows actual fallback-worker gate fixtures | 3 | All passed |
| Combined Pi/Windows replay-evaluation fixtures | 70 | 69 passed; one legacy-checkout skip |
| New review failure regressions | 10 | All passed |
| New actual-ASGI combined integration | 8 | All passed |

New ASGI scenarios exercise scoped roles, both TEST command kinds, explicit labels,
idempotent command identity, presentation/user ACKs, stale sequences/sessions,
default-disabled capability, malformed/oversized/nested bodies, actual worker ACKs,
release/disconnect/expiry, backend/worker restarts, thermal streaming and genuine
critical persistence/retry/replay during a fixture hold. A genuine event retains
one durable identity across retry and store/registry restart; caregiver A's
confirmation does not suppress caregiver B's recovery. Existing Pi cancellation
tests additionally verify one hub publication within their cancellation boundaries.

The exact command is retained and reproducible:

```bash
/home/thesis/offline-work-backups/C1_58_INT_MERGE_20261102T111558Z/test-venv/bin/python -B \
  /home/thesis/offline-work-backups/C1_58_INT_MERGE_20261102T111558Z/run_combined.py \
  combined-final reproduce
```

Logs/counts: `combined-final-attempt1.log` / `.json`, plus focused and red/green
artifacts in the audit directory. The runner rejects network connections, live
device/production paths, non-synthetic SQLite and process execution except the
exact candidate-local `git rev-parse HEAD` provenance query. Synthetic replay
drives fake engines/PCM only. A 45-second diagnostic stack dump during paced replay
is not a timeout failure; the full process finished successfully.

Lightweight test dependencies were installed only into the separate audit-directory
venv with existing system NumPy available. No production interpreter, package,
service or boot configuration was changed. `validation-requirements.txt` records
the installed versions, including FastAPI 0.162.0 and HTTPX 0.28.1. Framework
deprecation warnings remain in the logs; no heavy ML or Flutter SDK was installed.

## Remaining app/device tests and deployment prerequisites

Flutter and Dart are unavailable here. No combined Flutter test, Android build,
APK installation or Dart analysis result is claimed. Windows' historical software
results remain historical evidence, not a pass of this integrated candidate.
Single-tap/double-tap gesture arbitration, output plugin ordering, persisted TEST
presentation dedup and real emergency preemption need the retained Flutter suites
on this exact final source with an available toolchain. Backend command-kind tests
do not establish physical tap or siren behavior.

The earlier Pi report's provider superseded-ID replay candidate remains a separate
known app reliability follow-up: `isActive` checks the current active ID without
retained `_supersededAlertIds`. It was not silently patched without the required
Flutter reproduction/execution. Backend same-ID deduplication and source review do
not certify universal exactly-once physical siren output.

Before deployment: review the final diff/commit and configuration; run combined
Flutter/runtime/recovery tests; resolve that app replay finding; approve transport
security and private same-UID IPC/single-backend-worker ownership; arrange an
authorized production database/outbox/config backup and rollback; reconcile against
the production HEAD (different from both source tips); and obtain explicit
deployment/device-test authorization. No production mute lease duration has been
safety-approved. Keep remote mute disabled until that separate policy/timing review.

Remaining controlled device tests include real three-device routing/authentication,
native model reset/capture stalls, recognition stop/resume latency and maximum
expiry delay, actual disconnect/background/kill/restart behavior, thermal continuity,
authorized outbox recovery and emergency-over-TEST output priority. Expiry is checked
at capture boundaries; a blocked native capture/model/reset can delay progress.
Synthetic clocks do not prove a hardware time bound or acoustic accuracy.

Final verification records the original Pi, production and evaluation HEAD/branch/
status unchanged and all 37 original development hashes unchanged. No production
database/recording was accessed; no live microphone/native inference, service restart,
swap/boot change, GitHub push/merge or Android deployment occurred.

## Complete changed-file inventory

Paths below are relative to the candidate and compare its final content against
the common parent. All 44 incoming Windows paths are retained. Integration/review
additions and preserved Pi files are identified; no existing file was deleted.

| File | Source contribution |
|---|---|
| `.impeccable/design.json` | Windows |
| `DESIGN.md` | Windows |
| `android/.gitignore` | Windows |
| `android/app/build.gradle.kts` | Windows |
| `android/app/src/main/AndroidManifest.xml` | Windows |
| `docs/C1_43_offline_keyword_rearming_report.md` | Pi preserved work |
| `docs/C1_44_emergency_safe_rearming_report.md` | Pi preserved work |
| `docs/C1_45_recognition_defect_remediation_report.md` | Pi preserved work |
| `docs/C1_46_vosk_hypothesis_revision_report.md` | Pi preserved work |
| `docs/C1_47_alarm_authority_contract_report.md` | Pi preserved work |
| `docs/C1_50_runtime_safety_blocker_review.md` | Pi preserved work |
| `docs/C1_51_disconnected_observation_adapter_report.md` | Pi preserved work |
| `docs/C1_52_runtime_integration_acceptance_plan.md` | Pi preserved work |
| `docs/C1_53_pure_observation_contract_report.md` | Pi preserved work |
| `docs/C1_54_offline_recognition_integration_report.md` | Pi preserved work |
| `docs/C1_55_acoustic_validation_protocol.md` | Pi preserved work |
| `docs/C1_56_SOP_alignment_and_statistical_evidence.md` | Pi preserved work |
| `docs/C1_57_acoustic_evaluation_results.md` | Pi preserved work |
| `docs/C1_58_alert_reliability_hardening_report.md` | Pi preserved work |
| `docs/C1_58_backend_integration_preflight.md` | Pi preserved work |
| `docs/C1_58_backend_integration_report.md` | Windows |
| `docs/C1_58_resident_main_app_compatibility.md` | Windows |
| `docs/c158_flutter_ui_report.md` | Windows |
| `docs/m3_recognition_evidence_protocol.md` | Pi committed |
| `experiments/offline_recognition_mapper.py` | Pi preserved work |
| `experiments/recognition_observation_contract.py` | Pi preserved work |
| `lib/main.dart` | Windows |
| `lib/main_resident.dart` | Windows |
| `lib/models/audio_frame.dart` | Windows |
| `lib/screens/app_shell.dart` | Windows |
| `lib/screens/controls_screen.dart` | Windows |
| `lib/screens/history_screen.dart` | Windows |
| `lib/screens/monitor_screen.dart` | Windows |
| `lib/screens/resident_mode_screen.dart` | Windows |
| `lib/screens/resident_settings_screen.dart` | Windows |
| `lib/services/alert_runtime_service.dart` | Windows |
| `lib/services/mute_acknowledgement.dart` | Windows |
| `lib/services/resident_control_client.dart` | Windows |
| `lib/services/resident_monitor_service.dart` | Windows |
| `lib/widgets/alert_overlay.dart` | Windows |
| `lib/widgets/app_page.dart` | Windows |
| `lib/widgets/connection_indicator.dart` | Windows |
| `lib/widgets/led_control.dart` | Windows |
| `lib/widgets/radar_compass.dart` | Windows |
| `lib/widgets/resident_test_layer.dart` | Windows |
| `lib/widgets/thermal_display.dart` | Windows |
| `pubspec.yaml` | Windows |
| `raspberry_pi/backend/main.py` | Windows, Pi preserved work, Integration/review |
| `raspberry_pi/kws/audio_preprocessor.py` | Windows |
| `raspberry_pi/kws/kws_alert_dual.py` | Windows, Pi preserved work, Integration/review |
| `raspberry_pi/kws/replay_eval.py` | Windows, Pi committed |
| `raspberry_pi/resident_control.py` | Windows, Integration/review |
| `test/alarm_authority_contract_reference.py` | Pi preserved work |
| `test/alert_runtime_execution_test.dart` | Windows |
| `test/c158_ui_test.dart` | Windows |
| `test/disconnected_observation_reference.py` | Pi preserved work |
| `test/episode_review_support.py` | Pi preserved work |
| `test/monitor_voice_keyword_test.dart` | Windows |
| `test/resident_app_test.dart` | Windows |
| `test/resident_control_test.dart` | Windows |
| `test/resident_test_layer_test.dart` | Windows |
| `test/test_alarm_authority_contract.py` | Pi preserved work |
| `test/test_alert_reliability_hardening.py` | Pi preserved work |
| `test/test_alert_request_cancellation.py` | Pi preserved work |
| `test/test_c158_int_contract.py` | Integration/review |
| `test/test_combined_backend_integration.py` | Integration/review |
| `test/test_combined_mute_safety.py` | Integration/review |
| `test/test_disconnected_observation_adapter.py` | Pi preserved work |
| `test/test_episode_rearming_review.py` | Pi preserved work |
| `test/test_keyword_rearming_prototype.py` | Pi preserved work |
| `test/test_kws_live_paths.py` | Pi preserved work |
| `test/test_kws_recognition_regression.py` | Pi preserved work |
| `test/test_offline_recognition_mapper.py` | Pi preserved work |
| `test/test_pure_observation_contract.py` | Pi preserved work |
| `test/test_recognition_defect_remediation.py` | Pi preserved work |
| `test/test_remote_mute_kws.py` | Windows |
| `test/test_replay_eval.py` | Windows, Pi committed, Integration/review |
| `test/test_resident_control.py` | Windows |
| `test/test_runtime_safety_blockers.py` | Pi preserved work |
| `test/test_vosk_hypothesis_revision.py` | Pi preserved work |
| `test/vosk_hypothesis_reference.py` | Pi preserved work |
| `test/widget_test.dart` | Windows |
| `tools/keyword_rearming_prototype.py` | Pi preserved work |
| `docs/C1_58_combined_backend_integration_report.md` | Integration/report |


## Final status

```text
WINDOWS SOURCE IMPORTED: YES
PI RELIABILITY FIXES PRESERVED: YES
COMBINED SOURCE INTEGRATED: YES
COMBINED REGRESSIONS PASSED: YES — backend: 512 passed, 1 skipped, zero failures/errors/expected failures
REMOTE MUTE ENABLED: NO
PRODUCTION DEPLOYMENT AUTHORIZED: NO
```
