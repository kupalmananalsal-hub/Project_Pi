# C1.44 — Emergency-Safe Keyword Rearming Design and Regression Review

Decision: **NOT READY FOR DEPLOYMENT.** Recommend downstream episode deduplication
with independent thermal reevaluation. Keep all live capture/delivery code unchanged.

Workspace: /var/tmp/Project_Pi_C1_43_alarm_fix, detached at
8a44f109fae8adb4b7daa833c15548b56ccd2452. C1.43 files are preserved.

## 1. Scope and evidence

Reviewed C1.43 report, pure prototype, 17 tests; current CooldownGate,
DetectionDispatcher, Vosk partial/final matching, openWakeWord score extraction,
AlertDecisionEngine, backend event fingerprints/store/API, delivery recovery,
Flutter inbox/provider/dismissal source. No production files, databases, audio,
credentials or production queues were accessed. No service control, model/recognizer
initialization, installation, swap change, commit, push or deployment occurred.

All new strings, confidences, episode labels and frames are synthetic fixtures.
No historical C1.42 counts were remeasured. There is no acoustic accuracy or physical
siren measurement in this review.

## 2. The four existing expected failures

All four methods were invoked directly with normal setup/cleanup and individually
failed their intended assertions. Their @unittest.expectedFailure annotations were
NOT changed. A separate passing characterization test for each mechanism documents
what the current source actually does; these do not fix or excuse the defects.

### 2.1 test_ordinary_words_are_not_distress_keywords

Expected no matches; current synthetic mappings are:

| Input | Match |
|---|---|
| tulog, tuloy, tulo | tulong |
| araw, aral | aray |
| aga, agad | agai |
| sunod, sundo | sunog |
| masakit | ang sakit |

The matcher first accepts configured aliases, then permits short prefixes and
SequenceMatcher ratios >= 0.72. In particular, masakit is an explicit alias of
ang sakit; that case is a vocabulary/context policy disagreement, not merely a fuzzy
matching bug. The test cannot prove every use of every listed word is non-distress.

Contribution: the broad matcher can turn synthetic ordinary-word recognizer output
into a distress candidate. The real Vosk worker submits matches at its configured
confidence and resets the recognizer. New occurrences can become new alert IDs after
cooldown; positive thermal evidence can escalate a notice. This is a source/fixture
mechanism for false candidates, NOT proof those words were spoken or recognized in a
historical alarm. Fixing vocabulary or fuzzy rules requires separate recall evidence.

### 2.2 test_partial_prefix_does_not_match_while_word_is_spoken

Expected detect_tagalog_keyword("tul") to return None; observed "tulong". "tu"
returns None. Three letters already satisfy the tulong prefix rule. read_vosk_text()
does not preserve whether the returned text was partial or final. vosk_worker()
submits and Reset()s after a match, including partial matches.

Contribution: a word can be classified before its distinguishing suffix is available.
Reset can discard the continuation that would have corrected the interpretation.
This can create false candidates and subsequent fresh partial matches; recurrence
frequency and physical false alarms are not measured by this test.

### 2.3 test_non_tulong_vosk_hint_does_not_cancel_snowboy_help

Test schedules Snowboy help, then passes synthetic "araw" to note_vosk_text(). Expected
help publication; actual output is empty. "araw" matches aray, yet note_vosk_text()
checks only for ANY match, updates last_tulong_hint_at and cancels the pending help
timer/payload. A manual timer fixture independently verifies cancellation without
starting timer threads.

Contribution: a missed/delayed genuine help risk, not duplicate publication by this
operation. On the real worker path, note_vosk_text() is followed by submit() of the
matched aray candidate, which can substitute the wrong alert and potentially escalate
with thermal evidence. That extra publication is not itself executed by this xfail.

### 2.4 test_vosk_hint_does_not_suppress_openwakeword_help

Test passes synthetic "tulog" as a hint, then submits openWakeWord help. Expected help;
actual output is empty. The false tulong match updates last_tulong_hint_at even though
no tulong alert was published. _publish_help_now() suppresses help near that hint.
A mocked clock confirms last_tulong_at stays zero while last_tulong_hint_at advances.

Contribution: cross-engine loss of a potentially genuine distress candidate. On the
full worker path the misclassified tulong can also be submitted, causing wrong-label
or false candidates. Repeated hints can prolong suppression, but this individual test
does not measure that duration or establish repeated physical sirens.

Do not simply remove xfail markers or delete aliases. Existing recall guards include
genuine tulong suppression of Snowboy help. Distinguishing an intended help/tulong
fusion rule from false cancellation requires separately reviewed matching changes.

## 3. Additional blockers established by source and tests

1. /api/alerts performs durable event-ID lookup before reading thermal evidence. Same-ID
   retries return the stored envelope; they do not reclassify. Changed input under the
   same ID conflicts with the request fingerprint (409).
2. Flutter deduplicates by event_id and retains the existing inbox event. Mutating an
   advisory envelope into critical under that same ID would not reliably present it.
3. Critical recovery is per immutable event, per caregiver, within the existing replay
   window. Presentation is not user confirmation. A new critical transition must have
   its own ID and must not inherit advisory confirmation.
4. evaluate() mutates repeat/recent histories. A synthetic .75 event evaluated twice
   with repeat escalation enabled becomes repeated_distress_escalation even though it
   is the same voice observation. Current explicit policy disables repeat escalation,
   but a new thermal poller must not manufacture repeat evidence under any policy.
5. AudioPreprocessor currently emits model scores only on speech frames. Missing scores
   do not establish a release. C1.43's .25/.125 timing examples remain illustrative
   only; this review chooses no release timing.
6. /ws/thermal reads frames per connected client; alert ingestion calls latest(), which
   may read the sensor. Health monitoring checks availability but is not an independent
   continuous decision-reevaluation loop. A backend-owned trigger must be designed;
   reevaluation cannot depend on a caregiver keeping a thermal screen connected.

## 4. Architectural comparison

| Concern | A: upstream rearming plus exceptions | B: downstream episode deduplication plus thermal reevaluation |
|---|---|---|
| Sustained matches | Drop candidates before backend | Preserve observations; suppress redundant presentation transitions |
| Higher voice confidence | Needs bypass and downstream acceptance feedback | Reclassify snapshot; emit first critical transition |
| New positive thermal | KWS needs thermal feedback or a separate backend mechanism anyway | Backend independently reclassifies still-valid voice evidence |
| Missing/failed predictions | Latch can remain stuck or wrongly rearm | Explicit uncertainty; never treat missing scores as release |
| Identity | Must distinguish suppressed, queued, accepted and retried candidates | Separate observation, episode and immutable presentation identities |
| Emergency risk | An omitted exception loses evidence before safety classification | Classification occurs before presentation deduplication |
| Protocol work | Apparently smaller gate, but exceptions duplicate backend policy | Requires explicit episode state/receipts; existing output protocol can remain |
| Recommendation | Do not integrate the C1.43 gate | Preferred proposal, pending contracts and durable implementation |

A confidence-upgrade exception alone is insufficient. It does not cover thermal
transitions, dispatcher cooldown rejection, release uncertainty, crash recovery or
stale outbox observations. Adding backend reevaluation to A converges toward B while
retaining two separate suppression authorities.

## 5. Recommended minimum safety-preserving design

### 5.1 Keep evidence identity separate from alarm identity

- observation_id: immutable input identity, retained across HTTP/outbox retries.
- episode_id: correlation scope, never a substitute for event_id or an ACK target.
- event_id: immutable presentation transition identity. Existing legacy/manual event
  IDs remain unchanged. Allocate a new critical ID when an advisory episode escalates.
- source session/generation and monotonic sequence: prevent restart/out-of-order input
  from silently reopening or regressing an episode.

Initially scope episodes by engine and canonical keyword as well as source session.
Do not merge help/tulong or different speakers/labels solely by temporal proximity.
Different labels and uncertain associations remain independent candidates. This leaves
some possible duplicates, deliberately avoiding unverified suppression of emergencies.

### 5.2 Episode state and transitions

Maintain segmentation state separately from the highest committed presentation level
and from delivery ACKs. Keep latest valid voice evidence with its acquisition time,
source/session, engine status, release evidence, pending immutable transitions and
references to emitted events.

| Input/condition | Evidence action | Presentation action |
|---|---|---|
| First valid match | Open candidate episode | Classify immediately under existing policy |
| Continuous matches, membership supported | Update/reevaluate valid evidence | No new event for an already committed level |
| Advisory to critical voice confidence | Reevaluate immediately | Emit one new critical event, without waiting for release/cooldown |
| Negative to fresh valid positive thermal | Independently reevaluate still-associated voice | Emit critical if newly warranted, even at identical voice confidence |
| Repeated positive frames / thermal flapping | Continue evaluating; do not retract a critical event | No additional first-critical transition for that episode |
| Verified release then new match | Close old episode; new episode gets new identity | New immediate emergency allowed |
| Missing/invalid scores or engine failure | Mark unknown/fault; break release evidence | No fabricated silence or emergency; existing valid critical delivery continues |
| Insufficient release evidence | Do not declare a proven new episode | Do not install an indefinite suppressing latch |
| Voice evidence no longer associated | Exclude it from future thermal pairing | No new critical inferred from obsolete speech |

The distinction between genuine release and score fluctuation is NOT solved by a
Boolean in a test. Release evidence, permitted observation gaps, voice-evidence lifetime
and the response to ambiguous episode membership remain acceptance gates. No duration
or new threshold is supplied here. Thermal frame freshness uses existing policy and
is separate from voice freshness; do not reuse its value as a voice lifetime.

For uncertain boundaries or missing episode metadata, retain legacy acceptance rather
than applying a new dedup veto. First valid candidates and newly critical evidence
must not be withheld by uncertain grouping. This fallback preserves emergency detection
but cannot promise duplicate elimination. It must be explicit and observable, not an
indefinite latch or a declaration that missing data proves a new acoustic episode.

### 5.3 Independent thermal reevaluation

Use one backend thermal acquisition owner and an independent notification of successful
fresh frames/failures. Reuse existing sensor ownership/locking; do not add a competing
I2C reader or depend on /ws/thermal subscriber presence. Define lifecycle, scheduling,
backpressure and cache behavior before implementation; no new sampling cadence is chosen.

For each associated, unclosed voice episode: classify latest valid voice plus fresh
validated thermal evidence before applying presentation deduplication. Unknown engine
status does not veto escalation if retained voice association is still valid; it also
does not extend that association. Failed, invalid or stale thermal evidence must never
be converted to positive. Old queued observations must be assessed by acquisition time,
not receipt time. A sensor positive with no eligible voice remains thermal-only behavior.

Separate pure classification from history updates in AlertDecisionEngine. Ingest one
new voice observation once; thermal reevaluation and retries do not increment repeat
history. If repeat escalation is enabled in a future policy, count genuine accepted
voice episodes/observations according to that reviewed policy, never poll iterations.

### 5.4 Deduplicate transitions after classification

Within a supported episode: publish at most its first advisory notice and first critical
transition. Once critical has been emitted, advisory/negative frames do not reset that
slot, stop the siren or generate another critical ID. Updated direction/thermal evidence
can be status metadata without a new alarm identity; existing alarm envelopes stay frozen.
A genuinely separate episode receives independent presentation IDs.

This concerns unnecessary NEW alarm events. Reliable replay of an unresolved critical
ID is still intentional. Do not disable recovery or assume a presentation attempt is
confirmation. Per-caregiver confirmation is not global episode dismissal. Acknowledging
an advisory must never acknowledge its later critical transition.

System faults and manual emergency/single-tap controls bypass recognition-episode dedup
and retain their existing decision rules. Never apply this mechanism globally to all
alerts based only on keyword text.

### 5.5 Durability and compatibility

Atomically commit observation receipts, episode state, transition uniqueness and immutable
alert envelopes. A committed transition must remain recoverable if publication fails.
Enforce uniqueness on episode plus presentation transition; serialize concurrent voice
and thermal updates. Freeze event ID and payload BEFORE an ambiguous write/send retry.
Do not mark an episode handled merely because publication was attempted.

Existing alert storage/delivery remains the source for critical replay; retain sequences,
fingerprints, per-phone ACKs, five-minute recovery eligibility and inbox UUID handling.
A backend restart must restore episode/receipt/transition state together. Unknown source
sessions cannot be silently stitched together or retroactively merged.

Use an opt-in typed observation protocol (proposed /api/keyword-observations) rather than
changing existing /api/alerts retry semantics. A receipt is not a presentation event.
Keep /api/alerts for existing legacy/manual callers; the observation coordinator produces
ordinary immutable output envelopes. No Flutter runtime dedup by episode_id is needed.
This is the smallest recommended semantic design, not a claim of a small line-count patch.

## 6. Synthetic experiments and results

### Test-only reference model

New test/episode_review_support.py models classify-before-presentation-deduplication,
separate advisory/critical IDs, frozen pending publication and explicit fixture release.
It is intentionally NOT a production coordinator. Episode membership and voice association
validity are fixture inputs; no timing or segmentation algorithm is implemented.

It uses a fresh real AlertDecisionEngine for each snapshot under the existing repeat-
disabled policy, avoiding test bookkeeping inflation. Resetting the live engine per frame
is NOT proposed; a real implementation needs the pure reevaluation split described above.

New test/test_episode_rearming_review.py contains 21 passing tests:
- Four characterize the expected-failure mechanisms with stubbed engines/manual timers.
- Seventeen cover repeated observations, immediate voice upgrades, thermal upgrades,
  thermal freshness/failure, unknown engines/missing scores, release validity, independent
  labels, thermal flapping, publication retry, bookkeeping inflation and real storage.

Required escalation regression: voice .40 with negative thermal is advisory; a thermal
update to positive with IDENTICAL .40 voice emits critical, with the same episode ID
and a different event ID. Twelve repeated positive reevaluations emit no further critical.

The storage experiment AST-extracts the real AlertStore and fingerprint function without
importing backend startup. It creates only a temporary synthetic DB inside this worktree.
It verifies two immutable rows, retry dedup, conflicting ID rejection, store reopening,
critical replay eligibility, advisory confirmation isolation and critical recovery cursor
movement only after critical user confirmation. This is not a live database test.

### Selected regression suite

Bytecode writing disabled; recognition/model/audio/network imports are stubbed in the
KWS tests. Existing live-path tests run scripted recognizers, not recognition engines.
Temporary SQLite stores use synthetic events. No actual authentication credential is read.

Ran these modules:
- test.test_episode_rearming_review
- test.test_keyword_rearming_prototype
- test.test_kws_event_id
- test.test_keyword_fusion
- test.test_kws_live_paths
- test.test_kws_recognition_regression
- test.test_alert_decision
- test.test_alert_trace
- test.test_alert_publication

Plus these inspected DeliveryStorageTest methods from test.test_alert_delivery:
- test_restart_retains_full_envelope_and_uuid
- test_concurrent_duplicate_and_conflicting_uuid
- test_independent_acks_survive_restart
- test_replay_policy_boundaries
- test_recovery_cursor_ignores_presentation_but_respects_confirmation_and_age

Invocation: PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest followed by the module names
and fully qualified DeliveryStorageTest method names above. The execution wrapper captures
diagnostics in memory and reports every failure/error/xfail, avoiding noisy synthetic logs.

Result: **156 tests in 11.075 seconds: 152 passed, 4 expected failures, 0 unexpected failures,
0 errors, 0 skipped, 0 unexpected successes; exit 0.** All 21 new tests passed.
Existing four expected failures remain named and unresolved in section 2.

No broad discovery, real backend startup, Flutter build/runtime, audio replay or physical
output was run. Source review and Python protocol tests do not prove Android behavior.
Passing a characterization of a defect does not establish that defect was corrected.

## 7. Files changed now and exact later change candidates

C1.44 adds only:
- test/episode_review_support.py
- test/test_episode_rearming_review.py
- docs/C1_44_emergency_safe_rearming_report.md

C1.43 files remain unchanged. No existing tracked application/test file is modified.

Later reviewed implementation candidates (NOT implemented or approved for deployment):

| File | Proposed responsibility |
|---|---|
| raspberry_pi/kws/audio_preprocessor.py | Expose reliable full-model observations separately from speech/presentation filtering |
| raspberry_pi/kws/keyword_episode.py (new) | Reviewed segmentation/uncertainty contract; no guessed release defaults |
| raspberry_pi/kws/kws_alert_dual.py | Immutable observation/session IDs, episode metadata, acceptance feedback, preserve worker-only transport and existing emergency bypasses |
| raspberry_pi/systemd/kws-alert.service | Opt-in observation endpoint configuration only after protocol approval; no recognition-threshold edits |
| raspberry_pi/alert_decision.py | Pure snapshot reevaluation separated from per-observation history accounting |
| raspberry_pi/episode_decision.py (new) | Decision-before-dedup coordinator, transition ledger interfaces, explicit validity/health boundaries |
| raspberry_pi/backend/main.py | Typed observation endpoint, transactional store migration/receipts/episode state, headless thermal scheduling/reevaluation, retain legacy API |
| test/test_keyword_episode.py (new) | Validated release and uncertainty fixtures once the missing evidence exists |
| test/test_episode_decision.py (new) | Real coordinator regression tests replacing the current test-only model |
| test/test_alert_decision.py | Reevaluate without repeat inflation; preserve all existing safety decisions |
| test/test_kws_event_id.py | Observation outbox retry/session identities and immutable payloads |
| test/test_backend_alert_smoke.py | Observation endpoint, independent thermal escalation, failure/restart/rollback/concurrency cases, all hardware stubbed |
| test/test_alert_delivery.py | Episode-ledger atomicity, immutable escalation rows, restart and per-phone recovery |
| test/alert_authority_test.dart | Advisory-to-critical event handling and unchanged manual/fault behavior |
| test/alert_delivery_test.dart | Notice confirmation cannot hide later critical ID; replay and inbox durability |
| test/alert_recovery_failure_test.dart | Crash, publication, storage failure and restart recovery for immutable critical events |

The exact wire schema, migration, voice association lease and lifecycle ownership need
review before implementation. No production Flutter runtime change is presently proposed.
Keep evaluation's worker-only posting and superseded-event dismissal changes as they are.

The four recognition defects should be handled in a separate reviewed change touching
raspberry_pi/kws/kws_alert_dual.py, test/test_kws_recognition_regression.py and
test/test_kws_live_paths.py, with approved recall evidence before changing aliases,
partial/final acceptance or tulong/help arbitration. No xfail removal is proposed here.

## 8. Unresolved risks and deployment readiness

- No validated release criterion or maximum gap; score segmentation cannot prove an
  acoustic utterance boundary. The test model receives that judgment from a fixture.
- No approved voice-to-thermal association lifetime, delayed-queue policy, source clock
  contract or evidence for correlating distinct speakers/engines.
- Missing scores cannot be treated as silence; engine loss cannot safely latch forever
  or authorize merging a later genuine emergency into an old episode.
- Headless thermal trigger, cache freshness and single sensor ownership are not yet
  implemented. The UI must not be necessary for backend escalation.
- Production coordinator durability, crash windows, ordering/concurrency, limits and
  atomic receipt/transition migration are not exercised by the in-memory test model.
- Only current repeat-disabled classification is modeled. Policy-preserving history
  refactoring needs tests for both enabled and disabled modes.
- User confirmation/repeated genuine calls within uncertain segmentation need explicit
  policy. Never reuse advisory ACKs or disable existing critical replay to hide repeats.
- Four known matching/fusion defects remain; episode dedup does not repair false matches
  or cross-engine suppression and cannot establish acoustic precision or recall.

**Readiness: proposal and passing offline design experiments only. No live integration.**
Next safe action: review the episode-boundary/voice-association and immutable observation/
transition contracts, then implement an isolated durable coordinator against crash and
concurrency fixtures. Choose no release timing until authorized representative evidence
supports it. New audio/model access, hardware evaluation and deployment remain separate
activities requiring explicit authorization.
