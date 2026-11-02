# C1.50 — Runtime Safety Blocker Investigation

**Decision: investigation complete; runtime integration and production deployment BLOCKED.**
No application runtime code was changed. The 245 selected mocked tests pass, including
12 new counterexamples. Passing characterization tests reproduce retained hazards;
they do not establish corrected behavior or acoustic safety.

Worktree: `/var/tmp/Project_Pi_C1_43_alarm_fix`.
Branch: `development/c1-43-c1-47-recognition-safety`.
HEAD: `8a44f109fae8adb4b7daa833c15548b56ccd2452`.
Source locations below refer to this uncommitted candidate, not the production checkout.
Date: 2026-11-02. All speech, scores, times, identities and thermal inputs used here
are synthetic. No acoustic recording or real recognition inference was used.

## A. Confirmed defects and their limits

| Finding | Evidence and classification |
|---|---|
| Exact partials reach legacy alert publication before finality is known | **Confirmed retained runtime defect relative to provisional-evidence isolation.** `read_vosk_text` discards finality; `vosk_worker` dispatches an exact partial and resets. A later scripted ordinary-word final does not retract the publication. Whether a real utterance follows that trace, and its frequency, are unmeasured. |
| Vosk can remove independent help without confirmed replacement authority | **Confirmed cancellation/ordering defect.** A tulong hint cancels pending Snowboy help without any replacement publication. A tulong submission updates veto timestamps before cooldown acceptance. A rejected repeat can extend suppression of both independent help paths. A later `tulog` revision does not undo these mutations. Acceptance by this dispatcher is not proof of stable recognition or durable alarm authority. |
| Recognition arrival order changes which help evidence survives | **Confirmed runtime behavior and safety risk.** Prior immediate openWakeWord help survives, while pending Snowboy help can be canceled; help arriving during/after a revised partial can be suppressed. This does not establish a field miss rate or an actual audible missed emergency. |
| Sustained matched scores republish after cooldown without observed release | **Confirmed runtime behavior; episode-deduplication gap.** Same-keyword eligibility reopens solely with elapsed cooldown. Fresh publication has a new UUID. Synthetic continuity does not prove that real repeated matches belong to one utterance; genuine repeated calls must remain eligible. No physical alarm count is inferred. |
| Later positive thermal alone does not upgrade an authoritative advisory | **Confirmed source-level integration gap.** Backend thermal read/stream paths do not retain/reclassify voice episodes. Flutter authoritative advisory clears pending legacy voice state. The positive-thermal classifier rule exists; the missing pieces are retained association and an independent trigger. |
| Calling `evaluate` repeatedly is not pure reevaluation | **Confirmed counterexample to a proposed workaround.** Repeated evaluation of one medium-confidence observation increments repeat history and can escalate as repeated speech. This is not proof of a currently running thermal-poll loop; no such loop was found. |
| Worker exceptions lack structured per-candidate reconciliation | **Confirmed lifecycle limitation.** Vosk exceptions propagate; the main loop detects dead workers and exits. A prior publication/veto is not revised by engine failure. No claim is made that the main loop continues normally after worker death. |
| Exact-only matching may reject genuine ASR variants | **Unvalidated recall tradeoff, not a measured regression.** Removing prefix/fuzzy guesses rejects non-alias strings and preserves configured aliases in text tests. Actual distress recall, false activation and latency are unknown. |

Ordinary `tulog` with no preceding exact `tulong` hypothesis preserves both independent
help paths in the C1.45 candidate. The earlier broad prefix/non-tulong cancellation
bugs are already corrected offline and are not newly claimed as current defects.
Missing score is not a negative score, observed release, hypothesis correction,
confirmation or cancellation. Runtime does not currently implement the proposed
retained per-keyword observation/episode contract; reference-model tests cannot
establish that it does.

## B. Reproduction evidence

New test artifact: [`test/test_runtime_safety_blockers.py`](../test/test_runtime_safety_blockers.py).
`RuntimeSafetyCounterexamples` executes the actual dispatcher and `vosk_worker` with
the existing stub loader, in-memory poster, manual timers and scripted recognizer.
`BackendSafetyCounterexamples` AST-extracts the actual API, enrichment, registry and
store functions; it never imports backend startup. Thermal data and shared-audio
access are injected, publication is a recording stub, and SQLite stores are newly
created synthetic temporary fixtures in the development worktree.

| Required scenario | Executed evidence | Observed result and limit |
|---|---|---|
| Partial `tulong` revised to final `tulog` | New `test_exact_partial_revision_leaves_original_publication`; existing C1.46 `CurrentLifecycleCounterexampleTest` | One Vosk tulong publication, one reset; delivered ordinary final produces no correction. New recognizer retains scripted packets after Reset. Existing `test_reset_aware_fixture_discards_the_not_yet_delivered_revision` separately demonstrates an alternative fixture in which reset prevents the correction from arriving. Neither predicts actual Vosk trace frequency. |
| Genuine partial-only `tulong` | New `test_partial_only_and_later_revised_call_share_an_observed_prefix`; existing C1.45/C1.46 partial-only tests | Current worker publishes without a final. Ground truth is stipulated positive in this synthetic fixture. A final-only gate produces no detection for the same fixture; it is not a proven safe replacement. |
| Ordinary speech with independent Snowboy/openWakeWord help | New `test_ordinary_speech_alone_preserves_both_independent_help_paths` | Final ordinary `tulog` does not match or reset, and both sources retain help. |
| Independent help before/between/after revision | New `test_independent_help_before_between_and_after_vosk_revision` | Six subcases: openWakeWord help before the partial survives alongside Vosk; Snowboy pending before it is canceled. Both help sources arriving between partial/final or just after the ordinary final are suppressed within the fixture correlation window. |
| Hint cancellation without replacement | New `test_hint_without_any_replacement_publication_can_cancel_snowboy` | Pending Snowboy timer canceled, no publication; previous immediate openWakeWord help remains. Calling `note_vosk_text('tulog')` does not undo the prior tulong hint. This isolates the actual cancellation method; normal worker wiring also calls submit afterward. |
| Rejected repeat extends help veto | New `test_rejected_tulong_refreshes_veto_without_new_publication` | Initial tulong publishes; repeat inside cooldown does not. That rejected repeat refreshes timestamps, blocking help after the initial correlation would have expired. Fixture numbers exercise existing constructor parameters, not proposed settings. |
| Voice advisory followed by positive thermal | New `test_positive_thermal_does_not_upgrade_retry_of_immutable_advisory`; C1.44/C1.47 episode tests | Actual API retry returns original advisory and does not read thermal again. A new request with a new ID can classify critical. Absence of autonomous thermal-triggered upgrade is additionally established by source inspection; changing the fixture's state is not a real thermal notification. Reference emits distinct advisory/critical only with explicit fixture association/authority. |
| Repeated sustained keyword scores | New `test_sustained_scores_publish_again_without_release`; C1.43 rearming tests | Four synthetic sunog submissions yield three dispatcher publications as cooldown expires. The prototype emits eligibility once per fixture episode and permits upgrades, but is not integrated or acoustically validated. |
| Backend replay after temporary disconnection | New `test_reopen_and_replay_preserves_critical_after_advisory_confirmation`; selected existing delivery/storage tests | Reopened store replays original IDs/envelopes in order; advisory confirmation does not confirm critical; changed-payload ID reuse conflicts. This models an absent consumer and reopened storage, not an executed WebSocket reconnection, network outage or Flutter device lifecycle. |
| Missing recognition scores | New `test_reference_missing_score_and_failure_do_not_release_or_invent_authority`; C1.43/C1.44/C1.47 missing-score cases | Reference retains prior candidate after missing/failure and defaults authority to UNRESOLVED with no event. Prototype missing/unavailable samples do not release. These are reference/prototype invariants, not an implemented runtime missing-score protocol. |
| Engine failure during a candidate | New `test_engine_failure_after_partial_does_not_retract_veto`; existing C1.46/C1.47 failure cases | Scripted recognizer raises after a partial; exception propagates, and dispatcher has no corrective health observation. Existing reference retains evidence without fabricating finality/authority; eligible thermal escalation in that reference depends on explicitly supplied validity and authorization. |

The reference's no-event result under unresolved authority is **not** proof that a
genuine partial-only emergency will sound promptly. Equally, thermal human presence
does not prove speech content, speaker identity or independent recognizer correctness.

## C. Exact functions and call paths

### Capture, recognition, reset and independent engines

All KWS references in this subsection are `raspberry_pi/kws/kws_alert_dual.py`.

1. `main:1308` creates the preprocessor and optional engines. `AudioPreprocessor.process`
   (`raspberry_pi/kws/audio_preprocessor.py:107`) predicts scores; missing/unavailable
   prediction is not a per-keyword release observation. Disabled/unavailable/model
   exceptions return unavailable results. A successful empty score list does not
   establish that every configured keyword received a valid negative observation.
2. Capture at `main:1586` reads a packet; `:1589` preprocesses; `fallback_speech_active:954`
   chooses speech gating. `main:1622-1658` submits eligible openWakeWord matches.
   `main:1687-1689` independently feeds both fallback queues for speech, even when
   openWakeWord matched. A primary match therefore does not itself starve the
   fallback queues. Non-speech packets are withheld; no FinalResult flush occurs
   in this worker path. `put_latest:966` discards an earlier packet on overflow.
3. `vosk_worker:1080` calls `read_vosk_text:939` at `:1124`. That helper calls
   `AcceptWaveform`, chooses Result/PartialResult, then returns only a flattened
   text string. `detect_tagalog_keyword:916` matches configured token aliases;
   it does not know finality. `:1183-1192` calls `note_vosk_text`, `submit`, then
   `recognizer.Reset()` and clears recent context regardless of dispatcher acceptance.
   Vosk confidence is a configured scalar, optionally verifier-boosted; it is not
   returned ASR word confidence or finality. Verifier nonconfirmation is boost-only,
   not a veto. None of that proves provisional alarm authority.
4. `snowboy_worker:1218` maps a detection to configured alert keyword and calls
   dispatcher `:1260`; a detector `-1` prints an error. openWakeWord, Snowboy and
   Vosk share speech/capture provenance and dispatcher state; distinct engine names
   do not establish statistical independence of their errors.
5. `DetectionDispatcher.submit:742` branches on keyword/source.
   `note_vosk_text:761` cancels pending Snowboy help for tulong aliases.
   `_publish_tulong:777` updates timestamps and cancels pending help **before**
   `CooldownGate.allow:665` can reject its publication. `_schedule_help:796` and
   `_publish_help:814` consult hints and submissions. `_publish_help_now:839`
   consults actual tulong submission time, which can still originate in an exact
   partial. `_publish_generic:864` and the other publication methods apply cooldown,
   not an acoustic episode or accepted-evidence protocol.
6. `AlertPoster.publish:214` creates a fresh UUID for each publication and persists
   an outbox intent. `flush:279` retries the same envelope/UUID; it removes successful
   deliveries and durably quarantines rejected requests. Dispatcher submit methods
   return no receipt distinguishing cooldown rejection, durable publication, or
   authority. Do not use the existence of `last_tulong_at` as such a receipt.
7. Engine creation exceptions at `main:1490-1518` disable optional engines upfront;
   if none remain available the process raises. `vosk_worker` catches empty queues
   but not recognition failures. `main:1563-1567` detects dead registered worker
   threads and raises to exit; repeated openWakeWord prediction failures also raise
   at `:1590-1599`. Cleanup is in `main:1701-1707`. This source inspection does not
   establish actual service restart latency or recovery behavior, and no restart
   was attempted. Existing health/status paths are not a revision ledger.

### Thermal, classification, persistence and delivery

Normal keyword path:

```text
AlertPoster.publish/flush
  -> POST /api/alerts: backend/main.py api_alerts:2729
  -> durable lookup:2737 -> idempotency claim:2742
  -> thermal.latest:2761 -> thermal_evidence_for_decision:1602
  -> enrich_alert_payload:1648 -> decision_engine.evaluate:1673
  -> AlertStore.insert:432 -> AlertHub.publish:538
  -> protocol-2 DeliverySessions.serve -> Flutter inbox/provider/output
```

`AlertDecisionEngine.evaluate` (`raspberry_pi/alert_decision.py:225`) mutates repeat
and recent/false-positive history. `_classify:362` preserves manual single/double
button and fault behavior; eligible voice plus positive thermal can classify
critical at `:427-431`. `_thermal_evidence:440` applies explicit validity/freshness
semantics. Fresh classification helpers in the references deliberately isolate
bookkeeping; resetting the live engine every frame is **not** the proposed fix.

`ThermalCamera.read` (`backend/main.py:834`) caches frame/confidence payload;
`latest:866` returns a recent cache or reads. `ws_thermal:1904` reads and streams
frames; neither invokes a retained voice-episode coordinator. A later positive
frame alone cannot call the API's keyword decision path.

`normalize_event_id:1548`, `alert_event_fingerprint:1567`, `AlertStore.lookup:384`
and `insert:432` enforce stable request identity. Same ID/same request returns the
stored envelope before new thermal sampling; same ID/changed request conflicts.
`AlertIdempotencyRegistry.claim:605` and `complete:641` cover concurrent/in-memory
claims; durable store lookup also survives restart. Its class comment about deferred
persistence is historical wording, not a reason to disregard the implemented store.
A recognition revision, episode identity and immutable published event identity
must be different concepts. Never overwrite an advisory or reuse its event ID for
a changed critical envelope.

`AlertStore.delivery_boundary:393`, `replay:399`, `recovery_cursor:404`, `offer:414`
and `acknowledge:419` persist ordering and caregiver-specific delivery dispositions.
`backend/main.py:1954 ws_alerts` selects protocol-2 `DeliverySessions.serve`
(`raspberry_pi/alert_delivery.py:48`). It replaces stale reconnect sessions, captures
a replay boundary, validates ACKs and polls SQLite for live rows. The durable store
is the delivery source even when the live hub has no consumer. `replay_eligible:34`
retains the existing age/confirmation policy; this policy is not a recognition
confirmation deadline. Episode deduplication must not suppress replay or change ACKs.

### Flutter critical-alarm lifecycle

| Location | Current responsibility and preservation requirement |
|---|---|
| `lib/models/alert_event.dart:232 hasAuthoritativeDecision` | Distinguishes backend decision envelopes from legacy interpretation. Do not send observations through legacy alert fallback. |
| `lib/services/alert_delivery_service.dart:300 _handle` | Validates ID/sequence, persists inbox/received ACK, records presentation intent, calls provider and records disposition/presented ACK. Confirmed/active/handled IDs have protections. Storage failure must not swallow an alarm; no unsupported durable ACK is sent. |
| `lib/providers/alerts_provider.dart:159` callback, `:328 _handleAlert`, `:368 _handleAuthoritativeAlert` | Historical/duplicate paths stay separate. Authoritative advisory clears pending legacy voice state and shows notice/soft beep. It is not retained in the legacy thermal-confirmation path. |
| Same file `:492 _startThermalConfirmationWindow`, `:520 _handleThermalStateChanged` | Later thermal can act on legacy pending voice, not a cleared authoritative advisory. Preserve that distinction when designing backend upgrades. |
| Same file `:583 _startAuthoritativeEmergencyAlert`, `:623 _startFullEmergencyAlert` | Critical bypasses the thermal-required gate; manual controls remain distinct. Activates overlay, retains replaced IDs for later confirmation and calls runtime output. |
| `lib/services/alert_runtime_service.dart:117 startEmergency`, `:274 _startAudio`, `:28` generation guards | Starts notification/audio/vibration independently with async generation/output-attempt protection. Completion/disposition is not measured audibility or vibration. |
| `lib/providers/alerts_provider.dart:230 dismissActiveAlert`, delivery service `:423 confirm`, runtime service `:163 stopEmergency` | Confirms active plus superseded identities, durably queues user-confirmed ACK and stops output with generation invalidation. Ordinary provider `disconnect:300` does not automatically stop an active alarm; disposal cleanup is distinct. |

No Dart/Flutter/device tests were run here. Background permissions, audio session,
process death, actual output, restart, notification permission, races and physical
audibility remain acceptance work. Source review cannot certify them.

## D. Safe remediation opportunities and reference-contract review

“Source-provable” below means a software invariant can be demonstrated with synthetic
regressions, not that a behavior change is globally safe to deploy.

| Area | Source-provable opportunity | Boundary that remains unresolved |
|---|---|---|
| **A. Cancellation/fusion** | Retain independent engine observations despite provisional Vosk text, revisions, failed/cooldown-rejected alternative submissions or engine failure. Separate hint tracking from cancellation side effects; use explicit outcome receipts rather than timestamps as evidence of acceptance. Cover every before/between/after ordering. | Preserving observations does not choose which candidates may sound alarms or how correlated alerts are deduplicated. Simply allowing every engine to actuate can increase duplicate output. Moving a timestamp after cooldown alone does not resolve provisional authority. |
| **B. Observation tracking** | Preserve result kind/raw synthetic payload, source, engine generation/session, sequence, acquisition provenance, capture gaps, missing/unavailable/failure states and immutable observation IDs. Revision updates a candidate view, never erases evidence or mutates a delivered event. Same-ID retry is idempotent; changed-ID content conflict fails explicitly. | ASR segment finality is not true speech certainty; session boundaries, cross-clock association and real payload retention/privacy need reviewed contracts. Do not claim a new observation channel already exists. |
| **C. Downstream episode deduplication** | Separate once-only ingestion/history from pure snapshot classification; deduplicate authorized presentation transitions after classification. Freeze payload/transition ID before durable retry; do not latch on attempted publication. Keep independent sources/labels separate without validated association. | Episode membership/release and evidence lifetime cannot be inferred from test timing, missing scores or cooldown alone. Durable serialization, migration and atomicity are not supplied by in-memory sets. |
| **D. Thermal reevaluation** | A single owner can notify a coordinator of valid thermal updates and reclassify eligible retained voice without incrementing speech/repeat counts. Preserve explicit negative/unavailable/stale/invalid states and immutable advisory/critical IDs. Thermal alone must not invent distress. | Voice/person association and eligibility lifetime need reviewed semantics and measurements. Do not bolt polling onto `evaluate`, add another competing camera owner, or rely on whether a phone happens to subscribe to thermal frames. |
| **E. Audible alarm authority** | Keep uncertainty and engine health explicit; preserve independent/manual paths; test that failure cannot fabricate finality, authority or user confirmation. | Provisional-only emergency authority and acceptable missed/distorted/delayed/false-alert tradeoffs remain UNRESOLVED. No timeout, score threshold or automatic authority decision is selected here. |

Prior artifacts support these boundaries:

- **C1.43:** `tools/keyword_rearming_prototype.py` separates missing/unavailable
  samples from observed low-score release; it is single-threaded eligibility only,
  with no acoustic segmentation, durable event ownership or thermal escalation.
- **C1.44:** `test/episode_review_support.py` retains fixture voice and emits
  advisory/critical transitions separately; membership/association/release are supplied
  verdicts. Its `sent/pending` maps are not a crash-safe coordinator.
- **C1.45:** exact aliases and narrowed hints correct text-level defects and preserve
  vocabulary (including masakit), but leave exact partial submission/reset/fusion and
  real recall unvalidated. These candidate changes remain unchanged in C1.50.
- **C1.46:** `test/vosk_hypothesis_reference.py` records immutable observations and
  revisable candidate views, health, sequence and generation constraints. It does not
  publish an emergency or choose a safe timeout.
- **C1.47:** `test/alarm_authority_contract_reference.py` explicitly separates fixture
  association and authority from classification. `FIXTURE_AUTHORIZED` is supplied
  test input, never a deployable policy. Default UNRESOLVED avoids invented authority
  but supplies no guarantee of timely partial-only emergency output.

Three approaches considered: a final-only filter loses the stipulated partial-only
positive; a stability timer/repetition count cannot distinguish identical histories
before later revision and would invent an unsupported setting; structured observation
tracking preserves uncertainty and independent evidence but does not solve audible
authority. Recommend the third for a disconnected first implementation, with authority
still gated. Do not copy any test-only helper into the live path unchanged.

## E. Decisions requiring acoustic validation

Separately authorize a provenance/consent-approved protocol with frozen code/model/config
versions and representative speaker/session-separated distress and contextual negatives.
Include all existing English/Tagalog vocabulary and configured aliases, unlisted ASR
variants, genuine partial-only/interrupted calls, utterance overlap/repetition,
capture/VAD/queue gaps, revisions and resets, endpoint loss, and engine failures.

Measure declared denominators and uncertainty for recall, false activation and
time-to-alert; establish acceptance criteria with recognition and rescue/safety
reviewers before evaluating or selecting any policy. No numerical acceptance limits
are invented here. Quantify engine score calibration/correlation, voice/thermal
association and freshness, genuine episode release versus noise gaps, and whether
independent corroboration carries useful evidence. Human presence is insufficient
to establish the spoken keyword. Preserve the existing 17-phrase vocabulary; do not
silently introduce new language or model scope.

Still unresolved: whether/how provisional-only distress can authorize audible output,
acceptable delay/miss/false-alert tradeoffs, handling no endpoint and interrupted calls,
release/association lifetime, and real engine recovery/capture continuity. Neither
final-only gating nor arbitrary waiting is endorsed. No accuracy improvement,
miss-rate reduction, recall preservation or physical false-alarm reduction is claimed.

## F. Test coverage and results

| Run | Tests | Failures | Errors | Skips / expected failures / unexpected successes |
|---|---:|---:|---:|---:|
| Initial new focused harness | 12 | 0 | 1 | 0 / 0 / 0 |
| Corrected focused counterexamples | 12 | 0 | 0 | 0 / 0 / 0 |
| Existing selected 233 plus new counterexamples | **245** | **0** | **0** | **0 / 0 / 0** |

Initial error was test-only misuse of `delivery_boundary()`: it returns `(instance,
high_water)`, not a scalar SQL boundary. The new test now unpacks `high_water`; no
application/reference/previous test code was edited. Final focused run took 0.880 s;
selected combined run took 12.968 s in this environment. These are software suite
durations, not emergency latency measurements.

Reproducible selected suite from the development worktree:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest \
  test.test_runtime_safety_blockers \
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

The actual combined invocation loaded exactly those names through unittest and captured
diagnostics in memory. Default temporary fixtures were redirected beneath a temporary
development-worktree directory; explicit ROOT temporary fixtures also remained there.
An audit guard rejected network connects/DNS, subprocesses, production file access,
model/recording extensions and SQLite paths outside the worktree. Bytecode was disabled.
No broad discovery, actual engine/model, backend startup, live camera, microphone,
Flutter build/device test or service action occurred. Temporary synthetic stores and
outboxes are not production resources and were cleaned by their fixture context managers.

An independent read-only reviewer confirmed backend/Flutter call paths and inspected
the new tests, finding no material assertion/side-effect issue. Evidence limits remain:
AST API tests bypass real thermal freshness adaptation and shared audio; storage
reopening is not a socket reconnect; missing-score retention is reference-only;
scripted reset/partial-only scenarios are constructed, not measured ASR traces.

## G. Proposed implementation order and acceptance gates

No implementation in this section was performed. Each step is a separate reviewed
commit/PR boundary, with its dependencies present and no unrelated model/threshold,
capture configuration, deployment or service change.

1. **Characterize A and define B without actuation (recommended C1.51).** Add an
   isolated observation schema/adapter and outcome vocabulary, initially disconnected
   from legacy alarms and live audio. Tests: partial/final/ordinary revision, unknown
   score, failure/gap, retry conflict, sequence/generation restart, immutable exports,
   preservation of independent observations. Acceptance: every synthetic input has
   reproducible provenance/status, no invented finality/score/release, no observation
   becomes a legacy alert, and current manual/critical/delivery behavior remains intact.
2. **Correct A in a narrowly reviewed dispatcher integration.** After observation
   identity is available, remove provisional text and rejected submissions as authority
   for erasing/vetoing independent evidence; expose explicit receipt state and serialize
   mutation. Tests: the six arrival orders above, hint-only cancellation, rejected
   cooldown, publish/storage failure, timer races and independent manual/fault paths.
   Acceptance: no independent evidence is lost, and no timestamp is treated as a
   publication/authority receipt. The current counterexample tests must be deliberately
   revised to approved expectations, not merely left passing as “fixed.” Choosing
   audible output/dedup behavior still requires its own explicit approval and gate E.
3. **Build C behind disabled integration: once-only ingestion, pure classification,
   then durable transition coordinator.** Tests: repeated evaluation cannot add repeat
   speech; sustained/overlapping/separate fixture episodes; missing-score and failure;
   frozen payload on ambiguous publication failure; concurrent retries, process restart
   and durable transition uniqueness. Acceptance: classifications precede presentation
   deduplication; advisory and critical use distinct stable event IDs; same-ID mutation
   conflicts; no confirmed/replayed event is erased. Runtime episode association/release
   remains blocked until its external contract is approved. Do not deploy C1.43 gating
   upstream of classification, where it could discard a critical upgrade.
4. **Add D through one thermal owner and an explicit eligible-evidence interface.**
   Tests: eligible voice advisory then fresh positive thermal emits one distinct
   critical transition without new speech ingestion; positive-only thermal emits no
   distress; stale/invalid/unavailable/association-expired evidence does not upgrade;
   thermal flapping/repeated frames do not rearm critical; generation failure cannot
   erase valid retained evidence or manufacture authority. Acceptance: existing manual,
   high-voice critical and fault decisions stay intact; no repeat-count inflation,
   duplicate camera owner or advisory-event mutation; association/lifetime is explicit
   and approved, never selected from these fixtures. Needs C and gate E for actuation.
5. **Resolve E with reviewed acoustic evidence, then separately authorize runtime
   activation and backend/Flutter acceptance.** Tests/criteria must include partial-only
   liveness, later revisions, independent/manual emergencies, negative and interrupted
   calls, output recovery, active/superseded ACKs, duplicate/replay behavior and device
   permissions/background/process death. Acceptance requires the predeclared acoustic
   criteria and reviewed authority/association policy; 245 mocked passes cannot satisfy
   it. Production rollout/restart, if ever approved, is a later separate task.

Exact future modification candidates (not modified here):

| File | Narrow responsibility / prerequisites |
|---|---|
| Proposed `raspberry_pi/recognition_observation.py` | Versioned, non-actuating observation validation/identity; explicit finality, generation, missing/gap/failure and provenance. Use synthetic fixtures until live data access is separately approved. |
| `raspberry_pi/kws/kws_alert_dual.py` | Later structured read/worker plumbing, safe reset lifecycle, dispatcher evidence isolation and explicit submission receipts. Preserve independent fallback feeding, genuine/manual paths, retry UUIDs and existing vocabulary. |
| `raspberry_pi/kws/audio_preprocessor.py` | Later explicit successful/missing/unavailable per-keyword score observations and capture provenance; no model/threshold change. |
| `raspberry_pi/alert_decision.py` | Separate once-only history ingestion from pure classification, preserving existing policy/manual/fault rules. |
| Proposed `raspberry_pi/alarm_episode_coordinator.py` | Durable serialized observation/episode/transition state after authority/association prerequisites; stable transition identities and publication receipts. |
| `raspberry_pi/backend/main.py` | Later opt-in observation receipt/storage and single-owner thermal notifications/coordinator integration; additive migration/atomicity review. Preserve `/api/alerts` immutable semantics. |
| Proposed `test/test_recognition_observation.py`, `test/test_alarm_episode_coordinator.py`, `test/test_thermal_episode_reevaluation.py` | Focused schema, state/transaction and thermal-trigger regression suites respectively. These files do not yet exist. |
| `test/test_runtime_safety_blockers.py`, `test/test_kws_live_paths.py`, `test/test_recognition_defect_remediation.py`, `test/test_vosk_hypothesis_revision.py`, `test/test_alert_decision.py`, `test/test_alert_delivery.py` | Extend characterization into accepted integration regressions with explicit old/new expectations and preserved delivery contracts. |

Preservation-review targets, **not default runtime edit scope**:
`raspberry_pi/alert_delivery.py`, `lib/models/alert_event.dart`,
`lib/providers/alerts_provider.dart`, `lib/services/alert_delivery_service.dart`,
`lib/services/alert_runtime_service.dart`. Modify only if a separately approved schema
or presentation contract requires it; never make observations fall through as legacy
emergencies. Existing Dart test candidates for later authorized validation are
`test/alert_event_test.dart`, `test/alert_authority_test.dart`,
`test/alert_delivery_test.dart`, `test/alert_recovery_failure_test.dart`,
`test/alert_runtime_execution_test.dart` and `test/alert_socket_lifecycle_test.dart`.

## H. Git integration readiness and preservation

Pre-flight verified the C1.48-R backup at
`/home/thesis/offline-work-backups/C1_48_R_20261102T011740.344081Z`:
41 artifact checksums, complete manifest/archive and retained recovery all passed.
SHA-256 of `SHA256SUMS`:
`ee49731c9348f23b65d5df6d67871075bc7a15ca1206f57d3922428ebd4b0772`.
The same checks passed after testing; failed-attempt artifact hashes also remain
unchanged. Neither backup was written to.

All original 17 changed files retain their recorded path/type/size/mode/SHA-256.
A before/after SHA-256 snapshot of **197 pre-existing tracked Python/Dart/Markdown
files** found no changes. Original binary tracked diff is backup-identical; offline
index is unchanged. C1.50 adds only this report and the new synthetic test module;
the original 3 modified tracked files and 14 untracked files remain present.
No restricted data, model, credential, database or local configuration is added.
Temporary fixture stores are removed; no source file was deleted or overwritten.

| Checkout | Verified final state |
|---|---|
| Production `/home/thesis/Project_Pi` | `main`, `1a5c3095a27421cb4c667ee6caed14169729e774`; tracked changes none; index/status unchanged. Four pre-existing untracked model/database paths remain; their contents were not opened. |
| Evaluation `/var/tmp/Project_Pi_M3_eval` | `main`, `8a44f109fae8adb4b7daa833c15548b56ccd2452`; clean, index/status unchanged. |
| Offline worktree | Requested development branch and baseline HEAD unchanged from C1.49; original index/17 files intact, plus exactly two new C1.50 artifacts. |

Git queries used explicit checkout paths and `GIT_OPTIONAL_LOCKS=0`. Offline Git dir is
`/var/tmp/Project_Pi_M3_eval/.git/worktrees/Project_Pi_C1_43_alarm_fix`; common dir is
evaluation `.git`. No operation relied on discovery from `/home/thesis`, whose
enclosing repository caused the earlier backup-harness skip. No refs, staging,
commits, pushes, pulls/fetches, merge/rebase/reset/clean/stash or PRs were performed.

Suggested immediate draft PR scope is **C1.50 investigation/test evidence only**,
with the C1.49 candidate/reference dependencies present as its declared review base.
The new tests import C1.45/C1.47 fixtures; they cannot be cherry-picked onto untouched
baseline without those dependencies. Keep the C1.45 runtime candidate and disconnected
C1.43/C1.44/C1.46/C1.47 design artifacts in their previously proposed logical commits,
not one undifferentiated runtime deployment. Branch readiness does not resolve shallow
cross-repository history/production compatibility. No PR was created.

## I. Production deployment decision

**BLOCKED.** No runtime integration, merge or deployment is justified by this milestone.
No final-only shortcut, confirmation timeout, confidence threshold, release timer or
emergency authority rule is selected. The candidate may be reviewed as text-level
mitigation with explicit recall/authority blockers; the experimental helpers must
remain disconnected. Manual emergencies, backend critical authority, immutable event
IDs, ACK/replay and active-alarm lifecycle must be preserved through any future work.

No production modification, database/queue/recording/credential access, model inference,
microphone, service restart, Docker, swap or filesystem configuration change occurred.

## J. Recommended C1.51 milestone

**C1.51 — Disconnected recognition observation adapter and independent-evidence
contract.** Limit implementation to a pure schema/adapter and synthetic regression
fixtures, initially outside the live worker/dispatcher/backend/Flutter paths. Preserve
all original files and take a new verified preservation snapshot before future edits.

Specify immutable observation IDs, source/session/generation/sequence, partial/final
kind, acquisition provenance, missing/gap/failure distinctions, retry conflicts,
revisable candidate views and an explicit accepted/rejected/unknown submission outcome.
Make independent evidence retention testable across all six arrival orders and failures.
No proposed adapter may publish/cancel an alert or select audible authority. Obtain a
separate recognition/emergency review of that contract before dispatcher integration.

In parallel, propose (do not execute without authorization) the representative acoustic
validation protocol and acceptance criteria required to resolve E and association/
episode questions. Success for C1.51 means reproducible non-actuating metadata and
preserved independence, not a claimed safe siren policy or authorization to deploy.
