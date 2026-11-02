# C1.45 — Offline Recognition Defect Remediation

**Production deployment readiness: BLOCKED.** Text-matcher and dispatcher candidate
corrections are implemented and tested only in the isolated worktree. Acoustic recall,
exact partial-hypothesis revision and emergency latency remain unvalidated.

Workspace: /var/tmp/Project_Pi_C1_43_alarm_fix, detached HEAD
8a44f109fae8adb4b7daa833c15548b56ccd2452. Nothing committed, pushed or deployed.

## A. Baseline and exact root causes

Read C1.43/C1.44 reports and inspected worktree status before editing. Initial changes
were only the six untracked C1.43/C1.44 artifacts; no tracked changes existed. The
original evaluation checkout was and remains clean. No production resource was opened.

The four original RecognitionRegressionTest cases were each called with normal
setup/cleanup, without changing their expectedFailure annotations, and all failed
with the intended AssertionError (not import/runtime errors):

| Original case | Baseline assertion failure | Root cause |
|---|---|---|
| test_ordinary_words_are_not_distress_keywords | Ten strings matched instead of none | Exact aliases, open-ended prefix guessing and a generic SequenceMatcher >= .72 fallback were conflated; one negative fixture contradicted the alias policy |
| test_partial_prefix_does_not_match_while_word_is_spoken | tul returned tulong | Minimum-three-letter prefix rule promoted incomplete text to a completed keyword |
| test_non_tulong_vosk_hint_does_not_cancel_snowboy_help | Expected Snowboy help; got no event | note_vosk_text accepted ANY matched Tagalog keyword, then updated the tulong hint timestamp and cancelled pending help |
| test_vosk_hint_does_not_suppress_openwakeword_help | Expected openWakeWord help; got no event | tulog falsely matched tulong, and immediate help suppression used the latest hint timestamp even without an actual tulong submission |

### A1. Fuzzy guesses versus explicit vocabulary

Baseline synthetic mapping:

| Fixture | Baseline result | Candidate result |
|---|---|---|
| tulog, tuloy, tulo | tulong | None |
| araw, aral | aray | None |
| aga, agad | agai | None |
| sunod, sundo | sunog | None |
| masakit | ang sakit | ang sakit |
| tul | tulong | None |
| tulong | tulong | tulong |
| aray | aray | aray |

The nine non-alias words have different lexical meanings from their matched labels
(e.g. tulog/sleep versus tulong/help; araw/day versus aray/pain interjection). They
are useful negative text fixtures, not proof of non-emergency context in every usage.
A leak, for example, can itself matter in rescue even though tulo is not a configured
distress keyword. No blanket claim about all ordinary language is made.

masakit (painful/it hurts), sakit, nanasakit and sumasakit are explicit pain aliases
and can be legitimate distress vocabulary. The correction retains them. All 30
configured aliases are unchanged, including spelling variants tolong/tulon/tulom,
sakolo/saglolo/saklola and agay. The 17-keyword dataset inventory is unchanged.

The baseline whole-phrase check also used string containment; ang sakitness matched
ang sakit without a complete final token. The candidate requires token boundaries
for multiword aliases as well as single-word aliases.

### A2. Actual caller behavior and partial versus final hypotheses

read_vosk_text() calls AcceptWaveform(), selects Result() for a completed segment or
PartialResult() otherwise, then returns text without exposing finality to its caller.
vosk_worker() sends either kind through the same matcher. A match is submitted at
configured Vosk confidence (or boost-only verification result), then Reset() is called
even if the dispatcher cooldown rejects publication. Worker input is speech-gated.

Therefore the baseline can publish tulong from partial tul before tulog completes.
The new matcher does not guess missing letters. Exact configured alias tokens remain
eligible in BOTH partial and final hypotheses; no endpoint waiting rule was added.

This distinction is explicit in the new scripted-worker tests:
- Incomplete prefix tul -> final tulog: no candidate and no match-triggered reset.
- Incomplete prefix tul -> completed tulong: one legitimate candidate/reset.
- Exact aray, masakit and tulong: still accepted in completed results.
- Exact aray, masakit and tulong with ONLY a partial result: still accepted immediately.
- Exact partial tulong -> final tulog: an early tulong candidate STILL exists.

The last case is a passing characterization of an unresolved failure mechanism,
NOT evidence it was corrected. A text token boundary cannot establish ASR stability.
A final-only alternative would suppress the three partial-only legitimate fixtures;
with speech-gated input, silence needed for Vosk endpointing may never be forwarded.
The synthetic test establishes the logical risk, not its physical frequency/latency.
We do not guess a partial stability duration, raise a confidence threshold, or introduce
a blanket final-only filter without recall/latency evidence.

### A3. Actual dispatcher wiring

The worker calls note_vosk_text(text) immediately before submit(keyword,...,"vosk").
Previously even a legitimate non-tulong keyword (aray, saklolo, sunog, masakit, agai)
could cancel pending Snowboy help. The new tests use those words independently of
araw's false fuzzy match, so fixing the matcher alone cannot hide the cancellation bug.

Actual tulong submission already updates the tulong timestamp and cancels pending
Snowboy help. This existing behavior is retained. A genuine Vosk tulong followed by
Snowboy help still yields tulong only. Same-keyword overlapping sources still share
the existing cooldown. Different labels remain independently publishable.

Immediate help previously used max(last_tulong_at, last_tulong_hint_at). The candidate
ignores a hint-only timestamp for this path while retaining correlation with an actual
tulong submission. A direct exact tulong TEXT HINT without submission no longer vetoes
openWakeWord help. This is separately tested from the raw tulog/tul failures.

Important limitation: an erroneous EXACT partial alias that reaches submit() is still
an actual submission from the dispatcher's perspective. It can retain normal tulong/help
suppression. No claim is made that every possible false-hint or fusion case is solved.

## B. Proposed and implemented offline changes

Only raspberry_pi/kws/kws_alert_dual.py has application-code changes:

1. Remove the open-ended prefix and SequenceMatcher fallback from the text matcher;
   retain the configured alias dictionary and existing keyword precedence.
2. Match aliases as exact contiguous whole-token sequences after existing normalization.
3. Restrict note_vosk_text() to looks_like_tulong(), rather than any distress match.
4. In immediate non-Snowboy help handling, use the actual tulong submission timestamp
   rather than a Vosk text-only hint timestamp.

No numeric recognition, confidence, VAD, noise, thermal, cooldown or fusion-window setting
is changed. This is a lexical matching-policy candidate, not a calibrated threshold
improvement. Removing general fuzzy acceptance can reduce recall for unlisted ASR
variants; that tradeoff requires acoustic evaluation before deployment.

No rearming/episode prototype is connected. Backend decisions, sensor handling,
critical delivery, Flutter output, manual controls, outbox persistence and UUID creation
are not modified. Worker-only runtime posting stays as it was in evaluation.

### Expected-failure annotation review

After the source candidate passed the new tests, the four ORIGINAL assertions were
called again while their markers were still present:
- Partial-prefix, unrelated-help cancellation and false-hint tests passed unchanged.
- The original ordinary-word assertion failed ONLY with {masakit: ang sakit}.

The fourth expectation was corrected transparently: remove masakit from ORDINARY_WORDS,
add masakit -> ang sakit to DISTRESS_PHRASES, keep all nine non-alias negative fixtures.
The new dedicated test also checks all 30 configured aliases, including masakit.
Then the four annotations were removed. This does not make the original contradictory
ten-negative assertion true; it corrects the fixture in accordance with the user's
explicit requirement to preserve legitimate masakit. The nine-word matcher defect is
independently demonstrably corrected by the test-first fixtures.

Existing tests that pinned known bad behavior were updated, not silently dropped:
- test_kws_live_paths: ordinary-word/prefix sequences now expect no candidate; pending
  help and independent openWakeWord help remain; an explicit actual-tulong submission
  regression preserves the existing correlation window.
- test_episode_rearming_review: its four historical defect characterizations now guard
  corrected matcher/dispatcher behavior, including genuine aray not cancelling help.
- C1.43/C1.44 historical reports remain unchanged and accurately describe their runs.

The original regression-file comment required acoustic replay before considering a
recognition fix accepted. The user authorizes this OFFLINE candidate and annotation
review, not acoustic testing/deployment. Updated comments distinguish ordinary passing
text assertions from production acceptance, which remains BLOCKED.

## C. Test-first evidence and baseline versus final results

### Verified-safe execution

Engine/audio/numpy/network dependencies are replaced with existing stubs before KWS
module import. The new worker fixture runs the actual vosk_worker synchronously on a
finite scripted queue, without opening capture or creating a model. Dispatcher timers
and clocks are mocked in the new module. Scripted strings are synthetic, not transcripts
from recordings. Diagnostic output is captured in memory where practical.

Existing storage tests use temporary synthetic stores and fake HTTP. C1.44 tests
AST-extract store/fingerprint code rather than importing backend startup. No production
DB, queue, credential, restricted WAV or microphone is accessed. Bytecode writing is
disabled. No broad test discovery, packages, Docker or hardware tests are run.

| Stage | Run | Passed | Assertion failures | Expected failures | Errors | Result |
|---|---:|---:|---:|---:|---:|---|
| Original selected baseline | 156 | 152 | 0 | 4 | 0 | exit 0, 11.492 s |
| New test-first fixtures BEFORE source edits | 16 | 7 test methods | 30 failure entries across 9 test methods, including subtests | 0 | 0 | exit 1, 0.311 s |
| Same new fixtures AFTER source correction | 16 | 16 | 0 | 0 | 0 | exit 0, 0.289 s |
| Full selected final suite | 173 | 173 | 0 | 0 | 0 | exit 0, 11.371 s |

The red phase failed for unwanted matches/cancellation, not missing imports or errors.
Some tests were baseline preservation/limitation guards and already passed. One guarded
edit attempt aborted before writing; a rerun reproduced the same 16/30 red result before
the corrected edit was applied. No unexplained failing test remains.

The final suite consists of the C1.44 selected 156 tests plus the 16 new tests and one
added actual-tulong correlation test in test_kws_live_paths. No unexpected successes
or skips occurred. Existing cooldown, event-ID retry, decision/fusion, publication,
immutable store, per-phone acknowledgement, replay eligibility and restart tests pass.

Reproducible selected command (from the isolated worktree):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest \
  test.test_recognition_defect_remediation \
  test.test_episode_rearming_review \
  test.test_keyword_rearming_prototype \
  test.test_kws_event_id test.test_keyword_fusion test.test_kws_live_paths \
  test.test_kws_recognition_regression test.test_alert_decision \
  test.test_alert_trace test.test_alert_publication \
  test.test_alert_delivery.DeliveryStorageTest.test_restart_retains_full_envelope_and_uuid \
  test.test_alert_delivery.DeliveryStorageTest.test_concurrent_duplicate_and_conflicting_uuid \
  test.test_alert_delivery.DeliveryStorageTest.test_independent_acks_survive_restart \
  test.test_alert_delivery.DeliveryStorageTest.test_replay_policy_boundaries \
  test.test_alert_delivery.DeliveryStorageTest.test_recovery_cursor_ignores_presentation_but_respects_confirmation_and_age
```

### Independent read-only review

A separate reviewer inspected the candidate and updated tests, and independently ran
only the safe focused module: 16 passed, zero failures/errors, 0.294 seconds. No new
candidate correctness defect requiring an edit was found. The reviewer explicitly
identified retained exact-partial submission/reset/fusion as a high-severity deployment
blocker. Review did not establish acoustic correctness or Android behavior.

## D. Distress-detection regression safeguards

- All 30 aliases remain and are exercised as literal positive fixtures; keyword/alias
  precedence is preserved. All 17 documented keyword labels are unchanged.
- aray, masakit, tulong, spelling variants, multiword phrases and help dispatch remain.
  The Tagalog matcher still does not recognize English help itself; existing English
  recognition sources and dispatch paths retain that responsibility.
- Unrelated non-tulong hints cannot cancel pending Snowboy help; a genuine non-tulong
  Vosk keyword and Snowboy help can both publish.
- Genuine Vosk tulong still cancels pending Snowboy help and suppresses a subsequent
  Snowboy help within the existing correlation window.
- openWakeWord help survives ambiguous/nonmatching Vosk hints and exact hint-only
  tulong; actual tulong submissions retain the existing fusion rule.
- Same-keyword overlapping sources share cooldown; repeated sunog detections at synthetic
  1000/1001/1002 still publish twice, preserving the existing two-second behavior.
  This patch does NOT solve sustained-score repetitions; C1.44 episode design remains
  separate and disconnected.
- C1.43/C1.44 thermal regression tests pass: identical .40 voice followed by new valid
  positive thermal produces critical in the offline downstream reference model. That
  is not a claim that the proposed downstream coordinator now exists in live code.
- Backend UUID uniqueness/fingerprint conflicts, immutable advisory/critical identities,
  HTTP retry identities, per-phone ACK independence and recovery tests pass.
- AST comparisons confirm CooldownGate, AlertPoster, read_vosk_text and vosk_worker
  are unchanged. Git checks confirm backend/main.py, alert_decision.py, alert_delivery.py
  and keyword_dataset_common.py are unchanged. No Flutter application file changed.

## E. Remaining uncertainties requiring validation

1. Exact-alias-only matching can miss unlisted real ASR spelling variants previously
   recovered by fuzzy guessing. Synthetic positives cover the configured vocabulary,
   not actual pronunciation/noise distributions or age/speaker diversity.
2. An exact alias in an unstable partial can still be revised. The explicit passing
   limitation fixture partial tulong -> final tulog emits an early tulong candidate.
   It can also trigger retained fusion suppression. This is not safe for production
   simply because the broad tul/tulog/araw guesses were removed.
3. read_vosk_text still discards finality, and Reset still occurs after a match even if
   publication is cooldown-suppressed. Changing those needs separate endpoint/latency
   and repeat/caller-state tests, not an arbitrary delay or confidence increase.
4. Genuine overlap of different calls/engines, false exact ASR tokens, negated phrases,
   contextual masakit and the existing tulong/help correlation policy need evidence.
   This patch intentionally does not remove valid distress vocabulary or redesign fusion.
5. No actual acoustic false-positive rate, recall, latency, thermal accuracy, Android
   siren behavior, or rescue effectiveness was measured. No accuracy improvement claimed.
6. C1.44 voice/thermal association, episode segmentation and independent thermal lifecycle
   contracts remain unresolved. Rearming is not part of this candidate.

## F. Modified file inventory

C1.45 changed only these six files, all inside the isolated worktree:

| File | Change |
|---|---|
| raspberry_pi/kws/kws_alert_dual.py | Exact whole-token aliases; tulong-only hints; actual-submission-only correlation for immediate help |
| test/test_recognition_defect_remediation.py (new) | Sixteen test-first/preservation/limitation tests with mocked clocks/timers and scripted worker |
| test/test_kws_recognition_regression.py | Retire four justified xfails; move masakit to positives, preserve nine non-alias negatives |
| test/test_kws_live_paths.py | Replace three bad-behavior characterizations; add explicit actual-tulong correlation guard |
| test/test_episode_rearming_review.py | Update four C1.44 matcher/dispatcher characterizations to corrected regression expectations |
| docs/C1_45_recognition_defect_remediation_report.md (new) | This report |

Preserved C1.43/C1.44 reports, rearming prototype, its 17 tests and test-only episode
support model. The original evaluation baseline remains clean at 8a44f10. Worktree
HEAD/index/branch were not changed. No service/unit/model/threshold files were edited.

## G. Production deployment readiness

**BLOCKED.** The specific lexical and cancellation assertions are corrected in offline
source and all selected software tests pass. Unlisted-variant recall and exact partial
hypothesis revision remain unvalidated, including a reproduced premature distress
candidate. No physical false-alarm or latency denominator exists. This candidate must
not be copied into production or treated as a completed recognition-safety fix.

There is no deployment action in this task. Production, databases/queues, recordings,
credentials, microphone, services, swap and boot settings remain untouched. No commits
or pushes were made. The report makes no claim that synthetic tests establish accuracy.

## H. Recommended C1.46 follow-up

C1.46: **Finality-aware hypothesis and fusion validation, with an explicit recall/latency
gate.** First extend the offline scripted-recognizer harness to retain partial/final
status and measure logical outcomes for revisions, missing endpoints, interrupted
phrases, cooldown-rejected submissions and simultaneous independent help. Compare
candidate policies without selecting new timing constants or disabling any engine.

Before acceptance, separately authorize representative acoustic/model replay with a
reviewed corpus, consent/provenance, speaker/session separation and frozen model/config
hashes. Include all 17 keywords, existing aliases (especially masakit/tulon/tolong),
near-word negatives and genuine simultaneous distress; report recall, false activations
and time-to-alert with denominators. No such audio/model access is authorized by C1.45.

Only after that evidence should a reviewed change alter partial acceptance, Reset,
fusion suppression or alias policy. Keep episode/thermal reevaluation work separate
so a recognition fix cannot silently block advisory-to-critical escalation or recovery.
