# C1.47 — Emergency Alarm Authority and Observation Contract

**Deployment readiness: BLOCKED. Alarm authority for provisional-only distress:
UNRESOLVED.** This is a proposed contract plus disconnected synthetic experiments,
not an implemented production protocol or a claim of preserved acoustic recall.

Workspace: `/var/tmp/Project_Pi_C1_43_alarm_fix`, detached at
`8a44f109fae8adb4b7daa833c15548b56ccd2452`.
Baseline: `/var/tmp/Project_Pi_M3_eval`, same commit on `main`.
Production: `/home/thesis/Project_Pi`, `main` at
`1a5c3095a27421cb4c667ee6caed14169729e774`.

## Scope, prior evidence and execution plan

Read the C1.43, C1.44, C1.45 and C1.46 reports, the C1.46 hypothesis ledger and its
fixtures, the C1.44 episode model, KWS preprocessing/worker/dispatcher/publisher,
backend classification/thermal/event storage/delivery, and Flutter model/provider/
delivery/output lifecycle. The existing C1.46 artifact is
`docs/C1_46_vosk_hypothesis_revision_report.md`; it is preserved. No historical
investigation or acoustic experiment was repeated. The 209-test selected baseline
was rerun because this task explicitly requires fresh verification.

Plan: (1) specify evidence and authority separately; (2) write synthetic contract
tests before a minimal test-only reference; (3) run the selected mocked regression
suite, conduct a separate read-only review, and verify Git isolation and preservation.
The requested complete offline work authorizes these test/doc changes; no application
runtime integration is authorized or justified. No branch/index mutation or commit.

Considered alternatives: final-only authority can lose genuine no-endpoint calls;
partial-immediate authority can alarm on a later correction; evidence retention with
independent reevaluation and explicit unresolved authority exposes both risks without
claiming to solve them. The third is the contract explored here. It does not choose
a production alarm gate. No new time limit, repeat threshold or score calibration.

## A. Proposed observation and event contract

### Ownership and authority boundary

Recognition adapters report evidence and health. A backend-owned coordinator retains
and classifies eligible evidence and materializes immutable alert transitions. Flutter
presents backend decisions and retains its existing manual/legacy behavior; a new raw
observation/status message must never be parsed as a legacy alert. Neither ASR finality,
an episode label nor an HTTP observation receipt grants audible-emergency authority.

The decision pipeline is:

`raw observations -> immutable evidence ledger -> current candidate views -> association
and freshness assessment -> candidate classification -> reviewed authority decision ->
immutable event + durable delivery -> Flutter emergency presentation`

Classification and authority are distinct: the current classifier can return critical
for a numerical Vosk candidate plus positive thermal even though that candidate is an
unstable partial. That existing result is not evidence that the proposed authority
policy is safe. Candidate classifications must not be sent as live alert envelopes
while the authority decision is unresolved.

### Proposed fields and semantics

| Record | Required semantics |
|---|---|
| Raw recognition observation | Version; immutable `observation_id`; source/device; engine/model/config identity; engine generation/session; monotonic source sequence; capture interval/sequence and clock domain; acquisition and receipt time separately; result kind; full permitted structured result; explicit missing/error reason. Raw here means engine result metadata, not a requirement to store PCM or private recordings. |
| Vosk hypothesis | Explicit provisional/final kind; original text/payload and exact lexical match with matcher/vocabulary version; segment/candidate identity; revision predecessor and history. Final means endpointed ASR output, not acoustic truth or emergency confirmation. Empty/ordinary final results remain observations. |
| Score observation | Model/label identity, original score and provenance, availability and successful-prediction status, configured threshold version, VAD/input gating and capture continuity. Do not manufacture a zero score for absent predictions. |
| Engine health | Independent session-wide healthy/unknown/failed state, last successful acquisition, failure/gap reason and generation. A finalized segment can still receive later health-control records. Missing heartbeat handling needs a reviewed bound; none is invented here. |
| Candidate view | Derived revisable pointer to the latest hypothesis and all supporting observations. Revision invalidates current keyword eligibility when appropriate, without editing history. Failure does not convert the last observation into a final. |
| Episode | Separate correlation identity, membership evidence and lifecycle/boundary reason; initially source/session/keyword scoped. An explicit fixture segment is not a validated utterance boundary. No time-near cross-engine/help-tulong merge is presumed safe. Unknown association remains visible. |
| Confidence | Preserve engine-specific raw score, configured Vosk candidate confidence, ASR word scores, verifier result, noise adjustment and rule-based fusion separately. Scores across engines are not interchangeable probabilities. A high configured Vosk confidence is not measured ASR certainty. |
| Thermal observation | Independent frame identity, acquisition time and clock domain, validated state positive/negative/unavailable/stale/invalid, age, error and model/analysis provenance. A cached frame is not a new sensor acquisition. Unknown freshness must not establish a fresh positive. |
| Association assessment | Versioned voice-to-thermal association verdict and supporting acquisition metadata; valid/invalid/unknown plus reason. Thermal freshness and voice lifetime are separate. Receipt/retry/polling must not renew either lifetime. Numerical voice lifetime and ambiguous boundary policy remain UNRESOLVED. |
| Authority assessment | Policy version; exact supporting observation/candidate/thermal references; candidate classification; authorized/unresolved/denied outcome and rationale. An assessment is not a user acknowledgement. UNRESOLVED must remain visible and must not be reported as safe rejection or successful emergency handling. |
| Immutable backend event | Existing `event_id` and frozen payload/fingerprint, persisted sequence and delivery envelope. Link episode and evidence references as provenance. An advisory-to-critical transition needs a new event ID. A changed payload must never reuse an old event ID. |
| Receipt and delivery disposition | Observation receipt confirms durable evidence ingestion only. Event receipt, presentation attempt and per-caregiver user confirmation remain distinct. Episode ID is never an ACK target. |

Observation retries must preserve ID and payload and not rewind the current view.
Conflicting IDs/associations are rejected without altering prior state. Old observations,
out-of-order arrivals and sequence gaps need explicit reconciliation; ignoring them
silently or treating arrival as acquisition is unsafe. Source sessions cannot bridge
process restarts by reusing a sequence or a wall-clock guess.

### Revision, failure and recovery

Partial `tulong -> tulog` changes current keyword eligibility, preserving both raw
observations. It does not retract, rewrite or acknowledge an already committed alert.
Correction presentation is a separate status protocol requiring review; no automatic
siren stop or critical downgrade is proposed. Other engines' evidence stays independent.

A genuine partial-only call remains available with finality/health metadata. It must
not be discarded merely because no final arrives. Evidence retention alone does not
guarantee timely audible detection: the unresolved authority/liveness tradeoff remains
a deployment blocker. Engine failure is visible and must not silently cancel either
independent sources or existing critical recovery, nor extend stale voice association.

Future durable implementation must atomically store observation receipt, candidate/
episode state, authority decision, transition uniqueness and immutable event/outbox
intent. Serialize voice/thermal races; distinguish committed output from attempted
publication. Recover after crashes at each boundary without generating a new event ID
for an existing transition. New engine generations do not silently rearm old episodes.
Unknown recovery state cannot be declared healthy or permanently suppress new calls.
Resource bounds, retention, ambiguous membership fallback and migration are UNRESOLVED.

The C1.47 reference is deliberately in-memory and does not implement this durability
contract. Its backend restart test reopens a synthetic event store, not a persistent
observation coordinator. It does not claim end-to-end restart correctness.

## B. Safety invariants

1. Preserve all configured distress vocabulary and independent valid candidates; do
   not install a final-only gate, indefinite latch or unvalidated deadline. Partial-only
   audible liveness cannot yet be guaranteed and remains an explicit acceptance gate.
2. An unconfirmed Vosk hint/revision/failure cannot cancel Snowboy/openWakeWord evidence,
   start their suppression windows, or count as negative evidence against them.
3. New valid thermal evidence can independently upgrade still-associated eligible voice
   evidence at unchanged confidence; no extra keyword publication or connected thermal
   screen is required by the proposed architecture.
4. Classify before presentation deduplication. Within a supported episode, emit at most
   the first advisory and first critical transition. Thermal flapping, elapsed time,
   polling and repeat transport do not reopen the critical slot.
5. Genuinely separate episodes have independent identities and prompt eligibility.
   Synthetic labels prove only this identity behavior; real segmentation is unresolved.
   Uncertain membership must not become an indefinite emergency suppression rule.
6. Retain backend event-ID uniqueness, immutable fingerprint conflicts and duplicate
   lookup semantics. A retry is not reclassification; a thermal upgrade is a new event.
7. Preserve critical replay and Flutter recovery, including per-caregiver confirmation,
   durable inbox identities and superseded active event disposition. Presentation is
   not confirmation. An advisory confirmation cannot confirm a later critical event.
8. Thermal polls and classification retries cannot add voice observations, repeat-history
   entries or genuine episode counts. Separate pure snapshot evaluation from ingestion.
9. Missing model scores, gated frames and dropped packets are unknown, not measured
   silence, valid release, proof of no person or proof that a new episode began.
10. Engine unavailability/faults are visible with provenance and continuity state.
    Other sources and pending critical delivery remain functional; faults do not prove
    absence of distress or authorize invented distress detections.

Manual emergency and single-tap behavior remain separate existing authority paths;
recognition deduplication and provisional corrections must not intercept them. Sensor
fault handling must remain distinct from distress classification.

## C. Alarm authority decision matrix

All outcomes below distinguish current code behavior from proposed safety acceptance.
No new threshold, wait interval or acoustic result is selected.

| Candidate policy/evidence | Current/proposed treatment | A: unjustified-alert risk | B: missed/delayed-emergency risk | Decision |
|---|---|---|---|---|
| Finalized Vosk exact configured distress | Retain immediately; classify using existing score provenance, not assumed certainty. Current worker already publishes matched finals and partials alike. | A wrong final or contextual/non-distress use can still match; configured confidence is not calibrated recognition truth. | Requiring finals for every path loses no-endpoint or interrupted genuine calls. | Finality metadata specified; universal final-only gate rejected as unsupported. Production authority acceptance UNRESOLVED. |
| Provisional exact distress alone | Retain as provisional; expose candidate classification separately from output permission. | Partial `tulong` can later become `tulog`; early immutable emergency cannot be undone by revision. | Waiting only for a final or silently denying unresolved evidence can miss genuine partial-only distress. | UNRESOLVED; no siren rule implemented. |
| Repeated identical partials | Preserve revisions within the same supported candidate. | Repetition does not prove a later correction impossible. | Arbitrary repetition/stability requirements delay or omit short genuine calls. | Not sufficient authority; no repeat count selected. |
| Cross-engine agreement | Preserve each independent source, provenance and calibrated meaning; optional future association must be reviewed. | Shared microphone/noise and correlated models can agree incorrectly; double-counting scores fabricates confidence. | Mandatory consensus suppresses genuine calls recognized by only one available engine. | Corroboration policy UNRESOLVED; never a required veto of independent detection. |
| Fresh validated thermal-positive plus eligible voice | Existing classifier upgrades notice-level voice to critical. Proposed coordinator must preserve this transition once authority/association are justified. | Human presence does not prove a provisional word was distress; stale/misassociated voice can create a false combination. | Requiring another keyword or suppressing identical confidence loses thermal escalation. | Transition semantics specified; provisional-plus-thermal authority and voice lifetime UNRESOLVED. |
| High-confidence voice only | Existing classifier permits critical without positive thermal; preserve this compatibility path during future review. | Raw/configured scores and model errors can be high; score is not calibrated probability. | Mandatory thermal/consensus/finality can suppress strong genuine independent voice detections. | No new gate/threshold. Source-specific calibration/authority acceptance UNRESOLVED. |
| Recognition revision to ordinary/empty | Invalidate that candidate's future pairing, retain immutable history/events. | Ignoring correction can create new alerts from invalidated evidence. | Broad/global cancellation can stop another source or retract a valid already-issued emergency. | No cross-source veto, event mutation or automatic siren cancellation. Correction UI policy UNRESOLVED. |
| Engine failure during unresolved episode | Report failed generation; retain bounded eligible evidence, do not fabricate final/silence. | Treating failure as confirmation or extending evidence forever can cause unjustified alerts. | Discarding evidence, suppressing other engines or waiting forever for final can miss distress. | Health semantics specified; partial-only failure authority UNRESOLVED. |
| Thermal unavailable/stale/invalid | Carry explicit state; no positive fusion credit. Existing high-confidence voice-only/manual paths remain. | Reusing old positive frames or converting unknown to positive creates false corroboration. | Treating unavailable as negative proof or a universal alarm veto suppresses genuine voice/manual emergencies. | No new thermal-required gate; missing-evidence degradation policy needs review. |

Identical available partial histories cannot be distinguished by a rule that sees only
those histories. This is the C1.46 logical counterexample, not a claim that improved
recognition or additional validated evidence cannot help. There is no justified timing
or confidence constant that this task can derive from synthetic traces.

## D. Thermal escalation requirements

Use a single backend thermal acquisition owner and explicit fresh-frame/fault
notifications. Reuse ownership and locking; do not add another I2C reader. Current
`ThermalCamera.latest()` is cache/read-on-demand and `/ws/thermal` is client-driven;
neither is an implemented independent episode reevaluation coordinator.

Each eligible episode is reevaluated on relevant new evidence with acquisition-based
voice association and validated thermal freshness. Receipt time and repeated cached
frame reads cannot renew evidence. The actual `_thermal_evidence` policy and backend
normalization are reused in synthetic decision tests; future observation input must
explicitly represent unknown freshness rather than relying on permissive missing-age
defaults. No sensor cadence or voice TTL is proposed.

Ingest voice once under an immutable observation ID. Snapshot classification must not
mutate repeat/recent histories. Existing `AlertDecisionEngine.evaluate()` does mutate
them, including when repeat escalation is disabled. The synthetic adapter constructs
a fresh evaluator for each snapshot; resetting live engines per poll is not proposed.
Future work must separate pure classification from once-only ingestion bookkeeping and
define repeat semantics using validated episodes, not poll counts or raw frame counts.

For a justified advisory-to-critical transition, retain episode identity and original
voice provenance, allocate a distinct immutable critical event ID, persist before
delivery, and leave advisory confirmation separate. Repeated positive frames and
thermal negative/unknown/positive flapping cannot emit another first-critical event.
No later correction/fault implicitly acknowledges, retracts or suppresses that event.

## E. Synthetic test evidence

Added only:

- `test/alarm_authority_contract_reference.py`: reduced normalized observation ledger,
  explicit fixture authority verdict, per-session health/continuity, separate snapshot
  classification, immutable in-memory transition identities and copied exports.
- `test/test_alarm_authority_contract.py`: 24 synthetic contract/compatibility checks.
- `docs/C1_47_alarm_authority_contract_report.md`: this report.

The new reference has no application imports, network, engine, audio, sensor, credential,
queue or database I/O. The test module reuses the C1.46 hypothesis ledger and existing
pure real classifier adapter. Storage coverage AST-extracts real `AlertStore` and its
fingerprint function without importing backend startup; only synthetic temporary SQLite
state is opened. Existing stubbed KWS tests do not run microphone/model inference.

`UNRESOLVED` is the default and produces no presentation event even for a candidate
classification of critical. `FIXTURE_AUTHORIZED` and `FIXTURE_DENIED` are external
counterfactual fixture verdicts, not acoustic policies or production permission. An
authorized provisional fixture deliberately demonstrates that a later revision cannot
rewrite an already issued emergency. This helper must not be wired into runtime as a
new restrictive alarm gate: its no-event default does not satisfy partial-only liveness.

This reduced ledger carries supplied normalized result status and optional original
payload. The C1.46 ledger remains responsible for the structured raw ASR/finality
experiments. C1.47 does not implement an ASR adapter, segmenter, bounded store, persistent
coordinator, concurrency/atomic outbox, cross-engine fusion, phone UI or real freshness
algorithm. Episode and association verdicts are explicitly supplied by fixtures.

| Stage | Tests run | Failures | Errors | Result |
|---|---:|---:|---:|---|
| First sandboxed baseline attempt | 209 | 0 | 1 | Existing `test_real_store_retains_advisory_and_critical_as_distinct_immutable_events` could not create its temporary offline-worktree directory (read-only sandbox); not a recognition regression. |
| Baseline rerun with required temporary-filesystem permission | 209 | 0 | 0 | PASS |
| Initial contract tests before reference existed | 22 | 22 | 0 | Expected RED: explicit absent-reference assertions; not 22 runtime defects. |
| Initial reference | 22 | 0 | 0 | PASS |
| Missing-score guard added, before validation correction | 24 | 1 | 0 | Expected RED: absent score mislabeled as a successful score observation could clear retained voice. |
| Corrected focused contract suite | 24 | 0 | 0 | PASS |
| Full final selected mocked suite | 233 | 0 | 0 | PASS; zero skips, expected failures or unexpected successes. |

The missing-score failure was traced to the ordinary-hypothesis invalidation branch
also accepting an empty score observation. Require explicit `missing` status for absent
model scores before mutating state; ordinary/empty ASR hypotheses still revise their
own candidate. The regression passed after this test-only validation correction.

Required scenarios are covered: partial tulong revised to tulog; partial-only distress
retained but authority unresolved; finalized distress; advisory then positive thermal;
identical thermal updates/flapping; independent Snowboy and openWakeWord; engine failure
with unresolved evidence and with still-valid thermal escalation; immutable-event replay
after reopening a synthetic store; explicitly separate episodes; repeated sustained scores.
Additional checks cover missing scores, invalid association, unavailable/stale/invalid
thermal, high voice-only classification, default unresolved authority, immutable exports,
retry/conflict/association identity, generation restart and no polling-added voice counts.

The replay test checks original event IDs, no duplicate stored event, changed fingerprint
conflict, advisory confirmation isolation, and critical recovery despite presentation
ACK. It does not execute Flutter. Existing 209 tests retain coverage of mocked dispatcher,
publication, immutable storage, delivery ACK/replay and recognition limitations.

Focused command:
```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest test.test_alarm_authority_contract -q
```

Full selected command (same 209 baseline tests plus the new module):
```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest \
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

Combined runs capture diagnostics in memory and print the result summary. Bytecode
writing is disabled. No broad discovery, package install, Docker, Flutter build/device
test, acoustic replay, hardware test or service action was performed.

Separate read-only review inspected all three new files and reran the focused suite:
24 tests passed, zero failures/errors/skips/expected failures. No blocking correctness
findings remained. One low-priority wording correction changed “original UUIDs” to
“original event IDs”: the new reference uses deterministic fixture IDs, not UUID-format
validation. The reviewer explicitly accepted only the disconnected test artifact,
not runtime authority or deployment. Final source-preservation check: SHA-256 comparison
of 182 pre-existing offline Python/Dart/Markdown source/doc files found zero mismatches,
including all earlier candidate and test/report artifacts. All three checkouts retained
their original HEAD/branch/index status; `git diff --check` passed in all three.

## F. Unknowns requiring real acoustic validation

- Actual partial/final/revision traces, endpoint loss under speech gating, capture gaps,
  queue drops and match-triggered recognizer reset behavior on representative calls.
- Partial-only emergency authority and acceptable delay/miss/false-alert tradeoffs;
  no-endpoint and interrupted genuine distress cannot be excluded from evaluation.
- Engine-specific score calibration and configured Vosk confidence meaning; correlated
  errors and whether cross-engine/thermal corroboration supplies useful independent evidence.
- Exact-alias-only matching recall for unlisted pronunciation/ASR variants, contextual
  negatives, all existing keywords/aliases and genuine overlapping/separate calls.
- Episode boundaries, release versus noise gaps, evidence lifetime and cross-clock
  association, including genuine repeated calls with sustained model scores.
- Thermal absence/unavailability, freshness and voice/person association. Human presence
  alone does not validate the recognized phrase or speaker identity.

Any future acoustic/model experiment needs separate authorization, provenance/consent
review, frozen configs, representative speaker/session separation, declared denominators
and acceptance criteria. None was performed here. No acoustic accuracy, precision,
recall, latency or physical false-alarm improvement is claimed. Synthetic iteration
counts and scores are examples, never selected operating constants.

## G. Exact proposed implementation locations

These are future review targets, not files changed in C1.47:

| Location | Proposed responsibility / prerequisite |
|---|---|
| `raspberry_pi/kws/kws_alert_dual.py`: `read_vosk_text`, `vosk_worker`, capture queue helpers | Opt-in structured hypotheses, capture/session/segment metadata, explicit gap/failure observations, safe reset lifecycle. Do not wire partials into cancellation while authority is unresolved. |
| Same file: `DetectionDispatcher.note_vosk_text`, `_publish_tulong`, help scheduling/publication and `submit` | Remove unconfirmed cross-engine veto only through a reviewed redesign; preserve all independent/manual paths and return explicit acceptance/receipt state. Current exact tulong hint/partial cancellation remains a blocker. |
| Same file: `AlertPoster` | Preserve retry UUID/payload; keep observation receipts distinct from legacy alert publication; do not latch an episode merely on attempted publication. |
| `raspberry_pi/kws/audio_preprocessor.py`: `AudioPreprocessor.process` | Explicit successful predictions versus missing/unavailable scores and VAD/capture provenance. No invented silence or deployment threshold changes. |
| Proposed `raspberry_pi/recognition_observation.py` | Versioned observation schema/validation; no dependency on test-only helpers. Naming is a proposal, not an existing file. |
| Proposed `raspberry_pi/alarm_episode_coordinator.py` | Durable serialized observation/episode/authority/transition coordinator with independently triggered thermal reevaluation. Implement only after policy/association gates are resolved. |
| `raspberry_pi/alert_decision.py`: `AlertDecisionEngine.evaluate`, `_classify`, `_thermal_evidence` | Separate pure snapshot classification from once-only history updates, preserve existing/manual/fault behavior and explicit thermal states. Finality/authority cannot be inferred from numerical confidence. |
| `raspberry_pi/backend/main.py`: `ThermalCamera`, `thermal_evidence_for_decision`, `api_alerts`, `AlertStore` | Single-owner thermal notifications; proposed opt-in `/api/keyword-observations`; durable observation receipts and transition uniqueness. Leave `/api/alerts` immutable retry semantics intact. Schema migration/atomicity requires review. |
| `raspberry_pi/alert_delivery.py`: `replay_eligible`, `DeliverySessions` | Preserve existing event IDs, persisted sequence, recovery boundaries and per-caregiver ACKs; do not use episode dedup to block replay. |
| `lib/models/alert_event.dart`, `lib/providers/alerts_provider.dart` | Backend authoritative critical presentation, advisory notice, manual controls and superseded active IDs preserved. Any observation/correction UI needs a separate type/channel, never a legacy alert fallback. |
| `lib/services/alert_delivery_service.dart`, `lib/services/alert_runtime_service.dart` | Preserve durable inbox IDs, recovery and output generation guards. Unresolved observation, revision or engine failure cannot auto-confirm/stop an emergency. |

Flutter inspection shows authoritative advisory goes to notice/soft-beep behavior,
critical bypasses a thermal-required gate, and system faults are visible. Legacy
voice/thermal/manual paths also exist and must stay isolated from a future observation
channel. Replays use durable per-event inbox state, and user dismissal confirms active
and superseded IDs. Source inspection and Python storage fixtures do not validate
Android/iOS output, notification permission, process recovery or audible presentation.

## H. Git isolation and future pull-conflict assessment

All Git queries are read-only with optional index locking disabled. No pull, fetch,
checkout, reset, clean, stash, merge, rebase, add, commit or push was executed.
No remote URLs, credentials or restricted data contents were printed.

| Checkout | Branch / HEAD | Git storage relationship |
|---|---|---|
| Production `/home/thesis/Project_Pi` | `main`, `1a5c3095a27421cb4c667ee6caed14169729e774` | Git/common dir `/home/thesis/Project_Pi/.git`; only production is registered in its worktree list. |
| Evaluation `/var/tmp/Project_Pi_M3_eval` | `main`, `8a44f109fae8adb4b7daa833c15548b56ccd2452` | Git/common dir `/var/tmp/Project_Pi_M3_eval/.git`; independent from production; shallow history. |
| Offline `/var/tmp/Project_Pi_C1_43_alarm_fix` | Detached, same `8a44f10` | Git dir `/var/tmp/Project_Pi_M3_eval/.git/worktrees/Project_Pi_C1_43_alarm_fix`; common dir is evaluation `.git`; separate index and working files. |

Evaluation/offline share objects/refs/config, not the working tree or index. Detached
offline edits are not commits and cannot become incoming production commits just from
a pull. Shared evaluation metadata still requires care for future branch/worktree work.
Production/evaluation have no object alternates configured. Root/component paths are
not symlink aliases. The three changed tracked source paths have distinct inodes where
present across checkouts. Tracked model-directory symlinks resolve to each checkout's
own `dataset/` tree, not production from the offline checkout.

Production tracked modifications: **none**; staged paths: **none**. Untracked paths:
```text
dataset/thermal/models/thermal_human_shape.tflite
dataset/thermal/models/thermal_human_shape_labels.json
raspberry_pi/backend/alerts.db
raspberry_pi/backend/alerts.db.backup
```

Evaluation tracked modifications, staged paths, untracked and ignored files: **none**.

Offline pre-existing tracked modifications (unstaged; preserved):
```text
raspberry_pi/kws/kws_alert_dual.py
test/test_kws_live_paths.py
test/test_kws_recognition_regression.py
```

Offline untracked paths, including the three C1.47 additions:
```text
docs/C1_43_offline_keyword_rearming_report.md
docs/C1_44_emergency_safe_rearming_report.md
docs/C1_45_recognition_defect_remediation_report.md
docs/C1_46_vosk_hypothesis_revision_report.md
docs/C1_47_alarm_authority_contract_report.md
test/alarm_authority_contract_reference.py
test/episode_review_support.py
test/test_alarm_authority_contract.py
test/test_episode_rearming_review.py
test/test_keyword_rearming_prototype.py
test/test_recognition_defect_remediation.py
test/test_vosk_hypothesis_revision.py
test/vosk_hypothesis_reference.py
tools/keyword_rearming_prototype.py
```

Offline staged paths and ignored files: none. C1.43/C1.44 prototype/review artifacts,
C1.45 runtime candidate and C1.46 test-only observation ledger remain only in offline
working files. C1.47 adds only tests/support/report. Production's KWS file matches its
own committed HEAD; the other two offline-modified test paths and all experimental
untracked paths are absent from production. This verifies no current copied offline
candidate/artifact at those paths; it cannot certify historical copy-and-revert activity
or arbitrary outside-repository state. No production service state was inspected.

### Pull risks and protected files

Production is **0 ahead / 3 behind** its locally cached `origin/main`
`1c2b814a6d58852a07dffc404e7a5467a5e84d60`. There is no local divergence against
that cached ref. Evaluation `main` equals its own cached `origin/main` at `8a44f10`.
These are different cached snapshots, not verification of today's remote. Evaluation's
shallow history cannot establish the complete cross-repository ancestry from local
history alone. No fetch was permitted, so the exact future target is unknown.

The three cached incoming production commits are `b982348`, `801629e`, `1c2b814`.
Their path diff includes `raspberry_pi/alert_decision.py` and recognition evaluation
code as well as tooling/tests/docs. Even a clean fast-forward can change live production
behavior and is not deployment authorization. No current tracked local-edit conflict
or untracked/ignored file/directory path collision was found against that cached diff,
nor against the evaluation HEAD tracked paths. No assume-unchanged/skip-worktree index
flags or sparse checkout were found in production. No active non-sample Git hooks
were found in production's default hooks directory.

Production has 106 ignored local paths (names/metadata inspected only):
`build/app/outputs/flutter-apk/` (3), `dataset/archives/` (1),
`dataset/audio/keyword_dataset/` (57), `**/__pycache__/` (43),
`raspberry_pi/saklolo.onnx`, `raspberry_pi/saklolo.onnx.data`.
Ignoring files does not protect them against a future tracked-path collision; ignored
files can be overwritten by checkout/merge machinery in circumstances where ordinary
untracked files would stop an update. Recheck every local path against the exact target.

Preserve during any separately authorized production update:

- `raspberry_pi/backend/alerts.db`, `.backup`, and any active SQLite WAL/SHM companions;
  retain delivery/ack history, local outboxes/queues and their identities. No contents
  were opened. Use a separately approved consistent live-state backup procedure.
- `dataset/` private recordings/metadata/splits/archives and both tracked and local
  deployed models, including the two untracked thermal model paths above and the two local ONNX
  files. Preserve the two relative model-directory symlinks and their targets.
- Local configuration and credentials, including any `.aws/`, `.codex/`, `.agents/`,
  `.cursor/`, environment/pairing/authentication material and machine-local service
  overrides. Some are directories visible at production root; presence/content of
  every possible credential/config path was not investigated. Never commit secrets.
- `raspberry_pi/config/`, `raspberry_pi/systemd/`, deployed service ownership, audio,
  thresholds/model selection, network/boot/swap settings and manual emergency controls.
  Tracked copies may change with updates; do not automatically apply service/config
  changes. Outside-repository deployed settings were not audited.
- Locally generated APK/distribution outputs where operationally needed. Python caches
  are generated rather than authoritative state, but no cleanup is authorized here.

Safe future integration: preserve offline changes first under separately authorized
Git work; create a development branch in development infrastructure, review C1.45
runtime candidates separately from test-only C1.43/C1.44/C1.46/C1.47 artifacts, resolve
upstream differences there, and run permitted validation. Submit a PR with explicit
unresolved authority/association/durability gates; do not merge automatically. Do not
copy the offline KWS candidate into production or blindly carry these uncommitted
files into a new baseline. Refresh the remote in development only when authorized,
review the exact release commit/path diff and every local generated-path collision.
Production updates require separately authorized preservation/backup, rollback and
deployment review; only then consider an explicit reviewed fast-forward target.

**PRE-PULL decision: REQUIRES REVIEW.** Current metadata shows isolation and no collision
against inspected cached targets, but cannot certify a future pull. The remote is
unrefreshed, protected local state exists, and incoming/runtime changes need review.
**Deploying the offline candidate remains BLOCKED.**

## I. Deployment readiness decision

**BLOCKED.** The contract distinguishes evidence, candidate classification, alarm
authority and immutable delivery, but no supported rule resolves provisional distress
versus later correction while guaranteeing partial-only genuine emergency liveness.
Finality alone and positive thermal alone do not prove a spoken distress call.
Association lifetime, episode boundaries, durable coordinator/crash recovery and real
acoustic/Flutter acceptance are also unresolved. Do not integrate the test helper or
change KWS/backend/Flutter runtime based on these passing synthetic tests.

No production code/files/services, evaluation files, pre-existing offline source or
reports were intentionally modified by C1.47. No production database/model contents,
recordings, credentials or queues were accessed. No real inference, microphone,
deployment/restart, install/Docker, swap or boot changes occurred.

## J. Recommended C1.48 milestone

**C1.48 — Authority acceptance criteria and isolated recovery-contract validation.**
First obtain an explicit reviewed decision framework for provisional-only/no-endpoint
distress, correction presentation, independent-source preservation and acceptable
false-alert/missed-call/latency tradeoffs. Define episode/clock/association ownership
and an acoustic validation protocol with acceptance criteria; do not select operating
constants from these fixtures.

Safe offline continuation can build a test-only durable observation/transition
coordinator with synthetic crash cuts, concurrent voice/thermal updates, sequence gaps,
ambiguous persistence/send outcomes and independent phone confirmations. Compare its
recovered immutable events against the existing event-store/delivery contract. Keep
unresolved authority visible; this work cannot authorize provisional sirens.

Separately authorize representative acoustic/model replay before choosing an authority
rule, and later Flutter recovery/output validation before integration. Runtime changes,
production deployment, services and new audio access remain outside this milestone's
authorization. Do not repeat the completed lexical/partial counterexample investigations.
