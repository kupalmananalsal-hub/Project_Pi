# C1.53 — Pure Recognition Observation Contract

**TEST-ONLY VERIFIED: YES**

**INTEGRATION READY: NO**

**DEPLOYMENT READY: NO**

Only the pure experimental boundary was implemented. The selected prior 280 tests
and final combined 308 tests passed; the new focused suite has 28 passing tests.
No runtime application, backend, delivery, database schema or Flutter code was changed.

Worktree: `/var/tmp/Project_Pi_C1_43_alarm_fix`.
Branch: `development/c1-43-c1-47-recognition-safety`.
HEAD: `8a44f109fae8adb4b7daa833c15548b56ccd2452`.
Date: 2026-11-02. All inputs are synthetic; no acoustic outcomes were measured.

Plan: implement only the first C1.52 boundary, adapted to the user's explicit experimental-package requirement. Create `experiments/recognition_observation_contract.py`, `test/test_pure_observation_contract.py`, and this report. No thermal, classification, episode, outbox, backend, delivery or authority implementation.

- [x] Verify 41/8/10 backup checksums, 23 existing artifacts and byte-exact incremental preservation of C1.52.
- [x] Run prior 280-test selected baseline.
- [x] Write/observe failing synthetic contract tests, then implement the pure module.
- [x] Run isolated and combined selected suites; perform static boundary checks.
- [x] Obtain separate read-only review and repair reproduced issues only.
- [x] Verify unchanged sources/checkouts/backups; record new file hashes and final A–J findings.

Design decisions: supplied identity/finality/health/provenance are data, not detection truth or alarm authority. Strict plain JSON identity is type-sensitive. Candidate keys include engine, producer, generation and local candidate ID. Source sequence orders one generation; exported records use deterministic source-key/sequence ordering rather than claiming a global acoustic timeline. Failed generations require explicit replacement and cannot silently heal. Receipts are only in-memory records. There is no episode or publication API. All state and returned values are detached from caller-owned structures.

Ruling: execute the user's fully specified pure experimental boundary directly; do not add approval cycles, runtime wiring, commits or unrelated workflow artifacts. Keep the plan/ledger in this requested report. Existing C1.50–C1.52 references inform invariants but are not imported or modified.

Execution ledger: initial 27 tests failed at the explicit absent-module assertion
(27 failures, zero errors). First implementation passed all 27 and combined 307.
Independent review reproduced the inability to represent detector-only recognition
with absent confidence. A new test failed for that missing status, then passed after
an explicit non-ASR `detection` status was added. Final focused 28 and combined 308
passed. Only new module/test/report files were edited, including for the review repair.

## A. Exact new module and test paths

| File | Purpose |
|---|---|
| [`experiments/recognition_observation_contract.py`](../experiments/recognition_observation_contract.py) | Standalone standard-library contract and in-memory `EvidenceLedger`. `experiments` is a Python namespace package; no application package initialization or packaging configuration was added. |
| [`test/test_pure_observation_contract.py`](../test/test_pure_observation_contract.py) | 28 synthetic tests, including independent engine interleavings and purity checks; no application imports or database fixtures. |
| `docs/C1_53_pure_observation_contract_report.md` | This report and implementation/verification ledger. |

Public module surface:

```text
canonical_identity(plain_json_value) -> canonical JSON string
validate_observation(raw_mapping) -> detached validated observation
EvidenceLedger.begin_generation(engine, producer_id, generation_id)
EvidenceLedger.ingest(observation) -> in-memory recorded/duplicate receipt
EvidenceLedger.candidate((engine, producer_id, generation_id, candidate_id)) -> copy or None
EvidenceLedger.record_publication_receipt(supplied_receipt) -> copy
EvidenceLedger.snapshot() -> detached deterministic evidence snapshot
```

The implementation imports only `datetime`, `json` and `math`. Datetime is used only
to parse supplied timestamps, never to read the clock. There are no application/test
reference imports, filesystem/database/network/subprocess APIs, model/microphone
dependencies, publication callbacks, classifier or thermal functions.

## B. Scope and integration boundary

This is an experimental subset of C1.52 S1, under the user's explicit non-runtime
package requirement. It implements representation, structural validation and independent
memory bookkeeping, not the full proposed production ObservationV1 transport schema
or any of S2–S9. No new source/config/policy/score threshold or timeout was selected.

The strict version-1 input fields are:

```text
schema_version=1, record_type=recognition_observation,
observation_id, engine, producer_id, generation_id, candidate_id,
sequence, revision, status, observed_at, clock_domain, capture_range,
original_payload, keyword, confidence, score_state, health
```

- Identity strings must be nonempty; observations are globally identity-keyed.
  Candidate keys include engine, producer, generation and local candidate ID.
  A generation must be explicitly declared before new input is accepted.
- `status` is Vosk `partial`/`final`, non-ASR `score`/`detection`, or explicit
  `missing`/`no_detection`/`gap`/`failure`. A non-ASR detection cannot claim ASR
  finality. Control records have no invented keyword, confidence or recognition revision.
  Engine-wide controls may use null candidate ID without fabricating a candidate.
- `confidence` is an optional **declared normalized confidence-domain value** in
  `[0,1]`; this validation is not a recognition cutoff or calibration claim. `score`
  requires an actually present value; `detection` can preserve a known detector label
  with absent confidence. ASR can also have missing confidence. A model with an absent
  score uses explicit `missing`, not zero. Raw uncalibrated scores, detector indices,
  model/config identifiers or calibration details remain opaque in `original_payload`;
  the module does not convert them to normalized confidence or validate a complete
  production provenance schema. Future engine adapters need a separately reviewed schema.
- `health` is explicit `healthy`, `unknown`, `unavailable` or `failed`, constrained
  consistently with status. Healthy no-detection and failed engine are different facts.
  A detection's missing confidence does not manufacture a score or invalidate readable
  ASR health. Missing model score and missing normalized detector confidence are explicit.
- Supplied aware ISO `observed_at`, named clock domain and optional nonnegative
  `{first,last}` capture range are preserved. No timestamp ordering, cross-clock
  association, age, confirmation delay or episode boundary is inferred.
- All original payload data are copied without label inference. The module does not
  run a matcher or verify semantic agreement of text and a supplied label. It preserves
  the evidence needed for a future reviewed adapter to do that. Pure tests use declared
  fixture labels, not recognized audio or acoustic ground truth.

`canonical_identity` rejects cycles, nonfinite numbers, non-string object keys and
non-JSON objects rather than silently coercing them. It distinguishes booleans,
integers and floats. Object key order is immaterial; raw JSON text supplied as a
string remains exact text. Stored observation/receipt representations are canonical
strings, preventing retained aliases to caller-owned mutable values.

Snapshots contain only observations, candidate views, generation metadata and supplied
publication receipts. They contain no episodes, classification, alert events, persistence
state, thermal associations, suppression timers or authority verdicts. The `recorded`
ingest receipt explicitly identifies itself as an **in-memory** observation receipt;
it is not a durable transport ACK or backend acceptance.

**Unresolved evidence never enters a live path here.** No observation is inserted into
the alert store, sent to `/api/alerts`, live history, polling, replay, WebSocket or
Flutter. Do not infer safety from `record_type`: existing consumers can interpret
ordinary alert-shaped data irrespective of experimental metadata. Structural absence
of runtime callers and I/O is the boundary. A future consumer must never route these
records to legacy alert processing or give them an authoritative `decision_state`.

## C. Enforced safety invariants

| Required invariant | Enforced behavior and limits |
|---|---|
| One engine cannot erase another's evidence | Source/candidate keys are partitioned. All accepted original observations remain retained; one candidate revision changes only its view. |
| Provisional Vosk cannot veto help | Six before/between/after cases preserve Snowboy/openWakeWord labels. There is no cross-engine cancellation function. This does not repair the current application's dispatcher. |
| Rejected publication cannot refresh suppression | Receipt ingestion changes only its own journal. There is no suppression state; accepted/unknown receipts also supply no authority. |
| Missing is not silence | Null/missing is not zero. Controls retain prior evidence and mark latest status; they cannot close an episode or declare release. Retention is not a current eligibility verdict. |
| Failed generation differs from healthy no-detection | Failure is explicit, latched for that generation; redeclaration cannot heal it. New generation recovery is explicit, old evidence stays inspectable, and retired generations cannot reactivate. |
| Candidate revisions are not episodes | Consecutive revisions remain under one key. ASR final closes recognition revisions, not an acoustic episode. The module has no episode/history-counting API. |
| Exact retries are idempotent | Same identity and canonical content returns duplicate without appending or rewinding state; old exact retries do not heal/reopen failed/retired evidence. |
| Identity conflict is explicit | Changed content under the same observation/receipt identity raises ValueError before mutation. New independent candidates still require explicit identities and source order. |
| Typed JSON identity | Nested true/1 and 1/1.0 changes conflict; dictionary key reordering remains an exact JSON-value retry. |
| Mutation isolation | Inputs, snapshots, candidate views, validation results and returned receipts cannot mutate retained structures. Stored canonical strings and fresh JSON copies preserve this boundary. |
| No critical alert operation | No event creation, classification, authority, persistence or send function/callback exists; only observation/receipt data can be returned. Original opaque payload text is not executed or published. |
| Deterministic supplied ordering | Source sequence must increase within one producer/generation; candidate revisions are consecutive. All 12 valid cross-engine schedules produce the same canonical snapshot. This is not multithreaded correctness. |

An observed sequence gap marks continuity false, never silence or release. Out-of-order
new inputs are rejected atomically; no persistent pending/reconciliation layer is
implemented. Clock domains and capture ranges are preserved, not proof that all real
packets arrived. Export order is lexical engine/producer/generation/source sequence,
not a global acquisition or acoustic timeline.

## D. Synthetic test evidence

| Scenario | Observed outcome |
|---|---|
| Partial tulong → ordinary final tulog | Same candidate retains both observation IDs/revisions; latest recognized keyword becomes null and finality remains explicit. |
| Partial tulong without final | Stays provisional data with one revision; no event or decision state is created. Genuine ground truth is stipulated only, not measured. |
| Independent Snowboy/openWakeWord help | Help remains under its own engine in all six before/between/after Vosk revision cases. |
| Rejected publication | Observation/candidate/generation snapshots are unchanged; rejection is a separate supplied receipt. |
| Engine failure and recovery | Old finalized evidence remains finalized with failed health; implicit healing/no-detection is rejected, fresh generation is healthy only after explicit new input. No episode is created. |
| Healthy no-detection | Remains distinct from failed generation and creates no fake recognition candidate when candidate ID is null. |
| Missing/malformed scores | Missing control preserves prior score; zero stays a present score; booleans, nonfinite/out-of-domain values and contradictory states are rejected without mutation. |
| Detector-only positive | Snowboy `{detector_index:1}`, help label and absent confidence are retained as non-ASR detection with `score_state=missing`; no score or finality is invented. |
| Duplicate/conflicting identity | Exact old retry cannot rewind final revision; changed payload or typed nested JSON content conflicts. |
| Out-of-order/gap/revision/finality | Reordered sequence and invalid revision/final reopening fail atomically; a gap retains evidence with discontinuity. |
| Mutation | Caller payload/capture changes and mutations of exported observations, candidate history or receipts do not change ledger state. |
| Distinct candidates/producers | Local candidate names on different producers are not merged; a new explicit candidate gets separate revision history. |
| Simultaneous independent evidence | Twelve deterministic valid sequential interleavings have identical final snapshots. No real threads, race scheduler or runtime inference is exercised. |
| Pure static surface | Module import allowlist is datetime/json/math; no forbidden I/O/time/publication calls or extra coordinator class. |

No acoustic accuracy, latency, false-activation or miss-rate result is claimed. The
fixture confidence/timestamp values are examples, not chosen operating constants.

## E. Baseline and final regression totals

| Run | Tests | Failures / errors | Skips / expected failures / unexpected successes |
|---|---:|---:|---:|
| Prior selected baseline | **280** | **0 / 0** | **0 / 0 / 0** |
| Before module implementation | 27 | 27 / 0, expected absent-module assertions | 0 / 0 / 0 |
| Initial focused implementation | 27 | 0 / 0 | 0 / 0 / 0 |
| Initial combined selection | 307 | 0 / 0 | 0 / 0 / 0 |
| Detector-only repair reproduction | 1 | 1 / 0, expected missing-status failure | 0 / 0 / 0 |
| Final focused suite | **28** | **0 / 0** | **0 / 0 / 0** |
| Final combined selected suite | **308** | **0 / 0** | **0 / 0 / 0** |

The detector-only test initially exposed ValueError for unsupported status; its explicit
failure assertion then documented the missing feature before the implementation repair.
Initial RED failures do not claim defects in the unchanged application. Final suite
duration was 13.776 seconds; that is software execution time, not emergency latency.

Focused command from the development worktree:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest test.test_pure_observation_contract -q
```

Final combined selection (omit only the new module to reproduce the prior 280):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest \
  test.test_pure_observation_contract test.test_disconnected_observation_adapter \
  test.test_runtime_safety_blockers test.test_alarm_authority_contract \
  test.test_vosk_hypothesis_revision test.test_recognition_defect_remediation \
  test.test_episode_rearming_review test.test_keyword_rearming_prototype \
  test.test_kws_event_id test.test_keyword_fusion test.test_kws_live_paths \
  test.test_kws_recognition_regression test.test_alert_decision \
  test.test_alert_trace test.test_alert_publication \
  test.test_alert_delivery.DeliveryStorageTest.test_restart_retains_full_envelope_and_uuid \
  test.test_alert_delivery.DeliveryStorageTest.test_concurrent_duplicate_and_conflicting_uuid \
  test.test_alert_delivery.DeliveryStorageTest.test_independent_acks_survive_restart \
  test.test_alert_delivery.DeliveryStorageTest.test_replay_policy_boundaries \
  test.test_alert_delivery.DeliveryStorageTest.test_recovery_cursor_ignores_presentation_but_respects_confirmation_and_age
```

Actual baseline/combined invocations load these exact unittest names, capture output
in memory, disable bytecode and redirect default temporary fixtures below the offline
worktree. Existing explicit ROOT fixtures remain there too. Audit guards reject network,
DNS, subprocesses, production reads, model/recording extensions and SQLite outside the
worktree. The **new focused tests use no database fixtures**; selected prior tests use
only freshly created synthetic SQLite stores/outboxes, never production databases.
Those fixtures are cleaned by their contexts. No broad discovery, model/recognizer
initialization, microphone, Flutter/device tests or runtime source edits occurred.
Existing malformed-policy warnings are expected synthetic tests, not deployed changes.

## F. Independent review findings

A separate reviewer read source/tests and ran pure `python -B` synthetic probes without
file/Git writes, databases, services, network, hardware or production access.

The reviewer independently reproduced a **representational gap**: a known Snowboy
positive without normalized confidence had no valid form. ASR partial/final was not
appropriate, `score` required a present value, and missing controls could not carry a
known label. The explicit non-ASR `detection` repair avoids inventing confidence.

The reviewer rechecked the valid detector-only case and rejected eight invalid boundary
cases, including Vosk detection, Snowboy ASR finality, score without score, detection
without label, contradictory score states and failed successful recognition. A later
missing control retains the prior label. Independent probes also confirmed exact retry
after failure, failed/retired generation behavior, return isolation and typed JSON
identity. No remaining material findings in the repaired module/tests.

Schema-scope note from review: this is not a complete production wire schema for every
engine. Typed model/config/calibration metadata and raw-score domain adaptation remain
future work. Arbitrary SDK score/index values must not be coerced into the declared
normalized confidence field. Test counts and preservation results were executed by the
implementer, not attributed to the reviewer. The reviewer also read the final report,
confirmed its scope/status/evidence distinctions and module/test hashes, and found no
material discrepancies. No additional suites or writes were performed by the reviewer.

## G. Static import-boundary verification

Checked tracked offline application sources: **30 Python files** under `raspberry_pi/`
and **67 Dart files** under `lib/`. No source text references the new module; Python
AST imports contain no `experiments` package dependency. Current KWS/backend entrypoints,
delivery paths and Flutter therefore have no new import/call site. The new module's
public surface is exactly `canonical_identity`, `validate_observation`, `EvidenceLedger`.
Its AST imports are only datetime/json/math; focused static tests reject filesystem,
dynamic execution/import, network, clock-read and publication call sites.

This is supported by byte-for-byte before/after preservation of all **197 pre-existing
tracked Python/Dart/Markdown files**, including backend/main.py (database schema/API),
alert_delivery.py, KWS and all Flutter source. The existing binary tracked diff remains
identical to the sealed original candidate. No new backend schema/migration or runtime
configuration was added. The experimental namespace directory has no initializer,
packaging registration, entrypoint or application plugin hook.

Thus no current polling, replay, live/legacy/WebSocket or Flutter consumer can read
this ledger through an added integration, and no siren lifecycle function changed.
Static absence and source preservation are scoped to the checked tree; this is not
an execution sandbox or a claim that future callers could never misuse returned data.

Future interface only, **not implemented/wired**:

```text
FutureEngineAdapter.describe_result(existing_engine_result, supplied_source_context)
    -> recognition observation JSON values
validate_observation(values) -> detached validated record
FutureDurableObservationPort.accept(record) -> separate durable typed receipt
```

Any future adapter must retain engine-specific raw score meaning, model/config and
capture provenance, preserve independent evidence, distinguish segment/reset from
acoustic episode, and supply identity before transmission. It must not use this
in-memory receipt as a durable ACK or route data to `/api/alerts`. No thermal, episode,
authority or alert interface is defined by this module.

## H. Backup and Git preservation verification

Before implementation, all sealed manifests passed exact hash/completeness checks:

| Backup | Artifacts checked | SHA-256 of SHA256SUMS |
|---|---:|---|
| `/home/thesis/offline-work-backups/C1_48_R_20261102T011740.344081Z` | 41 | `ee49731c9348f23b65d5df6d67871075bc7a15ca1206f57d3922428ebd4b0772` |
| `/home/thesis/offline-work-backups/C1_51_incremental_20261102T014123.101687Z` (C1.50 files) | 8 | `c217a060934c96c87bd15fced50c0ede3d744f37d67c3c5dee3928b1c772600a` |
| `/home/thesis/offline-work-backups/C1_52_incremental_20261102T020020.894305Z` (C1.51 files) | 10 | `aace26d4a970bbcf7fdd7a6698b9c413c1ef4db6ccadddc050d1c329ce49866d` |

All **23 prior source artifacts** match the sealed inventories and C1.52 completion
hash. New incremental backup, outside the three project checkouts:
`/home/thesis/offline-work-backups/C1_53_incremental_20261102T021726.563255Z`.

It preserves the C1.52 report (54163 bytes, SHA-256
`93fd473069ce85a7849a5303e722e174a047ec718d2d559fd8d852874ce8bc49`)
as a raw regular-file archive with inventory/type/mode/HEAD/status metadata and retained
byte-exact recovery. **8 new artifact checksums** pass. SHA-256 of its SHA256SUMS:
`1b154f50c5e10a973ae7b1d19494b30c5a31a78914f398526c5f235a6e35c243`.
File and directory metadata were flushed before phase 0 passed. Restore through its
`RESTORE.md` into a NEW empty target using standard-library binary tar extraction,
then compare exact inventory membership, type, bytes, size, permissions and hashes.
No Git/network operation is needed. These snapshots preserve changed files, not full
Git history or off-host redundancy. No old backup artifact was overwritten/deleted.

Final preservation repeats all manifest/source checks, confirms the earlier failed
backup hashes, checks no extra ignored/staged files, and confirms only the three
authorized C1.53 additions. Existing 23 artifacts and 197 tracked source/doc hashes
remain unchanged. New module/test hashes:

| File | Bytes | SHA-256 |
|---|---:|---|
| `experiments/recognition_observation_contract.py` | 12931 | `0490a30e4834e2731b7757258d1601f7b1fcaf0b368a97c108354be170244fc3` |
| `test/test_pure_observation_contract.py` | 17792 | `82886ca6474c0a53664af5df95f95c66826d3c0d7619771c9f3016927bbdf6e8` |

The third new file is this report. Its final complete-file SHA-256 is recorded in the
completion receipt rather than attempting an impossible self-referential checksum.
No current C1.53 file is implied to belong to the sealed earlier snapshots.

| Checkout | Preserved state |
|---|---|
| Production `/home/thesis/Project_Pi` | `main`, `1a5c3095a27421cb4c667ee6caed14169729e774`; tracked clean, same index/status; four pre-existing untracked private model/database paths inventoried only, contents not opened. |
| Evaluation `/var/tmp/Project_Pi_M3_eval` | `main`, `8a44f109fae8adb4b7daa833c15548b56ccd2452`; clean, same index/status. |
| Offline | Requested branch and same baseline HEAD/index; prior candidate modifications intact, plus exactly this milestone's three additions. |

All Git queries use explicit checkout paths and optional locks disabled; nothing
relies on enclosing `/home/thesis` discovery. No ref/config/staging/commit/push,
fetch/pull/reset/merge/rebase/clean, deployment, service restart, model inference,
microphone, restricted recording/production database/credential/queue access, swap,
Docker or boot changes occurred. Existing original modifications remain uncommitted.

## I. Remaining integration and deployment blockers

- Pure memory does not establish durable transactional storage, crash recovery,
  bounded retention, replay protocol or real concurrency correctness. Out-of-order
  reconciliation is explicitly future work; this ledger rejects rather than persists
  pending input. Twelve sequential schedules are not a thread/process stress test.
- Generation/source/candidate IDs, acquisition clocks and labels are supplied facts.
  The module does not prove trusted provenance, complete capture, semantic keyword
  correctness, true episode membership or uniqueness of spoken repeat occurrences.
- The normalized confidence field is not universal raw-score calibration or a detector
  threshold. Production metadata/score-domain validation and engine adapters are not
  implemented. No raw SDK output can become alarm authority merely by validation.
- Provisional speech authority, exact-only acoustic recall, voice/thermal association
  lifetime, genuine release/new-episode semantics and simultaneous evidence policy
  remain **UNRESOLVED**. No timeout or numeric operating rule is proposed here.
- Existing runtime partial publication, cross-engine veto/rejected veto refresh and
  missing thermal-triggered escalation remain untouched. C1.52's live-store/shadow
  isolation and atomic history/transition gates still apply. Existing immutable event,
  ACK/replay, manual/critical and Flutter active-alarm contracts remain protected.
- Acoustic accuracy/false-activation/latency and safe audible emergency authorization
  cannot be established by these tests. Authorized representative audio/model and
  controlled emergency/device validation are still required under predeclared criteria.

## J. Proposed next implementation boundary

**C1.54 — Disconnected engine-result mapping and schema completeness, synthetic only.**
If separately authorized, add a pure experimental mapping layer for already supplied
Vosk JSON results, Snowboy detector outputs and openWakeWord prediction dictionaries.
Preserve raw result/score meaning, model/config and capture provenance; explicitly
distinguish missing model score, unavailable confidence, no detection and failure.
Use fixture truth and existing vocabulary rules without creating a new acoustic
threshold. Do not call engines, change capture/reset, introduce callbacks/persistence,
wire runtime imports or infer episode/authority.

Acceptance should cover semantic payload/label consistency, detector-only results,
raw-score domains, malformed/gap/reset results, independent source order and unknown
confidence, while all 308 prior selected tests remain green. Require separate review
and unchanged runtime/source/backup proofs. Storage, endpoint registration, dispatcher
changes, thermal integration and active alert ownership remain later independently
approved boundaries, not a natural side effect of a green mapper test.

Final decision: **TEST-ONLY VERIFIED: YES. INTEGRATION READY: NO.
DEPLOYMENT READY: NO.**
