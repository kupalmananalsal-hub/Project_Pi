# C1.52 — Runtime Integration Design and Acceptance Gates

**Design/evidence milestone complete. TEST-ONLY VERIFIED evidence remains valid.
INTEGRATION READY: NO. DEPLOYMENT READY: NO.** No runtime integration was implemented.

Worktree: `/var/tmp/Project_Pi_C1_43_alarm_fix`.
Branch: `development/c1-43-c1-47-recognition-safety`.
HEAD: `8a44f109fae8adb4b7daa833c15548b56ccd2452`.
Date: 2026-11-02. The existing selected **280 mocked tests passed**; these include
characterizations that pass by reproducing retained runtime hazards. They do not
constitute passing runtime integration or acoustic acceptance.

This document is a proposal for review, not approval of a new authority policy,
sensor operation, recording access, migration, merge or deployment. Interface names
marked **proposed** do not exist yet. Existing C1.43–C1.51 files remain unchanged.

## A. Integration-point inventory

Locations refer to the current offline candidate, including the unchanged C1.45
runtime modifications. They are not measurements or inspection of deployed services.

| Boundary | Exact current location and imports | Data and call relationships |
|---|---|---|
| A: Vosk partial/final | `raspberry_pi/kws/kws_alert_dual.py:939 read_vosk_text`, `:1080 vosk_worker`; `from vosk import KaldiRecognizer, Model` at `:27`, `json`, `deque`, optional `Wav2Vec2Verifier` import `:35` | `AcceptWaveform` selects `Result`/`PartialResult`, then finality is flattened to text. `detect_tagalog_keyword:916` matches aliases. Worker `:1183–1192` calls `note_vosk_text`, `submit`, then `Reset` and clears context even if dispatch rejected. Configured scalar confidence is not ASR finality or calibrated word confidence. |
| B: Snowboy | Same file `:945 import_snowboydetect`, `:1195 create_snowboy_detector`, `:1218 snowboy_worker` | Deferred `import snowboydetect` loads the detector. Positive detector index maps configured label to alert keyword; `:1260 dispatcher.submit(..., 'snowboy')`. A `-1` result logs detection error. No provisional/final ASR claim is appropriate for this score/detection engine. |
| C: openWakeWord | `raspberry_pi/kws/audio_preprocessor.py:36 AudioPreprocessor`, `:107 process`, `:180 to_metrics`, `:226 _result`; imported by KWS at `:29` | `process` calls the model, returns availability/VAD, `scores` and above-threshold `wake_words`. KWS `main:1589` processes packets; `:1622–1658` submits eligible labels/scores. Empty output, non-speech gating or an absent model result is not complete per-keyword negative evidence. No model was loaded here. |
| D: capture and fusion | KWS `:83 KeywordCandidate`, `:659 CooldownGate.allow`, `:724 DetectionDispatcher`; `threading`, `queue`, `numpy`, `pyaudio` imports | `main:1308` owns capture/preprocessing; `fallback_speech_active:954`, `put_latest:966`, `_event_context:1270`. Speech feeds both fallback queues at `:1687–1689`, even after a primary match. `note_vosk_text:761` cancels pending Snowboy help. `_publish_tulong:777` refreshes veto state before cooldown acceptance; `_schedule_help:796`, `_publish_help:814`, `_publish_help_now:839` consult it. `submit:742` returns no explicit receipt. |
| E: KWS publication | KWS `:169 AlertPoster`, `publish:214`, `flush:279`, `_persist_pending_locked:613`, `_write_jsonl:624`; `requests` at `:26`, `uuid` at `:12`, `AlertPolicy`/`AlertDecisionEngine` at `:21` | Fresh publish allocates UUID and outbox intent; retry posts stable UUID/payload to `/api/alerts`. Local retention tier is omitted from request fingerprint input. No observation/candidate/episode protocol exists. Publication returns None; it is not an authority or durable backend receipt. |
| F: thermal state | `raspberry_pi/backend/main.py:760 ThermalCamera`, `read:834`, `latest:866`, `_confidence_payload:881`, `ws_thermal:1904`, `thermal_evidence_for_decision:1602`; `ThermalConfidenceScorer` import `:69` | Camera lock owns sensor/cache. `latest` may read. WebSocket thermal clients cause reads and send frames. These paths do not retain voice or notify an episode coordinator. Adapter marks stale/invalid/unavailable explicitly; positive human presence alone does not establish a spoken keyword or speaker identity. |
| G: backend classification/storage | `backend/main.py:262 AlertIn`, `api_alerts:2729`, `enrich_alert_payload:1648`, `AlertStore:321`, `AlertIdempotencyRegistry:581`, `AlertHub:534`; FastAPI/Pydantic, `sqlite3`, `asyncio`, `AlertDecisionEngine` import `:54` | API normalizes ID, fingerprints original request, performs durable lookup/claim, obtains thermal, calls `enrich_alert_payload -> decision_engine.evaluate`, inserts/publishes. `AlertDecisionEngine.evaluate` (`raspberry_pi/alert_decision.py:225`) updates repeat/recent/false-positive history; `_classify:362` and `_thermal_evidence:440` determine state. Same-ID retry returns stored envelope before thermal sampling. |
| H: delivery and Flutter output | `backend/main.py:1954 ws_alerts`; `from alert_delivery import DeliverySessions` at `:56`; `raspberry_pi/alert_delivery.py:48 DeliverySessions.serve`; Dart locations below | Protocol 2 reads SQLite, not only live hub publication. Existing envelope identity, sequence, dispositions and recovery boundaries are protected contracts. |

Current Flutter path:

```text
AlertStore.insert (backend/main.py:432)
 -> DeliverySessions.serve (alert_delivery.py:48; SQLite replay/live polling)
 -> AlertDeliveryService._handle (lib/services/alert_delivery_service.dart:300)
 -> AlertsController callback (:159), _handleAlert (:328), _handleAuthoritativeAlert (:368)
 -> _startAuthoritativeEmergencyAlert (:583), _startFullEmergencyAlert (:623)
 -> AlertRuntimeService.startEmergency (lib/services/alert_runtime_service.dart:117)
 -> independent notification / _startAudio (:274) / vibration attempts
```

The provider path is `lib/providers/alerts_provider.dart`; it imports `AlertEvent`,
thermal/settings providers and `AlertDeliveryService`. `lib/models/alert_event.dart:232
hasAuthoritativeDecision` treats a nonempty decision state as authoritative. Critical
bypasses the thermal-required gate. Advisory clears pending legacy voice and produces
notice/soft beep; `:520 _handleThermalStateChanged` only escalates the separate pending
legacy path, so it does not fill the backend advisory-upgrade gap.

`AlertDeliveryService` imports the reconnecting socket, model, secure-storage/path
helpers and trace module. It validates ID/sequence, persists inbox/received ACK,
records intent, invokes provider, then records presented disposition. `:423 confirm`
persists user-confirmed ACK. `AlertsController.dismissActiveAlert:230` confirms active
and superseded IDs and stops output. `AlertRuntimeService.stopEmergency:163` invalidates
generation and cleans outputs independently. Its imports include `audio_session`,
`just_audio`, notifications and vibration. Presented/attempted output is not proof of
audibility. Device/background/process-death behavior was not executed here.

## B. Proposed interface contracts

### B1. Engines → observation validation/transport

**Proposed** `raspberry_pi/recognition_observation.py`:

```text
validate_observation(raw_json_values) -> ObservationV1 | ValidationError
canonical_identity(observation) -> type-sensitive canonical JSON identity
```

Engine adapters consume existing result objects, not new model invocations. Preserve
the original payload and any supplied raw JSON text; do not infer missing characters,
finality, score or silence. Keep all existing vocabulary and thresholds unchanged.
No runtime module may import `test.disconnected_observation_reference`.

Proposed `ObservationV1` fields:

- `schema_version`, explicit discriminator `recognition_observation`;
- stable `observation_id`, `producer_instance_id`, engine, engine generation,
  source sequence and candidate/segment ID; candidate revision and ASR status;
- supplied acquisition timestamp plus clock domain/clock generation and capture
  sequence/range; source ordering must not rely on comparing unrelated wall clocks;
- original payload, original text/raw JSON where available, keyword or null,
  raw score or null and score meaning/calibration provenance;
- explicit `present`/`missing`/`not_applicable` score status, health and gap/failure
  diagnostics, model/config/policy identifiers and existing context provenance.

Vosk partial/final distinctions must survive; Snowboy/openWakeWord are score/detection
observations, not ASR finals. Explicit reset/segment and engine-restart observations
must not assert a new acoustic episode. Namespaced candidate identity must include
engine/generation; duplicate retries must retain original observation IDs, timestamps
and payloads. Domain validation is not a new detector threshold. Canonical identity
must distinguish nested true/1 and 1/1.0 as C1.51's review repair does. Unknown schema,
changed-ID content, nonfinite scores, invalid types or incompatible finality fail
explicitly without mutating accepted state.

Transport is a **separate proposed** `ObservationOutbox` in
`raspberry_pi/recognition_transport.py`, not `AlertPoster.publish`. Allocate and persist
observation identity before transmission. Network I/O stays outside capture/worker
critical paths. Backpressure/loss is explicit and source-scoped, never silently
converted to silence or global cancellation. Bounded retention, overload behavior
and durable unresolved-evidence handling need storage/load review before activation;
no capacity or expiry value is chosen here.

**Proposed** backend `POST /api/recognition-observations` consumes only the versioned
observation type, under existing authenticated access semantics. It must not accept
client-provided alarm authority, arbitrary episode membership or an alert envelope.
Schema-specific rejection must not fall through to `/api/alerts`.

```text
accept_observation(ObservationV1) -> ObservationReceipt
ObservationReceipt:
  observation_id, canonical_identity, outcome, journal_position, reason
outcome: persisted | duplicate | rejected | unknown
```

`persisted`/`duplicate` acknowledge durable receipt only, not classification, episode
membership, published alert or audible authority. Same-ID changed content conflicts;
duplicate returns the original committed receipt. Unknown transport outcome retries
the same ID/payload; rejection never refreshes suppression or clears another source.
Ordering gaps/out-of-order arrivals enter explicit pending/reconciliation state;
they cannot silently rewind a candidate, declare release or stall independent engines.
Only an explicit producer gap record can attest lost ranges; no waiting timeout is
invented to turn absence into a negative.

### B2. Observation adapter → evidence classification

**Proposed** `AlertDecisionEngine.ingest_observation_once` and
`classify_snapshot` in `raspberry_pi/alert_decision.py`:

```text
ingest_observation_once(observation_id, evidence, OccurrenceEligibility, state_tx) -> HistoryDelta | Duplicate
classify_snapshot(EvidenceSnapshot, PolicySnapshot) -> ClassificationSnapshot
```

The first owns idempotent input application and eligible history effects; the second is pure and contains
no I/O, time reads, repeat-history insertion or publication. Snapshot includes
observation IDs, candidate revision/finality, health/continuity, retained raw voice,
explicit eligibility/association verdicts, thermal ID/state/provenance and a fixed
policy version. Finality and numerical confidence remain different dimensions.

Existing `evaluate` is a compatibility path, not a reevaluation API. Preserve current
manual-single/manual-emergency/fault/high-voice-critical rules and existing classifier
semantics with differential tests. A legacy observation must not be counted once by
`evaluate` and again by the coordinator. Shadow classification uses isolated state;
it must not increment live repeat/recent/false-positive history.

**Once per observation is not once per spoken occurrence.** Distinct partial revisions,
sustained score frames and different engines may describe one utterance. Recording
them all is required; incrementing spoken-repeat history for each is not justified.
`OccurrenceEligibility` is a separate backend-owned, reviewed verdict with a stable
occurrence identity, repeat-rule version, evidence membership and reason, or explicit
UNRESOLVED state. Repeat history applies at most once per permitted occurrence/rule,
not automatically per new observation ID. Genuine distinct calls must still count.
Defining real occurrence membership across engines is an unresolved policy/validation
gate; do not invent a merge window, suppress one engine, or equate candidate/segment
IDs with true spoken occurrences. Until resolved, exercise this only with explicit
fixture occurrence verdicts and keep live repeat-history integration disabled.

### B3. Coordinator ↔ thermal state

**Proposed** `raspberry_pi/alarm_episode_coordinator.py`:

```text
ingest_observation(observation) -> durable observation receipt
ingest_thermal(ThermalObservation) -> durable frame receipt
reconcile_snapshot(episode_id, committed_version) -> classification/pending outcome
```

Backend-owned `ThermalStateFeed` is the single notification owner. It reuses the
existing camera/lock/cache; it must not create a competing sensor reader or depend
on a phone's thermal WebSocket subscription. Physical read cadence/ownership changes
need controlled validation; no new cadence is specified. Each acquisition has a
stable producer/generation/frame ID, acquisition provenance and explicit positive,
negative, stale, invalid or unavailable status. Notification/receipt time cannot
substitute for acquisition age.

Episode bindings are coordinator records with policy version/provenance, not a field
an untrusted observation can assign. Until a real membership/association policy is
approved, use fixtures or pending/unassigned state. A recognizer reset, generation
restart, cooldown expiry, missing score or failure is not evidence of release.
Thermal-triggered reevaluation consumes retained **eligible** voice without counting
new speech. Expired/invalid association cannot be revived merely by another frame.
Classifier decisions do not automatically become authorized presentation transitions.

### B4. Coordinator → durable backend alert boundary

**Proposed** `EpisodeStore` in `raspberry_pi/recognition_store.py` and shared backend
`persist_authorized_transition` helper:

```text
commit_observation_or_thermal_tx(input) -> Receipt
assess_authority(snapshot, approved_policy_version) -> permitted | rejected | UNRESOLVED
persist_authorized_transition(TransitionIntent, AuthorityAssessment) -> AlertReceipt
```

The authority function is an interface, **not an implemented or chosen policy**.
Default shadow operation produces no live alert. Permissions must be backend-owned,
versioned and auditable, never inferred from a producer receipt or client boolean.
UNRESOLVED cannot be treated as permitted. This does not propose dropping partial-only
emergencies in a live cutover; cutover remains prohibited until their liveness gate passes.

Durable, separate records distinguish:

| Record | Identity/uniqueness and purpose |
|---|---|
| Observation journal/receipt | Unique observation ID plus producer/generation/sequence; immutable typed identity and committed processing state. |
| Repeat-history eligibility | Reviewed occurrence/rule identity and evidence membership; unique application per permitted occurrence/rule, separate from retaining every observation. UNRESOLVED cannot invent another spoken repeat. |
| Candidate view | Engine/generation/candidate and revision; original observations remain append-only. |
| Episode binding/state | Stable episode ID and association-policy version; incomplete association remains explicit. |
| Classification snapshot | Separate classification ID/revision referencing exact evidence/policy; may contain critical *candidate* state without any alert authority. |
| Transition mapping | Stable transition intent and event-ID mapping, unique `(episode_id, presentation_level)` for the reviewed episode model. No new critical merely for a policy/frame retry. Alternative rearming needs a separate approved episode rule. |
| Authorized alert | Immutable runtime event ID/envelope/sequence in the existing alerts delivery store, created only after the authority gate permits it. |

**Shadow isolation is structural, not a metadata flag.** Do not insert observation,
fixture or UNRESOLVED classification rows into `AlertStore.alerts`, call `/api/alerts`,
send legacy WebSocket events or enqueue Flutter alarms. Protocol-2 live polling reads
SQLite even when `AlertHub.publish` is skipped. Existing Flutter sees nonempty
`decision_state` as authoritative; `audible_authority: UNRESOLVED` is ignored today.
Even advisory delivery can beep. Separate shadow tables/outbox/channel must be inaccessible
to all alert/history/live/replay consumers. C1.51's manual temporary-store test envelopes
are storage fixtures, never a safe production wire format.

Use one serialized coordinator writer with database transaction/version constraints.
For an applied input, commit input receipt/application position, occurrence-eligible speech
history, candidate/episode state, transition uniqueness, stable event mapping and
authorized alert intent atomically when applicable. Compute no hardware/network I/O
inside that transaction. On restart, a committed input is not reapplied; an ambiguous
producer response returns the original receipt. Crash before commit leaves no partial
history/transition; crash after commit cannot create another ID. Concurrent state
versions must reconcile, not overwrite a later revision with stale work.

For the minimum durable implementation, share a SQLite transaction/connection for
receipt, eligible history, state/mapping and authorized alert row wherever possible.
If an outbox boundary is necessary, atomically commit stable mapping plus frozen
permitted intent, then drain idempotently into `AlertStore` using that exact identity
and canonical fingerprint. Pending committed intents recover after crash without
rerunning classification, history or authority under a different policy. Commit the
intended envelope/policy/permit provenance before reply. Atomic durable intent is not
physical delivery; alert insertion/drain completion and phone ACKs remain distinct.
Prove recovery of the commit-to-drain gap in AT15/17 before using an outbox variant.

Current `api_alerts` evaluates before `AlertStore.insert`'s transaction. Simply adding
a journal beside it is insufficient: persistence failure followed by retry can otherwise
count phantom repeated speech. Legacy history and future coordinator ownership must
not run concurrently on the same active input.

Authorized transition persistence must reuse one canonical durable identity/fingerprint
contract through commit and retry. Current legacy fingerprint describes original
`AlertIn`, not the enriched stored envelope. Do not insert a coordinator envelope then
retry a differently fingerprinted `/api/alerts` request under its ID. Do not POST a
classified transition back through `api_alerts`, which samples thermal and classifies
again. Extract a reviewed shared store path for authorized envelopes while leaving
legacy request fingerprint behavior compatible. Keep the original advisory immutable;
eligible authorized critical escalation receives a distinct stable event ID.

### B5. Backend → Flutter/delivery

For approved transitions, preserve current event ID, persisted sequence, full immutable
envelope, decision state/reason/modality, explicit thermal status, source and policy
provenance. Do not overload observation IDs or episode IDs as runtime event IDs.
Reuse existing protocol-2/legacy compatibility until a separately reviewed protocol
change is needed; raw hypotheses never fall through to `AlertEvent` interpretation.

Keep observation receipt, authorized transition persistence receipt, phone
`ack_received`/`ack_presented`, and `ack_user_confirmed` distinct. Presentation intent
and output attempts are not proof of audible delivery or user confirmation.
Episode deduplication must not block replay of a stored unresolved critical event.
Confirming advisory must not acknowledge its later critical event. Reconnection,
generation changes and engine failure must not silently stop/confirm an active alarm.

## C. Emergency safety invariants

1. Independent source evidence survives another engine's provisional revision,
   rejected publication, gap or failure. Distinct engines share capture and may have
   correlated errors; preservation does not claim statistical independence.
2. Partial/final/score and health/continuity remain explicit. Missing score is never
   zero, silence, release, finality or authority. Retained evidence is not automatically
   eligible evidence.
3. Observation, candidate, episode, classification and alert event identities are
   separate. Duplicate retry cannot create another episode, repeat count or transition.
   Unique observation IDs do not by themselves establish unique spoken repeats;
   occurrence/rule eligibility is a separate reviewed history-ingestion identity.
4. Classification occurs before authorized transition deduplication. Same evidence
   can support later authorized critical escalation without new speech ingestion.
5. No thermal-only distress fabrication or cross-person pairing without an approved
   association verdict. Critical/manual existing paths do not acquire a new mandatory
   thermal gate.
6. No shadow output reaches live alerts, live history, ACK state or Flutter output.
   Accepted evidence or critical candidate classification does not authorize sound.
7. Advisory and critical IDs/envelopes remain immutable; transport retries preserve ID
   and payload, while distinct authorized transitions have distinct stable IDs.
8. Concurrent/restarted processing cannot repeat ingestion, refresh a veto on rejection,
   regress finality, erase independent evidence or let stale asynchronous work stop a
   current alarm. Delivery remains at-least-once with idempotent handling, not a claim
   of exactly-once physical sound.

## D. Acceptance-test matrix

Evidence legend: **REF-PASS** = disconnected fixture invariant in the 35 tests;
**CHAR-PASS** = retained defect reproduced by existing tests, not corrected acceptance;
**STORE-PASS** = existing synthetic storage contract; **NOT RUN** = required future
integration/device/audio test. Current suite was rerun here, but no future implementation
test is marked passed merely because its reference analogue passes.

Deployment blocker **Yes** means a missing/failed target acceptance gate blocks active
integration/deployment. **No** means this narrow existing check currently passes; it
does not waive other gates, and affected checks must rerun for later changes.

| ID | Scenario | Input evidence | Expected invariant | Required test type | Evidence status | Pass/fail criterion | Deployment blocker |
|---|---|---|---|---|---|---|---|
| AT01 | Revised Vosk hypothesis | Partial tulong then ordinary final tulog, same candidate | Trace both; no erasure of other engines or unauthorized transition | Unit + scripted runtime integration | REF-PASS; runtime CHAR-PASS | Target must retain both observations and ordinary revision; no unpermitted alert/cancellation | Yes |
| AT02 | Genuine partial-only distress | Stipulated partial-only positive, then authorized representative real traces | Retain uncertainty and satisfy approved emergency liveness | Unit, authorized acoustic/controlled scenario | REF-PASS retention only; acoustic NOT RUN; policy UNRESOLVED | Cannot pass until approved authority/liveness criteria exist and positive/negative evaluations meet them | Yes |
| AT03 | Snowboy independence | Help before/between/after Vosk revision | Preserve source evidence and accepted submission outcome | Unit + dispatcher integration | Six-order REF-PASS; runtime CHAR-PASS | All arrival orders retain independent help; provisional text never supplies a veto | Yes |
| AT04 | openWakeWord independence | Same order matrix for help | Same as AT03, without assuming engine error independence | Unit + dispatcher integration | REF-PASS; runtime CHAR-PASS | No independent evidence lost in any order; authority assessed separately | Yes |
| AT05 | Rejected/ambiguous publication | Cooldown reject, store failure, lost receipt | No veto refresh or invented acceptance; same-ID retry | Unit + transport failure injection | REF-PASS receipts; rejected-refresh CHAR-PASS | Rejection leaves evidence/authority state unchanged; unknown outcome reconciles durable original intent | Yes |
| AT06 | Missing score/empty result | Missing configured model score, unavailable prediction, non-speech frame | Unknown is distinct from negative/silence/release | Unit + scripted preprocessor integration | REF-PASS; runtime missing protocol NOT RUN | No zero fill, release or fabricated complete score set; provenance remains explicit | Yes |
| AT07 | Engine failure/recovery | Candidate, exception, new generation, stale callback | Preserve evidence/finality; new generation explicit | Unit + supervised-worker integration | REF-PASS; exception CHAR-PASS | Failed/retired generation cannot resume; no implicit release/new episode; independent paths preserved | Yes |
| AT08 | Raw identity/schema conflicts | Exact duplicates; nested true/1, 1/1.0; invalid/nonfinite fields | Typed immutable payload; atomic rejection | Unit | REF-PASS | Exact retry unchanged; every changed identity conflicts before callback/state mutation | No (reference layer) |
| AT09 | Out-of-order/gap reconciliation | Duplicate, reordered source sequences, missing ranges | No rewind or invented continuity; other engines proceed | Unit + persisted transport integration | REF-PASS rejection; production reconciliation NOT RUN | Durable pending/conflict outcome and deterministic reconciliation; no silent loss or global head-of-line veto | Yes |
| AT10 | Advisory → thermal critical | Retained eligible voice, negative then fresh positive thermal | Distinct authorized critical event; advisory unchanged | Unit + backend coordinator integration | REF-PASS; missing trigger source-confirmed | Exactly one allowed critical transition; same voice count; distinct stable event IDs | Yes |
| AT11 | Repeated/flapping thermal | Same ID retry; equivalent positive frames, negative/positive repeat | No repeated critical for an already critical episode | Unit + persisted coordinator integration | REF-PASS; integration NOT RUN | At most one event per approved episode/level; no speech-history increment | Yes |
| AT12 | Thermal invalidity/association | Stale, unavailable, invalid, other-person, expired/unknown association | No unjustified pairing; preserve existing manual/high-voice critical | Unit + authorized controlled association study | REF/classifier checks PASS; real association NOT RUN | Rejected/unknown association creates no transition; real eligibility meets preapproved criteria | Yes |
| AT13 | Sustained scores vs new call | Repeated scores plus truly separate distress calls | No assumed release from time/missingness; new genuine episode remains eligible | Unit + authorized acoustic scenario | REF-PASS explicit episodes; sustained CHAR-PASS | Approved episode rule passes both continuous and separate-call cases; current cooldown is not substitute | Yes |
| AT14 | Legacy ID/fingerprint | Same request retry; same ID changed payload | Immutable original event, conflict on reuse | Synthetic SQLite + API extraction | STORE-PASS | Original envelope/sequence returned; no duplicate row; changed content conflicts | No (existing legacy contract) |
| AT15 | Coordinator/legacy persistence boundary | Classified intent, retry after restart, legacy traffic coexistence | One canonical mapping; no second classification or speech count | Synthetic transactional integration | NOT RUN | Stable ID/fingerprint/envelope across all retry paths; legacy fixtures remain unchanged | Yes |
| AT16 | Backend interruption/replay | No consumer, reopen store, resume critical; advisory already confirmed | Original IDs replay; advisory ACK does not confirm critical | Synthetic SQLite, socket integration | STORE-PASS reopen; socket target NOT RUN | Store invariants pass AND target socket delivers retained critical with original ID/dispositions | Yes |
| AT17 | Crash at each commit boundary | Before receipt, during history/transition, after commit before reply | All-or-none applied input; restart returns committed receipt | Fresh synthetic process/SQLite crash tests | NOT RUN | Reopened state has no partial history/intent and no duplicate effects for any injected boundary | Yes |
| AT18 | Concurrent engines/thermal | Duplicate simultaneous inputs, revisions, frame updates and retries | Serialized/versioned state; no stale overwrite or duplicate transition | Synthetic concurrency/interleaving tests | Existing duplicate-store tests PASS; coordinator NOT RUN | All tested schedules obey committed ordering and once-only invariants; explicit association/authority fixed by fixtures | Yes |
| AT19 | Shadow isolation | Critical candidate, accepted observation, UNRESOLVED authority | No live alert/history/replay rows or phone output | Boundary integration + fake delivery/provider spies | Reference tags PASS; actual boundary NOT RUN | Zero writes to live alert/delivery tables; zero legacy/live emissions and output calls | Yes |
| AT20 | Flutter critical/manual lifecycle | Authorized critical with negative thermal; manual paths | Existing bypass, overlay, independent output attempts remain | Flutter unit/widget + authorized device | Source inspected; no Dart/device run here | Existing critical/manual fixtures pass; real output criteria met under approved scenario plan | Yes |
| AT21 | Flutter ACK/replay/stop races | Active/replaced IDs; reconnect; dismiss while async start pending | Durable separate ACKs; no unauthorized stop/reconfirm/restart | Flutter unit + authorized process/background device tests | Source inspected; NOT RUN here | Confirm appropriate IDs, preserve unconfirmed critical recovery, stale generations cannot actuate or stop current output | Yes |
| AT22 | Physical audible alarm | Permission/background/audio-session failures; process death | Output attempts not confused with audible success | Authorized controlled device/emergency scenario | NOT RUN | Predeclared audible/notification/vibration/recovery criteria met; presented ACK alone insufficient | Yes |
| AT23 | Exact-only matching recall | All configured vocabulary, genuine variants, contextual negatives | Quantify tradeoff without restoring fuzzy guessing by assumption | Authorized model/audio replay | Text fixtures PASS; acoustic NOT RUN | Frozen implementation meets predeclared recall/false-activation/latency criteria with reported uncertainty | Yes |
| AT24 | Shadow legacy equivalence | Same scripted capture/recognition inputs with observation capture off/on | No duplicate ownership, changed reset, added latency or legacy policy effects | Deterministic differential + controlled performance tests | NOT RUN | Identical legacy outcomes/IDs under controlled inputs; approved resource/latency budgets met before activation | Yes |
| AT25 | Preservation/disconnection | Existing sources/backups and proposed nonactuating modules | No accidental runtime edits/imports or restricted contents | Hash/inventory + source import audit | PASS this milestone | All prior artifacts identical; only authorized additions; sealed manifests complete | No |
| AT26 | Observation ownership under backpressure | Queue overflow, storage full, transport failure | Explicit loss/gap diagnostics; no silent evidence loss or capture blocking | Synthetic outbox/storage/load tests | Existing alert outbox tests PASS; observation target NOT RUN | Same-ID retry and visible loss/pending outcomes; approved retention/overload budget; independent engines continue | Yes |
| AT27 | Spoken repeat versus many observations | Revisions, sustained scores, two engines on one fixture occurrence, then a genuinely distinct occurrence | Retain every observation; history counts only permitted distinct occurrences/rule | Unit + transactional integration + authorized acoustic association | Reference input dedup PASS; real occurrence/history integration NOT RUN | Same approved occurrence contributes once despite distinct observation IDs; approved new occurrence remains countable; UNRESOLVED association never invents a repeat or erases evidence | Yes |

No acoustic numeric limit, confirmation timeout, score cutoff, release duration or
sample-size/accuracy claim is supplied by these pass/fail statements. A gate requiring
an absent policy or absent approved metric criterion cannot be closed by interpretation.

## E. Unresolved authority decisions

| Decision | Status and evidence | Required closure |
|---|---|---|
| When may provisional speech authorize an alarm? | **UNRESOLVED.** Partial-only genuine and later-revised negative can share identical observed prefixes. Neither final-only filtering nor arbitrary waiting is justified. | Approved versioned emergency authority/liveness policy, representative positive/negative acoustic traces and controlled emergency review; AT01/02/22/23. |
| How long may voice pair with later thermal? | **UNRESOLVED.** Existing thermal freshness is not voice lifetime or person association. | Approved acquisition-clock/association/expiry semantics supported by controlled measurements; AT10/12. No default duration here. |
| When does an episode end/new one begin? | **UNRESOLVED.** Cooldown, reset, failure and missing scores do not establish release. Spoken-repeat occurrence identity is not implied by a new observation or another engine. | Representative continuous, repeated, interrupted and overlapping calls with reviewed labels; AT07/13/27. |
| What authorizes a new critical event? | **UNRESOLVED for the new coordinator.** Existing manual/high-voice/thermal classification must remain compatible, but observation retention or a classifier label is not authority. | Separate eligibility, association and authority verdicts; stable transition mapping; approved initial/escalation/new-episode semantics. Replay is not a new event; AT10/11/15/20. |
| Simultaneous engines/thermal and restart | **Software serialization/atomicity can be specified now; physical association/priority remains UNRESOLVED.** Arrival order cannot justify erasing evidence. | Transaction/version/crash tests AT17/18 plus an approved association/authority policy. Do not infer statistical independence or resolve disagreement by last writer. |
| Storage bounds/provenance retention | **UNRESOLVED production resource/privacy contract.** Reference maps are unbounded and synthetic payloads are not consent for real transcripts. | Reviewed retention, overload/loss, identity ownership, authentication/privacy and load budgets; AT24/26. No original audio or credentials in observation payloads or Flutter messages. |

Safe source-supported work: strict typed schemas, separate channels/receipts, retention
of independent evidence, pure classification, once-only ingestion, immutable ID/conflict
handling and deterministic transactional recovery under explicit fixture policy inputs.
These establish software invariants, not global emergency safety. Choosing live alert
behavior, physical association, recall tradeoffs or siren liveness needs separate evidence.

## F. Minimal implementation sequence

Each row is a proposed small review boundary, not an action taken here. Names of new
files/functions below are proposals; do not copy the test reference into runtime.
Implementation starts with independent evidence and nonactuating boundaries, not a
new episode or emergency policy. No step implicitly authorizes a production migration.

| Change and exact target | Purpose/dependencies | Possible regression | Required tests | Rollback strategy | Merge-readiness gate |
|---|---|---|---|---|---|
| S1: proposed `raspberry_pi/recognition_observation.py::validate_observation`, `canonical_identity`; `test/test_recognition_observation_contract.py` | Pure production-shaped schema module, initially imported only by tests; no live caller. Depends on this interface review. | Type-coercion identity loss, lost raw finality, implicit zero score, accidental test-runtime dependency. | AT08/09 schema portion; all 280 existing tests; runtime-import/call-graph absence check. | Leave module unreferenced; remove only its new call-free code in a later reviewed change if rejected. No data/config rollback. | Deterministic schema tests and independent review pass; no runtime imports/calls, I/O or authority decisions. This gate permits only an isolated module, not integration. |
| S2: proposed `recognition_transport.py::ObservationOutbox.append/retry`, `recognition_store.py::accept_observation_tx`; backend `api_recognition_observations` proposed handler | Stable receipt/outbox identity and source-scoped reconciliation on fresh synthetic stores. Depends S1; route disabled/unregistered until review. | Capture blocking, silent losses, untrusted alarm injection, duplicate IDs/history. | AT05/09/17 receipt portion/19/26; auth/schema conflict tests with fake requests. | Keep route unregistered and outbox unused; retain synthetic/received journals for audit. Never auto-resend as legacy alerts. | No connection to capture or alert store; type/auth/conflict/retry/loss tests pass and retention contract reviewed before real use. |
| S3: KWS `read_vosk_text` companion `read_vosk_observation` proposed; `vosk_worker`, `snowboy_worker`, `main` score handoff; `AudioPreprocessor.process/to_metrics` | Capture independent metadata in explicit shadow mode without changing legacy dispatch/reset/vocabulary/thresholds. Depends S1/S2 and source-specific missing/reset contract. | Duplicate reading/reset, missed fallback audio, changed score interpretation, queue blocking. | AT01/03/04/06/07/19/24; scripted recognizers and score packets only initially. | Disable shadow producer; preserve journals and legacy outbox. Keep exactly one existing alert publisher; rollback must not re-submit observed data as new alerts. | Differential synthetic equivalence and physical shadow-isolation tests pass. Real audio use/performance testing requires separate authorization; shadow is not a safety correction. |
| S4: `DetectionDispatcher.submit/note_vosk_text/_publish_tulong/_schedule_help/_publish_help/_publish_help_now`; proposed structured `SubmissionReceipt` and separate evidence-ingestion path | Remove provisional hints/rejected attempts as reasons to destroy independent evidence. Depends on S1/S2, all arrival-order cases and reviewed distinction of evidence vs alert submission. | More duplicate legacy alarms, loss of genuine tulong/help correlation, timer races. | AT01/03/04/05/07/19; publication-failure and timer race cases. | Return to approved legacy ownership only before live cutover; retain evidence/IDs. After activation, rollback must use S9 recovery gate, not blind replay or deleting rows. | Nonactuating evidence isolation may merge with tests; **changing existing audible dispatch behavior cannot merge as an active path until authority, duplication and liveness gates close.** A timestamp-only fix is insufficient. |
| S5: `alert_decision.py::ingest_observation_once/classify_snapshot` proposed; compatibility `evaluate` wrapper | Separate stateful speech ingestion from pure thermal reevaluation; input dedup is distinct from approved occurrence/rule history eligibility. Depends S1/S2; new path stays inactive. | Changed manual/fault/critical decisions, phantom repeat speech, shadow contamination. | Differential current policy tests, AT10/11/12/17 history portion/24/27. | Keep legacy evaluate ownership active and new pure API unused; do not reset historical state as rollback. | Pure snapshot/input-dedup and fixture occurrence tests pass without evidence cancellation; no dual ingestion; existing policy/vocabulary untouched. Live history activation remains blocked until occurrence semantics are approved. |
| S6: proposed `alarm_episode_coordinator.py::ingest_observation/ingest_thermal/reconcile_snapshot` and `recognition_store.py::EpisodeStore`; backend `AlertStore._init_db` only in a separately reviewed additive migration | Serialized journal/candidate/fixture-episode/transition transactions on synthetic stores. Depends S2/S5; actual membership/authority still inactive. | Partial commits, split-brain writer, hidden repeated history, stale revisions. | AT09/11/13/15/17/18/19/27; migration compatibility and failure injection. | Stop new input owner; retain additive tables/receipts/intents, never destructive downgrade. Old reader must ignore new schema; pending authorized intents require drain/reconcile plan. | All crash/concurrency/migration tests pass; single-writer and backward-reader compatibility proved. No active occurrence/episode policy while E is unresolved. |
| S7: backend `ThermalCamera.read/latest`, proposed `ThermalStateFeed.notify`, coordinator thermal input | Single-owner updates enable reevaluation independent of phones; no live camera ownership change yet. Depends S5/S6 and association/freshness contract. | Competing sensor reads, stale time relabeling, person mismatch, repeated critical. | AT10/11/12/18/19; fake camera first, controlled thermal scenario later. | Disable coordinator notification subscription, keep camera owner/cache and persisted evidence. Never mutate old alerts back to advisory. | Fake-source identity/freshness/order tests pass; real ownership/cadence and association approval required before activation. |
| S8: backend proposed `persist_authorized_transition`, shared `AlertStore` insertion helper, preserved `api_alerts` compatibility; protocol-2 `DeliverySessions` preservation | Commit authorized mapping/history/alert intent atomically, preserve canonical legacy fingerprint and new internal identity separately. Depends S5/S6 and approved authority/association policy; do not route classified intent back through `api_alerts`. | Double classification, conflicting fingerprints, unauthenticated authority, duplicate rows/siren. | AT10/14/15/16/17/18/19 plus legacy API/ACK/replay compatibility. | Close new transition producer; retain mapped IDs and reconcile committed outbox; never regenerate IDs, mutate advisory or delete new critical events. | Authority and association gate closed, transactions/replay pass; shadow negative tests prove no live rows without permit. No active merge while policy is UNRESOLVED. |
| S9: KWS `main` output ownership and backend activation boundary; Dart files only if approved envelope compatibility needs them | Separately reviewed cutover and rollback design, not a default enabling flag. Depends S1–S8 and every applicable blocker in D. | Both legacy/coordinator actuate, neither actuates, active alarm cleared, pending intents lost on rollback. | AT02/13/16–24/26/27, approved acoustic/device/controlled emergency scenarios. | One versioned owner per input epoch; quiesce/reconcile/drain stable intents, preserve old/new replay readers and active alarms. Restore prior software only after backward compatibility and no-loss plan are proved; no automatic fallback on observation errors. | All required quantitative criteria predeclared and met; reviewer/owner approvals, preserved backup/recovery and separate deployment authorization. This document authorizes none of these operations. |

Suggested logical PRs: S1 alone; S2 synthetic transport/storage; S3 shadow-only
metadata; S4 independent-evidence isolation; S5 pure classifier; S6 durable coordinator;
S7 thermal feed; S8 authorized persistence; S9 activation only after all policy/evidence
gates. Split a row further if migration and source changes cannot be reviewed together.
No source imports from `test/`, no new alert policy hidden in a helper, and no unrelated
model/configuration/threshold/service change belongs in these PRs.

Flutter files are preservation targets by default: `lib/models/alert_event.dart`,
`lib/providers/alerts_provider.dart`, `lib/services/alert_delivery_service.dart`,
`lib/services/alert_runtime_service.dart`. Propose modifications only if S8's separately
reviewed envelope contract requires them. Existing `test/alert_event_test.dart`,
`test/alert_authority_test.dart`, `test/alert_delivery_test.dart`,
`test/alert_recovery_failure_test.dart`, `test/alert_runtime_execution_test.dart` and
`test/alert_socket_lifecycle_test.dart` are exact future regression targets, not tests
run in this milestone.

## G. Required acoustic and controlled-validation plan

No recordings, microphone, model inference or hardware were accessed. Before any such
work, obtain separate authorization and approve provenance/consent, retention/privacy,
versions, inclusion/exclusion criteria, ground-truth annotation and rescue/safety review.

Freeze code/model/config/policy identifiers and preserve the existing 17-phrase
vocabulary. Partition by speaker/session so tuning does not contaminate evaluation.
Include genuine and contextual ordinary speech, exact aliases/unlisted ASR variants,
partial-only/no-endpoint/interrupted distress, late revisions, repeated/overlapping
calls, capture/VAD/drop gaps and generation resets. Measure the actual raw result/reset
trace; final ASR text is not ground truth by itself. Include positive/negative/unavailable
thermal states, other-person scenes and sensor/clock failure cases under controlled
conditions. Distinct engine names do not guarantee independent acoustic errors.

Predeclare denominators, uncertainty reporting and decision-specific recall,
false-activation and time-to-alert acceptance criteria. The authorized reviewers must
choose numerical bounds, sampling sufficiency and acceptable tradeoffs **before**
experiments. All those values are **UNRESOLVED here**; no percentage, miss reduction,
timeout or operating threshold is invented. Synthetic fixture counts are not acoustic
sample counts or physical experiments. Do not select constants from the 35 tests.

Separately evaluate phone notification permissions, foreground/background/audio focus,
actual audible/vibration output, process death, storage failure, reconnect and
dismiss/replace races. Match device traces by immutable event IDs to backend receipts,
not merely a presented ACK. Controlled emergency scenarios must also cover independent
manual/high-voice critical paths and genuine partial-only distress without forcing a
final result. Approve scenario stop conditions and acceptance criteria before devices
are used. No production deployment is needed to conduct an authorized isolated study.

## H. Git, backup and regression verification

Phase 0 completed before report creation:

| Preservation layer | Check |
|---|---|
| C1.48-R original backup | 41 artifact hashes, manifest completeness, archive/recovery; original 17 source files match. |
| C1.50 files in C1.51 incremental | 8 artifact hashes, manifest completeness and retained 2-file recovery; C1.50 originals match. |
| C1.51 artifacts | Three regular files inventoried with type/mode/size/SHA-256; archived raw and restored into a fresh retained directory; all three byte-identical. This creates their first sealed incremental copy. |
| Entire preflight changed-file inventory | 22 files captured in `preserved-artifacts.json`; all prior sealed-file comparisons pass. |

Original backup: `/home/thesis/offline-work-backups/C1_48_R_20261102T011740.344081Z`.
Manifest SHA-256: `ee49731c9348f23b65d5df6d67871075bc7a15ca1206f57d3922428ebd4b0772`.

C1.50 incremental: `/home/thesis/offline-work-backups/C1_51_incremental_20261102T014123.101687Z`.
Manifest SHA-256: `c217a060934c96c87bd15fced50c0ede3d744f37d67c3c5dee3928b1c772600a`.

New C1.51 incremental: `/home/thesis/offline-work-backups/C1_52_incremental_20261102T020020.894305Z`.
**10 artifact checksums** including the three retained recovery files, excluding only
the checksum manifest itself. Manifest SHA-256:
`aace26d4a970bbcf7fdd7a6698b9c413c1ef4db6ccadddc050d1c329ce49866d`.
Files and directory metadata were flushed before preservation passed. Its `RESTORE.md`
describes safe binary extraction of exactly three regular relative members into a
NEW target and metadata/hash comparison. No Git/network restoration is required.
All three backups are outside the three project checkouts; no operation used ancestor
discovery under `/home/thesis`. These are local changed-file backups, not full Git
history or off-host redundancy. The new C1.52 report is not in earlier sealed snapshots.

Selected suite rerun: **280 tests; zero failures, errors, skips, expected failures or
unexpected successes; 13.299 seconds** in this environment. Duration is test execution,
not emergency latency. Selection is exactly the C1.51 final command, including its 35
adapter tests; see [C1.51 section F](C1_51_disconnected_observation_adapter_report.md#f-regression-results). Actual invocation loaded those exact module/
method names through unittest with bytecode disabled and diagnostics captured in memory.
Temporary synthetic stores/outboxes stayed under the offline worktree and were removed
by fixture contexts. Audit guards rejected network/DNS/subprocess, production file,
model/recording extension access and SQLite outside the worktree. No broad discovery,
Flutter/device test or future runtime test was run. Expected malformed-policy warnings
are existing fixture diagnostics, not real configuration changes.

Preservation verification compares all 22 prior artifact paths/types/sizes/modes/hashes,
197 pre-existing tracked Python/Dart/Markdown hashes, original binary tracked diff,
HEAD/ref/index/status and ignored/untracked inventory. Only this new report is an
authorized C1.52 addition. No old source, test, report or backup is edited.

| Checkout | Expected preserved state checked before/after work |
|---|---|
| Production `/home/thesis/Project_Pi` | `main`, `1a5c3095a27421cb4c667ee6caed14169729e774`; tracked clean, original index/status; four pre-existing untracked model/database paths unchanged by Git inventory, contents not opened. |
| Evaluation `/var/tmp/Project_Pi_M3_eval` | `main`, `8a44f109fae8adb4b7daa833c15548b56ccd2452`; clean, index/status unchanged. |
| Offline | Requested development branch, same baseline HEAD/index, 22 original changed artifacts plus exactly this report. |

All Git reads specify the checkout path with optional locks disabled. Offline shares
evaluation's common Git directory, but files/indexes are separate. No ref/config,
staging, commit, push, pull/fetch, merge/rebase/reset/clean, deployment, service restart,
Docker, swap or boot changes occurred. Only synthetic test inputs and offline source
text were read; no credentials, restricted recording, production database, queue or
model contents were accessed. Earlier failed-backup artifacts are preserved as well.

Separate read-only review examines this design's contracts, current call paths and
acceptance boundaries. Confirmed review constraints incorporated: stateful evaluation
must not precede an unrelated durable commit; original request fingerprints cannot
be confused with enriched envelopes; shadow classifications must never enter SQLite
alert rows; and Flutter ignores proposed authority metadata on ordinary alert events.
The separate reviewer completed a final source/documentation-only pass and found no
remaining material issues. Review corrections included the actual `AlertsController`
class name, explicit occurrence-based repeat eligibility (AT27), and recovery of a
frozen authorized intent without repeating classification/history under a new policy.
The reviewer did not run tests or verify backup hashes; test/preservation results
here were independently executed by the implementer. Review involved no file/Git
writes, private data, hardware or network access.

## I. Integration and deployment readiness verdict

- **DESIGN REVIEW ARTIFACT: prepared**, with explicit target interfaces, policies,
  per-change merge gates and objective evidence distinctions. It is not approval to
  enable the proposed path.
- **TEST-ONLY VERIFIED: retained**, for existing disconnected reference contracts;
  280 selected mocked tests pass. Runtime counterexamples remain counterexamples.
- **INTEGRATION READY: NO.** The production-shaped schema/transport, transactional
  history/coordinator, single thermal owner, migration/recovery and rollout contracts
  require implementation/review and the applicable deterministic gates. Live policy
  decisions remain unresolved.
- **DEPLOYMENT READY: NO.** Acoustic/controlled emergency/device gates, approved
  authority/association/episode policies, rollback evidence and explicit authorization
  are absent. No merge/deployment readiness is inferred from reference tests.

## J. Recommended next executable milestone

**C1.53 — Production-shaped pure observation contract, unreferenced by runtime (S1).**
If separately authorized, implement only `raspberry_pi/recognition_observation.py` and
`test/test_recognition_observation_contract.py`, plus its report and preservation.
Port requirements, not the test module itself: strict versioned schema, typed identity,
source/generation/sequence/candidate/finality, original payload, missing/gap/failure,
clock/provenance and explicit receipt distinctions. No engine/capture/dispatcher/backend/
Flutter imports or callers, no network/sensor/storage operation or alarm authority.

Acceptance: new deterministic tests for AT08 and the schema portion of AT09 pass;
all prior 280 tests pass; import/call-graph/source preservation checks prove no runtime
wiring; independent review finds no blocking issue; previous snapshots remain byte-exact.
Do not expand into S2–S9 without a separate reviewed task. This is the smallest
executable step toward independent evidence handling while all live actuation gates
remain closed. Acoustic protocol preparation can proceed as documentation only;
actual recording/model/device work needs separate authorization.
