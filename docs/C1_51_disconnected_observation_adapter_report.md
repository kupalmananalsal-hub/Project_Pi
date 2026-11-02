# C1.51 — Disconnected Recognition Observation Adapter

**Decision: TEST-ONLY VERIFIED. INTEGRATION READY: NO. DEPLOYMENT READY: NO.**

The disconnected reference and synthetic tests satisfy the stated fixture contracts.
They do not correct the existing worker/dispatcher, grant alarm authority, measure
acoustic behavior or implement a durable episode coordinator. All C1.50 runtime
blockers remain deployment blockers.

Worktree: `/var/tmp/Project_Pi_C1_43_alarm_fix`.
Branch: `development/c1-43-c1-47-recognition-safety`.
HEAD: `8a44f109fae8adb4b7daa833c15548b56ccd2452`.
Date: 2026-11-02. No runtime application files were edited.

## Implementation plan and decisions

User specification: C1.51 task and C1.50 recommended disconnected milestone. Work in the existing isolated development branch without runtime edits, staging or commits.

- [x] Verify original backup/17 files and C1.50 additions; create and byte-exactly recover an incremental two-file backup.
- [x] Run the selected 245-test pre-change baseline (245 passed).
- [x] Write failing isolated tests for an observation ledger and fixture episode contract.
- [x] Implement `test/disconnected_observation_reference.py`; verify isolated tests.
- [x] Run the combined selected mocked suite; request independent read-only review and repair evidence-supported reference/test issues only.
- [x] Recheck source/repository/backup preservation and complete sections A–J.

Architecture: a pure Python standard-library observation ledger, separate publication-receipt ledger, and fixture-only episode/classification-transition contract. No sensors, models, clocks, timers, network, database, publisher callback or alarm policy in the implementation. Engines/generations/candidates are distinct keys. Original JSON payloads and fixture timestamps survive copying; sequence is ordering, not a timeout. Episode association, classification eligibility and classification callback are explicit fixture inputs. Recorded events have unresolved audible authority and are not runtime API envelopes.

Ruling: the task explicitly authorizes this disconnected implementation and separate review; implement directly from that specification without another approval cycle. Keep the implementation plan/ledger in this requested report instead of creating unrelated plan files. Existing worktree isolation and no-commit constraints take precedence over workflow scaffolding/commit defaults.

Review focus: conflicting/reordered retries must be atomic; failure must require an explicit new generation without erasing retained evidence; ordinary Vosk revisions must not change other engines; duplicate binding must not create episodes; transition identities and envelopes must remain immutable through thermal changes and replay. Cover these with negative and behavioral tests.

Implementation ledger: initial 31 tests failed with the explicit missing-reference
assertion (31 failures, zero errors). First implementation passed all 31. Independent
review then exposed type-insensitive JSON identity comparisons. Two new regression
methods reproduced four boolean/integer and integer/float conflict failures; canonical
JSON comparison repaired them. Two further methods expanded arrival-order and accepted
receipt coverage. Final isolated 35 and combined 280 tests passed. No existing source,
reference, test or report was modified to make the new tests pass.

## A. Adapter architecture

New implementation: [`test/disconnected_observation_reference.py`](../test/disconnected_observation_reference.py).
New tests: [`test/test_disconnected_observation_adapter.py`](../test/test_disconnected_observation_adapter.py).

`ObservationAdapter` has three responsibilities: validate/copied immutable observations,
maintain independent candidate views, and record submission receipts separately.
`EpisodeContract` has explicit fixture episode bindings and records immutable
classification transitions from an injected pure classifier. Its events are tagged
`fixture_classification_transition`, with `audible_authority: UNRESOLVED`; they are
not legacy `/api/alerts` input or permission to publish an emergency.

The implementation imports only `datetime`, `json` and `math`. It performs no file,
SQLite, network, model, recognizer, microphone, sensor, timer or publication I/O.
No wall clock is read. Tests inject the existing decision classifier through the
previous pure fixture helper, which creates a fresh evaluator and disables repeated
speech escalation for that helper. This is test isolation, not a proposed runtime
engine reset or a new recognition threshold.

Data flows:

```text
synthetic per-engine records -> validation -> immutable observation journal
                                        -> independent candidate views
explicit submission outcomes -----------> separate receipt journal
explicit candidate/episode binding + fixture thermal/association/eligibility
                         -> pure classification -> immutable modeled transitions
```

No event/receipt feeds back to rewrite evidence. There is no suppression timestamp
or cancellation API, so rejected outcomes cannot refresh a cross-engine veto. This
proves the disconnected contract; it does not remove existing runtime suppression.

## B. Observation schema

`ingest` requires exactly the following version-1 fields. Unknown fields, invalid
types and incomplete records fail before mutation. Plain JSON validation rejects
non-string object keys, unsupported objects and nonfinite numbers; copies preserve
JSON value types. Original key ordering is not semantic identity. A raw JSON string,
if supplied within `original_payload`, is preserved as a string, including whitespace.

| Field | Contract |
|---|---|
| `schema_version` | Integer `1`; boolean `True` is not accepted as version 1. |
| `observation_id` | Globally unique nonempty fixture identity. Exact retry is idempotent; changed content conflicts. |
| `engine` | `vosk`, `snowboy`, or `openwakeword`. |
| `generation` | Explicit engine generation identity declared with `begin_generation`. A failed generation cannot heal by redeclaration; recovery needs a new generation. Retired generations cannot reactivate. |
| `candidate_id` | Fixture candidate/utterance identity local to its engine/generation. The structured key is `(engine, generation, candidate_id)`, avoiding accidental cross-engine merging. |
| `sequence` | Positive integer ordering across one engine generation. Reordering is rejected; gaps make continuity unknown, never silence or release. Different engines have separate ordering domains. |
| `revision` | Consecutive positive candidate revision for partial/final/score observations; null for missing/gap/failure controls. Controls do not invent recognition revisions. |
| `kind` | Vosk `partial`/`final`; score-engine `score`; explicit uncertainty controls `missing`, `gap`, `failure`. No implicit silence status is inferred. |
| `observed_at` | Fixture-supplied timezone-aware ISO timestamp. Preserved exactly. Sequence orders records; timestamps do not select expiry, confirmation or association windows. |
| `original_payload` | Original JSON object, copied recursively. For Vosk detection, the appropriate `partial`/`text` field must be a string and agree with the injected pure matcher and supplied keyword. No SDK/recognizer is called. |
| `keyword` | Nonempty label or null. Ordinary Vosk revision can set null for that candidate while preserving journal history and other engines. |
| `confidence` | Supplied finite numeric value in the score domain `[0,1]`, or null. Domain validation is not a new recognition cutoff or probability calibration. Boolean scores are rejected. |
| `score_state` | `present`, `missing`, or `not_applicable`, consistent with confidence/status. Absent confidence is never replaced by zero. Missing-score detections do not overwrite retained valid model evidence. |

Candidate views distinguish latest observation/control from retained evidence:
`latest_observation_id`, `latest_kind`, `latest_score_state` versus
`evidence_observation_id`, `evidence_status`, retained keyword/confidence and revision.
They additionally export health (`ok`, `unknown`, `failed`), continuity and whether
that generation is still active. A failure can leave finalized evidence finalized
while current health is failed. Retention never implies current eligibility.

Publication receipts have exactly `receipt_id`, known `observation_id`, outcome
(`accepted`, `rejected`, `unknown`), fixture `observed_at`, and reason. They are
idempotent/conflict-checked journal entries, not durable backend receipts or authority.
Even an accepted receipt cannot create an episode or make classification eligible.

All exported records/views are independent copies. Duplicate old observations are
accepted without rewinding a later revision, including an already retired generation's
previously recorded exact retry. New observations from retired generations are rejected.
Final candidates cannot reopen; a new call needs a new fixture candidate identity.

## C. Independent-engine safety invariants

1. **No cross-engine evidence cancellation:** candidate keys and source ordering are
   partitioned. A Vosk tulong-to-tulog revision affects only that candidate. Both
   Snowboy/openWakeWord help remain present in all six before/between/after subcases.
2. **Rejected publication cannot refresh suppression:** receipts change only the
   receipt journal. No suppression state exists in the reference. Independent help
   remains classifiable when the fixture explicitly permits it.
3. **Missing scores are not silence:** null/missing controls retain the last valid
   evidence and mark uncertainty. No release, episode closure or zero score is created.
4. **Failure does not erase evidence:** source health becomes failed, while evidence
   and original finality remain inspectable. New detection requires a new generation;
   stale callbacks cannot reactivate an old generation. Whether retained voice remains
   eligible is an explicit fixture verdict, never inferred from failure or retention.
5. **Traceable revisions:** consecutive revisions retain the same structured candidate;
   ordinary final text invalidates that candidate's current keyword, not prior records
   or other engine evidence. Delivered modeled events are immutable.
6. **Finality is explicit:** partial/final status survives normalization and later
   health controls. A stipulated genuine partial-only fixture stays provisional.
   No assertion establishes real acoustic ground truth or timely siren output.
7. **Duplicates do not fabricate episodes:** ingestion never creates episodes.
   Exact binding retry is a no-op; one candidate cannot be rebound as a second episode,
   and an episode cannot merge another candidate/engine. New independent episodes
   require explicit new candidate and episode identities.

This is a fixture contract rather than acoustic segmentation. An adapter cannot prove
that a supplied candidate/episode boundary corresponds to a real new distress call.

## D. Thermal reevaluation contract

`bind_episode(episode_id, candidate_key)` is an explicit fixture association, not an
automatic clustering rule. `reevaluate` requires both boolean `association_valid`
and `classification_eligible`. Omitting them, passing non-booleans, or referring to
unknown episodes is an error. False verdicts prevent classification/events; no default
authority decision or evidence lifetime is invented.

Thermal records require `thermal_id`, supplied aware `observed_at`, and a JSON
`payload`. Same-ID changed data conflicts before invoking the classifier. This wrapper
does not itself validate real thermal model output, freshness, person identity or
cross-sensor association. Tests pass explicit fixture thermal states through the
existing classifier. Repeated frames may be reclassified, but cannot add speech
observations or duplicate an already recorded episode/level transition.

The identity distinctions are:

| Identity | Meaning | Demonstrated behavior |
|---|---|---|
| Observation | Immutable recognition evidence, engine/generation sequence and original payload | Retry does not add observations or rewind a revision. |
| Candidate | Revisable recognition hypothesis within an engine generation | Partial tulong and final tulog share a traceable candidate. |
| Episode | Explicit fixture grouping for one candidate | Independent new episodes remain eligible; duplicate evidence cannot create them automatically. |
| Immutable event | Modeled classification transition for an episode/level | Advisory retains its ID/envelope; critical receives a different deterministic fixture ID. |

Transition deduplication occurs **after classification**, on `(episode_id, level)`.
Critical is not repeatedly emitted for identical/equivalent positive frames, and a
later negative frame does not downgrade/rearm a critical episode. Distinct explicit
episodes can each record critical transitions from the same thermal fixture. The
classifier can update candidate decisions without mutating older transition events.

Classification is not actuation: every event retains `audible_authority=UNRESOLVED`,
and a receipt does not change it. Events have a fixture-only tag and no legacy
`keyword_detected` dispatch action. Callback inputs/outputs are copied, and callback
failure leaves thermal/transition journals unchanged. The model does not own delivery
ACKs or publication success and does not claim crash/transaction/concurrency safety.

Synthetic backend integration tests AST-extract the existing `AlertStore`, insert
these explicitly test-only envelopes into a newly created temporary store, retry a
critical event and reopen/replay the store. Same-ID/same-content remains one row;
changed fingerprint conflicts. Confirming advisory does not confirm critical. This
validates storage identity preservation only: no real API startup, WebSocket outage,
device, notification, alarm or Flutter output is exercised.

## E. Synthetic test evidence

| Required scenario | New test evidence |
|---|---|
| Partial tulong revised to tulog | Same candidate, two immutable observations; final view has no keyword. Other engine help survives. |
| Genuine partial-only tulong | Stipulated positive fixture remains retained as partial, with no invented final or automatic publication receipt. |
| Snowboy/openWakeWord help after ordinary speech | Six engine/arrival-order subcases cover before, between and after the Vosk ordinary revision, preserving help in every case. |
| Rejected Vosk submission before help | Rejected receipt cannot change candidate views; independent help can form explicitly eligible fixture episodes. Accepted receipt also does not grant eligibility or audible authority. |
| Engine failure/recovery | Retained old evidence remains failed/inspectable; fresh generation accepts new observations, while old-generation resumption and reactivation fail. |
| Missing score | Explicit missing control retains prior model score/evidence identity; initially absent score cannot invent a classification. |
| Repeated identical observations | Old exact retry leaves later revision intact; same candidate binding is idempotent and cannot create another episode. |
| Advisory then positive thermal | Advisory event remains unchanged; distinct critical ID references the same episode/observation. |
| Repeated unchanged thermal | Same frame, equivalent positive frames and flapping do not create another critical event. Observation count stays unchanged. |
| Backend retry/replay | Real AST-extracted temporary store retains two immutable transition IDs across retry/reopen/replay; critical recovery remains eligible despite advisory confirmation. |
| Two independent emergencies | New candidate and explicit new episode both remain eligible, with different critical event IDs. |
| Validation/atomicity | Version/types, score domain, unknown fields, non-string JSON keys, timestamp awareness, order/revision conflicts and finality violations are rejected without state mutation. Mutation of caller/exports/callback copies cannot rewrite evidence/events. |
| Typed identity conflicts | Nested true-versus-1 and 1-versus-1.0 changes conflict for observations and thermal frames before classifier invocation. Exact retries still succeed. |

Test score/time values are synthetic examples, not selected operating parameters.
No acoustic accuracy, miss reduction, latency improvement or preserved real-world
distress recall is claimed. Test execution duration is not emergency latency.

## F. Regression results

| Run | Tests | Failures / errors | Skips / expected failures / unexpected successes |
|---|---:|---:|---:|
| Prior selected baseline before new implementation | **245** | **0 / 0** | **0 / 0 / 0** |
| Initial adapter tests before reference existed | 31 | 31 / 0 | 0 / 0 / 0 |
| First adapter implementation | 31 | 0 / 0 | 0 / 0 / 0 |
| First combined selected run, before review fixes | 276 | 0 / 0 | 0 / 0 / 0 |
| Review identity-conflict reproduction | 2 methods, four typed-conflict subcases | Four expected assertion failures / 0 errors | 0 / 0 / 0 |
| Final isolated adapter suite | **35** | **0 / 0** | **0 / 0 / 0** |
| Final combined selected suite | **280** | **0 / 0** | **0 / 0 / 0** |

Initial missing-reference failures demonstrate absent implementation, not runtime
defects. Review found an actual blind spot after the first green suite; both its
reproduction and repair are reported rather than relying on the initial 276 passes.

Focused command:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest test.test_disconnected_observation_adapter -q
```

Final selected suite, from the development worktree (omit the new module to reproduce
the prior 245-test selection):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest \
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

Actual baseline/combined runs loaded these exact names through unittest, captured
diagnostics in memory, disabled bytecode, and placed default temporary fixtures under
temporary development-worktree directories. Existing explicit ROOT fixtures also stayed
in the worktree. Audit guards rejected network/DNS, subprocesses, production access,
model/recording extensions and SQLite outside the worktree. No broad discovery or real
backend/engine initialization occurred. Existing malformed-policy fixture warnings are
expected tests, not changes to deployed configuration. Temporary stores/outboxes were
cleaned by fixture contexts. No retained fixture directories or bytecode additions remain.

## G. Separate read-only review findings

A fresh reviewer inspected the reference/tests and performed pure `python -B` probes,
without file/Git writes, SQLite fixtures, production access or model/network/hardware.

**Confirmed P2:** Python dictionary equality conflates JSON boolean/integer and
integer/float values (`True == 1`, `1 == 1.0`). An altered retry could pass the old
identity check; thermal data could reach the classifier and overwrite its retained
frame under the same ID. This violated immutable original-payload identity.

**Repair:** `_same_json` compares canonical JSON with types preserved, used for
observations, thermal frames and receipts. Added nested type-conflict regressions
first failed as intended, then passed. The reviewer independently rechecked all four
conflict cases, confirmed no journal/candidate/receipt/event/callback-count mutation,
and confirmed exact duplicate retry remains accepted. No remaining review findings.
The final focused/combined test counts above were run by the implementer, not claimed
as reviewer-run suites. Only this milestone's reference/tests were changed for the fix.

## H. Unresolved acoustic and integration validation

- Provisional-only distress may be genuine or may later revise. No final-only filter,
  stability timeout, repetition count or confidence threshold can be selected from
  these fixtures. Audible emergency authority remains unresolved.
- Matcher labels and scores here are supplied synthetic values, not measured ASR
  confidence, cross-engine independence or evidence of actual recall/precision.
  Exact-only matching still needs authorized representative acoustic validation.
- Candidate/episode boundaries, recovery generations, clocks, thermal association,
  freshness/eligibility lifetime and genuine release remain explicit fixture assumptions
  until reviewed and empirically supported. Missing/gap/failure is never proof of silence.
- Runtime still discards Vosk finality before publication and can veto independent help;
  rejected submissions can refresh that veto. No runtime suppression was fixed here.
- Runtime thermal updates still do not autonomously upgrade authoritative advisories.
  New classification records are not a durable single-owner thermal coordinator.
- The model is unbounded, in-memory, single-threaded and non-durable. No restart atomicity,
  journal recovery, concurrent ingestion, bounded retention or production migration is
  implemented. The classifier must be pure; this reference cannot enforce purity of an
  arbitrary external callback. No identity generator or trusted clock is implemented.
- Existing immutable event/ACK/replay/manual/critical contracts must survive future
  integration. Storage fixtures do not validate Flutter background permissions,
  audible/vibration output, process death or physical latency.

Representative acoustic/model replay requires separate authorization, approved
provenance/consent, frozen versions, speaker/session separation, existing vocabulary,
contextual negatives and interrupted/partial-only calls, with acceptance criteria
declared before measurement. No such data were accessed or experiment run here.

## I. Git and backup preservation verification

Original backup verified before and after work:
`/home/thesis/offline-work-backups/C1_48_R_20261102T011740.344081Z`.
All **41 artifact checksums**, manifest completeness, archive and retained recovery
checks pass. Its `SHA256SUMS` SHA-256 remains:
`ee49731c9348f23b65d5df6d67871075bc7a15ca1206f57d3922428ebd4b0772`.
All original **17/17** offline changed files retain path/type/size/mode/SHA-256.
The earlier failed backup also retains its recorded artifact hashes.

Before implementation, the two C1.50 additions were checked against their C1.50 hashes:

| File | Bytes | SHA-256 |
|---|---:|---|
| `docs/C1_50_runtime_safety_blocker_review.md` | 38521 | `f1bae1fc91696390ad5f9db10d390a8d531185087e7871a5c7effd8ed18ea87b` |
| `test/test_runtime_safety_blockers.py` | 15377 | `f772f5dcfd49d7e5e62b2cd6af30a53c15d10b0620648a8c187e8f51df70d81f` |

Incremental backup created outside all three project checkouts:
`/home/thesis/offline-work-backups/C1_51_incremental_20261102T014123.101687Z`.
It contains the two-file raw binary archive, inventory/type/permission/hash metadata,
HEAD/status, verification, restoration instructions and retained `verified-recovery/`.
Both recovered files matched originals byte-for-byte, including type, size, SHA-256
and mode. All **8 artifact checksums** and manifest completeness passed again after
testing. Its `SHA256SUMS` SHA-256 is:
`c217a060934c96c87bd15fced50c0ede3d744f37d67c3c5dee3928b1c772600a`.
Manifest files exclude only themselves; their hashes are recorded here. Every file
was fsynced, with backup directory metadata flushed before phase 0 passed. No old
backup artifact was modified or replaced. This is local preservation, not off-host
redundancy. The new C1.51 artifacts are not part of either sealed earlier snapshot.

Restoration: follow the incremental `RESTORE.md` using Python standard-library binary
tar extraction into a NEW empty target; require exactly the inventory members and
compare their bytes/types/sizes/modes/hashes. Verify all `SHA256SUMS` lines first.
Combine with the original 17-file backup for C1.43–C1.50 preservation. No Git/network
operation is needed to recover the preserved changed files.

Fresh before/after SHA-256 comparison of **197 pre-existing tracked Python/Dart/Markdown
files** found no changes. Original binary tracked diff remains backup-identical.
Offline index/HEAD/branch remain unchanged, with no staged changes or unexpected ignored
files. Existing 19 artifacts are intact; only these three C1.51 files were added:

1. `test/disconnected_observation_reference.py`
2. `test/test_disconnected_observation_adapter.py`
3. `docs/C1_51_disconnected_observation_adapter_report.md`

| Checkout | Verified state |
|---|---|
| Production `/home/thesis/Project_Pi` | `main`, `1a5c3095a27421cb4c667ee6caed14169729e774`; no tracked changes, same index and Git status. Four pre-existing untracked model/database paths remain; contents were not opened. |
| Evaluation `/var/tmp/Project_Pi_M3_eval` | `main`, `8a44f109fae8adb4b7daa833c15548b56ccd2452`; clean, same index/HEAD/status. |
| Offline development worktree | Requested branch, same baseline HEAD/index and original candidate modifications; exactly the three authorized C1.51 additions. |

Git reads used explicit checkout paths and optional locks disabled. Offline and
evaluation share Git metadata but separate files/indexes; no refs/config were changed.
No discovery-based apply/checkout was used under the enclosing `/home/thesis` repository.
No staging, commit, push, pull/fetch, merge/rebase/reset/clean, deployment, services,
microphone, actual model inference, restricted recording/production database access,
swap, Docker or boot changes occurred. Backup writes were limited to the new incremental
directory; implementation/report/test additions were limited to the development worktree.

## J. Recommended C1.52 milestone and decision

**Recommended C1.52: disconnected observation/coordinator boundary hardening.**
Retain test-only status. Specify and test a versioned transport/receipt boundary,
atomic observation-to-transition state recovery and serialized ingestion using new
synthetic stores, while preserving source/engine independence and immutable events.
Use deterministic crash/retry/out-of-order/concurrency fixtures and explicit association/
eligibility verdicts; do not introduce live recognition, sensor ownership or alarm
actuation. Review bounded retention and provenance requirements without silently
discarding unresolved evidence. Do not reuse classification records as `/api/alerts`.

Before any worker/dispatcher/backend integration, separately review the A–E gates
in C1.50 and define the accepted independent-evidence/submission outcome contract.
Any later cancellation fix needs its own narrow tests and review; this ledger does
not authorize changing alarm behavior. Plan, but do not execute without authorization,
the acoustic protocol needed to resolve provisional authority, episode/association
semantics and the exact-only matching recall tradeoff.

Final status:

- **TEST-ONLY VERIFIED: YES**, for the explicit synthetic contract and test selection.
- **INTEGRATION READY: NO**, because runtime wiring, durability, concurrency, trusted
  provenance and association/authority contracts are unresolved.
- **DEPLOYMENT READY: NO**, because acoustic and end-to-end emergency acceptance,
  approved authority policy and deployment authorization are absent.
