# C1.46 — Vosk Hypothesis Revision and Distress Preservation

**Deployment readiness: BLOCKED.** Completed a test-only structured-observation and
revision reference model. No C1.46 application runtime change is justified by the
available evidence. Partial-only emergency authority remains unresolved.

Workspace: /var/tmp/Project_Pi_C1_43_alarm_fix, detached at
8a44f109fae8adb4b7daa833c15548b56ccd2452. C1.43/C1.44/C1.45 reports and candidate
changes were read and preserved. The original evaluation checkout remains clean.
No commits, pushes, deployments, service/package/Docker/swap/boot actions, recognition
inference, microphone/recording access or production DB/queue/credential access occurred.

## A. Exact partial/final recognition lifecycle

### Current C1.45 candidate runtime (unchanged by C1.46)

1. Capture preprocesses packets and computes fallback_speech_active(). With usable VAD,
   this follows is_speech; otherwise it uses the existing raw-energy floor. Only speech
   packets are put into the Vosk and Snowboy queues. An openWakeWord match does not
   starve these fallback queues, but nonspeech is still withheld.
2. put_latest() drops the oldest queued packet if the bounded queue is full. Vosk gets
   no explicit sequence-gap or silence-control observation. Capture frame continuity
   is therefore not guaranteed by this queue helper.
3. vosk_worker() adds samples to its recent verification context, then calls
   read_vosk_text(). AcceptWaveform(data) selects Result() when true and PartialResult()
   otherwise. The helper returns only normalized text, losing the final/partial flag,
   original JSON, word metadata and per-word confidences.
4. Both kinds of text enter the SAME C1.45 exact-alias matcher. Incomplete tul is no
   match; exact tulong and configured aliases such as tulon are matches even in partials.
   A match uses configured keyword confidence; optional wav2vec2 verification can boost
   it but does not veto an unconfirmed candidate. Word confidence is not substituted
   for this configured keyword confidence.
5. The worker calls note_vosk_text(text), then dispatcher.submit(..., source="vosk").
   A tulong alias can cancel pending Snowboy help in the hint path. Actual tulong
   submission refreshes fusion state before shared cooldown checks. Immediate help
   ignores hint-only timestamps after C1.45, but actual partial-derived submissions
   can still suppress independent help through the retained correlation rule.
6. AlertPoster assigns an event UUID only when publication occurs. Dispatcher submit
   provides no acceptance result to the worker. A two-second per-keyword cooldown can
   reject publication, but the worker unconditionally Reset()s after ANY matched text,
   then clears recent verification audio. Thus a rejected match also resets recognition.
7. Nonmatching text does not cause this explicit Reset(). A later revised ordinary
   result cannot undo an already-published event. A final result is an ASR endpointed
   segment result, not proof that the speech or emergency interpretation is correct.
8. Queue-empty waits simply continue. The worker does not synthesize a final result,
   call FinalResult(), or flush recognition on shutdown. A recognition exception is
   not caught by the queue.Empty handler. Existing main-loop worker supervision can
   notice a dead worker; that existing behavior was inspected, never exercised as a
   real restart in this task.

Relevant source: raspberry_pi/kws/kws_alert_dual.py, functions read_vosk_text,
fallback_speech_active, put_latest, vosk_worker and class DetectionDispatcher;
raspberry_pi/kws/audio_preprocessor.py, process().

### When a final may be absent or unusable

- Endpoint-relevant nonspeech packets may be withheld by speech gating.
- Continuous speech may yield only partial results during the observed interval.
- Queue drops, missing capture input, engine exceptions or process termination can
  interrupt the result stream.
- An early match-triggered Reset changes decoder state before a possible correction.
- There is no explicit end-of-input FinalResult() call in the current worker.

These are source-supported failure possibilities and synthetic counterexamples. No
real ASR endpoint frequency or latency was measured. The scripted recognizer that
continues after Reset deliberately models a possible revision trace, not real Vosk
state. A second reset-aware fixture discards the not-yet-delivered continuation,
illustrating that a reset itself can prevent that correction from being observed.
Neither fixture proves a specific real recording would yield the scripted outputs.

## B. Confirmed failure mechanisms

| Synthetic case | Current runtime experiment | Reference observation behavior |
|---|---|---|
| Partial tulong, then final tulog | tulong publishes before the scripted correction; no retraction | Both immutable observations retained; current keyword becomes None |
| Partial tul, then final tulong | Only completed exact tulong matches | Final tulong remains immediately available |
| Genuine final tulong | Candidate published | Final candidate available without an added wait |
| Genuine partial-only tulong | Candidate can publish without a final | Provisional evidence retained and available; siren authority unresolved |
| Repeated exact partials at synthetic 1000/1001/1002 | Two publications, three Reset calls | Revisions share a candidate identity; observations have separate immutable IDs |
| Silence or missing frames | No new final forced by the worker | Explicit unknown/continuity state, never a fabricated final |
| Engine failure | Exception propagates from read helper | Session failure retained separately from segment finality |
| Separate final distress segments | Existing cooldown/fusion still applies | Distinct fixture utterance identities preserve distinct candidates |

Other confirmed issues retained from C1.44/C1.45:
- Reusing an existing backend event ID returns its cached decision before thermal reads;
  changing the same ID's request payload conflicts with idempotency.
- An upstream partial/rearming veto could discard evidence needed for later thermal
  escalation. Thermal reevaluation must remain possible without another keyword event.
- Treating every revision as a new emergency creates unnecessary identities; treating
  an observation/candidate identity as a mutable backend event breaks replay semantics.

### Indistinguishable-history limit

The finite input history [partial tulong, ...] can describe either a synthetic genuine
call with no final or a trace later revised to final tulog. The test compares identical
prefixes with 1, 2, 4 and 8 repetitions. Those counts are counterexamples, NOT proposed
confirmation thresholds. Waiting for more repetitions cannot, by itself, prove that a
later revision is impossible. Waiting only for a final can omit the partial-only call.

This logical tradeoff is limited to identical available observations. It does not prove
that other validated evidence or a better real recognition pipeline cannot help. No
confirmation deadline, speech duration, repeat count or new confidence threshold is
justified by the synthetic traces.

## C. Design alternatives and tradeoffs

| Approach | False-alert risk | Missed-distress risk | Latency | Cross-engine effects | Recovery |
|---|---|---|---|---|---|
| A. Final-result-only publication | Avoids the demonstrated pre-final reversal; wrong final text remains possible | Can miss a real call with no final/endpoint | Wait depends on endpoint availability; unbounded in no-final fixture | Independent engines must keep operating while Vosk waits | Must preserve unfinished observations across failure; shutdown cannot invent a final |
| B. Provisional partial tracking | Keeps uncertainty explicit; does not establish safe alarm authority | Retains partial evidence, but retention alone does not guarantee timely emergency output | Evidence can be available immediately; siren timing unresolved | Partial records must not enter tulong cancellation or shared emergency cooldown | Immutable observations plus revisable candidate state; needs future durable implementation |
| C. Revision-aware confirmation with bounded evidence | A real final or separately validated corroboration may support a decision; repeated identical partials alone do not | Unsupported bounds can suppress genuine calls; missing evidence cannot mean rejection | No safe numerical bound supplied | Independent recognizers should alert on their own evidence, not be held behind a Vosk condition | Source generation/sequence/finality needed; gap/failure must invalidate continuity assumptions |
| D. Downstream episode-aware deduplication | Prevents redundant presentation events, not an incorrect initial interpretation | Preserves reevaluation if observations are retained; segmentation/association errors can still lose distress | Classification can precede presentation deduplication | No broad cross-engine merge without evidence; preserve manual/fault paths | Separate observation/episode/event identities and durable critical replay required |

**Recommendation:** B supplies evidence/finality metadata; D supplies separate immutable
presentation transitions and independent thermal reevaluation. C may supply an authority
rule only after evidence and policy review. Do not replace current behavior with A or
invent a timing rule to claim a complete solution. D is complementary to B/C, not a
solution to uncertain partial authority by itself.

Even corroborating thermal presence does not prove the spoken word was distress. A
permissive partial-to-critical policy is evaluated as a comparison, not selected as safe.

## D. Offline implementation and limits

### Implemented only under test/

read_hypothesis_result() in test/vosk_hypothesis_reference.py uses a scripted recognizer
and preserves kind, normalized matching text, the complete parsed original payload and
exact raw JSON. It does not import Vosk, create an engine or read audio.

HypothesisReference is an in-memory test-only ledger:
- Immutable observation IDs, original result/context and copied exports.
- Stable candidate identity scoped by explicit fixture session and utterance IDs.
- Every revision retained, including ordinary/empty final results; the current candidate
  can be revised away without rewriting its old evidence.
- Identical observation retries are idempotent; conflicting IDs/out-of-order inputs are
  rejected without changing prior state. An older retry cannot rewind a final revision.
- A new healthy hypothesis cannot reopen a finalized utterance; a new engine generation
  needs a new session identity. Repeated genuine calls use distinct fixture segments.
- Silence/gap/failure controls never manufacture a final, delete the original observation,
  infer a validated release, or automatically authorize an alarm.
- Segment finality remains sealed while later health controls remain reportable. Current
  session failure and continuity gaps are reflected on all retained candidate exports.
- for_classification() keeps eligible partial evidence available with provisional and
  health/continuity metadata. Its association_valid argument is an explicit fixture
  verdict; no voice lifetime, timestamp policy or acoustic segmenter is implemented.

The full ORIGINAL observation is retained. This includes supplied context and any raw
word scores/timestamps in the synthetic result. No PCM recording or real transcript is
stored. The test helper's synthetic capture_sequence is not a real acquisition clock.

### What is deliberately NOT implemented

No automatic siren decision, alert envelope, event UUID, delivery ACK, fusion callback,
recognizer Reset, confirmation timeout, threshold, sensor sampling or persistent store
is added to this reference model. Stable candidate identity is not a backend event ID.
It does not put provisional text into DetectionDispatcher.note_vosk_text or submit.

Tests that compare a provisional candidate with existing real AlertDecisionEngine
classification preserve the possibility of thermal escalation. The permissive downstream
EpisodeReviewModel scenario emits one advisory and one critical transition rather than
many duplicate events. That demonstrates presentation semantics ONLY. It does not prove
that the partial deserved an alarm, and a later revision cannot safely erase an already
issued critical alarm under the current immutable-event protocol.

**Preserving a partial as eligible evidence is not a guarantee that a partial-only genuine
call will sound a siren.** That unresolved liveness/authority requirement is precisely why
this remains a test-only reference and application runtime stays unchanged.

### Review-driven corrections

The separate reviewer found a reference-model defect: a finalized utterance could not
accept later health-control records, and a fault/gap on another utterance could leave
retained candidates reporting healthy/continuous state. Three new regressions failed
before correction. Session-wide health/continuity now overlays all exported candidates,
while raw observations and finality remain unchanged. No runtime file was modified.

## E. Baseline and final test results

All executed recognition inputs are synthetic, with mocked engines, clocks/timers and
finite queues. Real Python decision logic and AST-extracted store tests are exercised
only on synthetic temporary state. No backend startup or real sensor/model is imported
by the new reference module. Existing safe tests were retained; no expectation or xfail
annotation from C1.45 was changed.

| Stage | Run | Failures | Errors | Outcome |
|---|---:|---:|---:|---|
| C1.45 baseline before edits | 173 | 0 | 0 | PASS, 11.648 s |
| Read-result counterexamples against current flattening helper | 3 | 3 | 0 | Expected RED: finality/full payload missing; identical text indistinguishable |
| Test-only structured reader | 3 | 0 | 0 | GREEN |
| Tracker contracts before tracker implementation | 33 | 22 | 0 | Expected RED: tracker-presence assertion guards; 11 other tests passed |
| First tracker plus existing counterexamples | 33 | 0 | 0 | PASS |
| Initial full selected suite | 206 | 0 | 0 | PASS, 15.992 s |
| Review regression: fault propagation and controls after final | 2 | 2 | 0 | Expected RED against first reference model |
| Review regression: session continuity gap | 1 | 1 | 0 | Expected RED against first reference model |
| Corrected focused module | 36 | 0 | 0 | PASS, 0.612 s |
| Independent reviewer focused rerun | 36 | 0 | 0 | PASS, 0.584 s |
| Final full selected mocked suite | 209 | 0 | 0 | PASS, 11.763 s |

The tracker-contract red guards established that the new model was not yet implemented;
those 22 failures are NOT claims of 22 runtime defects. The first three red tests do
exercise the actual C1.45 helper's metadata loss. All final tests have zero expected
failures, unexpected successes or skips. Passing known-failure characterizations does
not mean the current runtime failure mechanisms were fixed.

Focused command:
```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest test.test_vosk_hypothesis_revision -q
```

Final selected command:
```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest \
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

Diagnostic output was captured in memory for the combined suite. No broad discovery,
Flutter build/runtime, actual acoustic replay or hardware test was run.

## F. Safety and missed-distress regression coverage

All requested synthetic cases are covered:
- Exact partial tulong -> final tulog, including reset-insensitive and reset-aware
  current-worker fixtures. The reference revises the active candidate, not history.
- Partial tul -> final tulong; direct final tulong; partial-only tulong without endpoint.
- Multiple revisions and repeated partials without new emergency event identities.
- Empty final, explicit silence/gap controls, missing sequences, engine exceptions,
  session restart and stale retry ordering.
- Separate genuine final calls with independent segment identities; existing cooldown
  behavior remains covered by C1.45 and current-worker tests.
- Simultaneous openWakeWord detection continues without waiting for Vosk finality.
- An actual mocked Snowboy pending help survives provisional tracking. These tests
  demonstrate that the DISCONNECTED reference does not cancel help; current runtime
  cancellation behavior is not thereby corrected.
- Identical partial voice .40 remains available for advisory classification with
  negative thermal and critical classification with positive thermal using real decision
  code. Provisional authority is still unresolved. A revised-away keyword is no longer
  eligible for a NEW current classification; old critical delivery must not be erased.
- Existing UUID idempotency, immutable event conflicts, publication, replay and per-phone
  acknowledgement regressions continue to pass in the selected suite.

Current critical recovery and manual emergency controls are unchanged. Future revision
messages must be separate observations/status, not rewritten alert envelopes or inferred
user confirmation. Independent source alerts must not be cancelled by uncertain Vosk text.

## G. Remaining acoustic validation requirements

Before selecting an emergency authority rule, separately authorize a representative,
provenance-reviewed replay experiment with frozen recognizer/model/preprocessing config.
Include all 17 keywords/30 aliases, partial-only and interrupted distress, true endpoints,
word revisions, near-word negatives, silence/noise, simultaneous sources, engine gaps,
queue drops and genuine repeated calls. No such audio/model use occurs in C1.46.

Measure actual partial/final sequences, endpoint delivery under current speech gating,
ASR revision rates, alert/cancellation outcomes, recall, false activations and time-to-alert
with denominators and speaker/session separation. Compare full-stream versus speech-gated
recognizer input without interfering with the current capture owner. This is a future
reviewed experiment, not authorization to change a service or record audio.

Unresolved software contracts also include acquisition-clock/session identity, voice-to-
thermal association lifetime, durable observation receipts and event transitions,
partial-confirmation authority, correction presentation, resource limits and crash recovery.
The reference ledger is unbounded, in-memory, single-threaded and fixture-scoped. Its
ordering rejection is not a complete out-of-order transport-reconciliation strategy.
Final ASR text still is not acoustic ground truth. No accuracy improvement is claimed.

## H. Modified file inventory

C1.46 adds only:
1. test/vosk_hypothesis_reference.py — structured reader and test-only revision ledger.
2. test/test_vosk_hypothesis_revision.py — 36 synthetic lifecycle/reference regressions.
3. docs/C1_46_vosk_hypothesis_revision_report.md — this report.

No existing file is changed by C1.46. Pre-edit hashes of all existing modified/untracked
C1.43/C1.44/C1.45 artifacts are retained for final verification. The three pre-existing
tracked C1.45 modifications remain exactly as before this task. Evaluation HEAD remains
8a44f10 with a clean working tree. No Git index/HEAD/branch mutation occurred.

## I. Deployment readiness decision

**BLOCKED.** Safe handling cannot be completed by a final-only gate, repeated-partial
count or unvalidated timeout. The reference fixes metadata loss in its own test-only
reader, retains revisable evidence and separates it from independent cancellation,
but supplies no supported siren authority rule or guaranteed partial-only emergency
liveness. Current runtime still publishes/reset exact partial matches. Existing C1.45
recognition recall and C1.44 episode/thermal-association blockers remain.

A separate read-only reviewer inspected the two new files and ran the permitted focused
module. After three review-driven regressions were corrected, no unresolved correctness
finding remained in the test-only artifact. The reviewer explicitly distinguished this
from production readiness and declined runtime integration, threshold/timing selection,
services, audio/model access, databases/queues and deployment.

## J. Recommended next milestone

**C1.47 — Observation contract and authority-policy validation.** First specify an opt-in,
finality-aware observation interface with source/session/segment identity, acquisition
metadata, independent engine paths and immutable correction records. Add mocked crash,
ordering and per-phone recovery fixtures before connecting it to any runtime path.

Then, only under separate acoustic/model authorization, evaluate actual hypothesis and
endpoint traces and choose an explicit partial-only emergency authority/latency policy.
Provisional evidence must remain available for thermal reevaluation; it must not silently
veto independent help or bypass existing critical-event idempotency/recovery. Deployment
should await reviewed acceptance evidence, rollback and explicit authorization.
