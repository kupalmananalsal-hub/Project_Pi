# C1.43 — Offline keyword rearming engineering report

Status: isolated, tested prototype; NOT a deployable alarm correction.
Base: 8a44f109fae8adb4b7daa833c15548b56ccd2452.
Workspace: /var/tmp/Project_Pi_C1_43_alarm_fix (detached worktree).

## A. Root-cause mechanism

C1.42 historical counts are supplied evidence, not remeasured here: 4,289 records,
4,273 openWakeWord, 2,374 adjacent same-keyword pairs within ten seconds.
No production database was opened in C1.43.

CooldownGate allows each keyword again after two seconds without observing release.
DetectionDispatcher forwards accepted matches to AlertPoster, which assigns a fresh
UUID per publication. Synthetic timestamps 1000, 1002, 1004 with an unchanged .60
sunog score reproduce three pending events with three different UUIDs through the
real dispatcher and publisher, using fake HTTP and an isolated temporary outbox.
Retrying the first pending event preserves its UUID.

The live openWakeWord loop submits all matching labels, ordered by score. Separate
keywords have separate cooldowns. Existing tulong/help fusion suppression remains
unchanged, including known Vosk hint defects pinned by existing expected failures.
No new cross-keyword or cross-engine arbitration was added.

## Design and test-first execution

Considered: longer cooldown (delays genuine calls and still repeats); one winner
per frame (can suppress distinct genuine calls); per-keyword observed rearming
(selected only as an offline experiment). No recognition thresholds were increased.

Plan executed: inspect gate/dispatcher/score output and stubbed tests; verify baseline;
write score/timestamp expectations and observe red; implement a pure state machine;
verify candidate plus the inspected mocked regression set; review integration risks.

The prototype consumes explicit per-keyword score, existing model threshold,
monotonic timestamp and availability. It returns eligibility reasons only:
- First matching observation: episode_start, immediately.
- A sustained match: no new episode solely because time passes.
- Adjacent valid below-threshold observations spanning release_seconds: rearm.
- Next match after release: episode_start immediately, without a fixed cooldown.
- One rise to critical_threshold during an episode: critical_upgrade immediately.
- Different keywords: independent state; no winner-takes-all suppression.
- Missing, unavailable, invalid or sparse observations: break release evidence.

There are no deployment timing defaults. Fixtures supply release_seconds=0.25 and
max_gap_seconds=0.125 using exactly representable synthetic timestamps. Those values
are experimental examples, NOT validated acoustic settings. The .30 model and .85
critical fixture thresholds are supplied independently; production values are untouched.

## B. Offline files modified

Only three new, untracked files; no existing tracked application files changed:
- tools/keyword_rearming_prototype.py — pure Python eligibility state machine.
- test/test_keyword_rearming_prototype.py — 17 synthetic tests, including baseline
  reproduction through real dispatcher/publisher and a thermal-escalation blocker.
- docs/C1_43_offline_keyword_rearming_report.md — this report.

No dependency on the prototype was added to live KWS or Flutter. No commit, push,
service control, deployment, Docker, installation, microphone use or ML initialization.
Evaluation HEAD and working files remain clean; worktree registration is the intended
Git metadata change. No production files or production database were accessed.

## C. Regression tests and results

Inspected dependencies before running: KWS imports of numpy, PyAudio, Vosk,
requests, preprocessing, noise suppression and wav2vec2 are replaced by test stubs.
The new tests never call main(). Publisher HTTP is a fake session. Persistence tests
use temporary outboxes, never production queues. Bytecode writing was disabled.

Baseline command:
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest test.test_kws_event_id test.test_keyword_fusion test.test_kws_recognition_regression test.test_alert_decision test.test_alert_trace -q
Result: 101 run; 97 passed; 4 expected failures; zero errors; exit 0.

Red phase, before prototype existed:
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest test.test_keyword_rearming_prototype -v
Result: 13 run; 12 assertion failure entries (including subtest entries); zero errors;
exit 1. Two test methods passed: existing dispatcher reproduction and first-match
boundary guards. Expectations exercised the existing gate via a baseline adapter.

Initial green phase: same command, 13 tests passed, exit 0.
Four additional guard/characterization tests then covered interrupted low sequences,
critical onset after release, and the unresolved thermal escalation hazard.

Final selected suite (one process, captured diagnostic output in memory):
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest test.test_keyword_rearming_prototype test.test_kws_event_id test.test_keyword_fusion test.test_kws_live_paths test.test_kws_recognition_regression test.test_alert_decision test.test_alert_trace
Result: 129 run in 10.281 seconds; 125 passed; 4 expected failures; 0 failures,
0 errors, 0 unexpected successes, 0 skipped; exit 0. All 17 new tests passed.

Unresolved expected failures, unchanged:
- RecognitionRegressionTest.test_non_tulong_vosk_hint_does_not_cancel_snowboy_help
- RecognitionRegressionTest.test_ordinary_words_are_not_distress_keywords
- RecognitionRegressionTest.test_partial_prefix_does_not_match_while_word_is_spoken
- RecognitionRegressionTest.test_vosk_hint_does_not_suppress_openwakeword_help

Existing characterization tests deliberately demonstrate recognition defects;
passing them is not evidence that those defects were fixed. Expected diagnostics
for fake backend failures and malformed test policy files are not live outages.
No broad discovery, backend/hardware suite, Flutter build or physical test was run.
The limited, inspected test set follows the explicit lightweight/mock-only constraint.

## D. Distress-call preservation safeguards

First candidate, threshold equality, independent overlapping keywords and one
critical-confidence upgrade are preserved in the prototype. A new episode can be
eligible 0.5 seconds after the previous onset in the synthetic fixture, immediately
on the first match following observed release. Missing predictions are not silence.
Original event IDs, retry behavior, policy, thermal logic, manual emergency controls,
backend critical delivery, Vosk/Snowboy paths and Flutter output are untouched.

Reviewed existing evaluation fixes, without duplicating them:
- The capture loop no longer calls poster.flush(); the alert-poster worker owns
  runtime network posting. AlertPoster still permits synchronous flush when no
  worker is running, as used by offline tests.
- Flutter tracks superseded active IDs and confirms them plus the current ID on
  dismissal. This was source-reviewed only; no Flutter runtime claim is made.

## E. Remaining limitations and stop condition

A score episode is not proven to be an utterance. Real calls might remain above
threshold across separate utterances; noise may create low gaps inside one call.
No release duration or maximum sample gap can be called safe from these fixtures.

Crucially, AudioPreprocessor.process exposes model scores only for speech frames.
An empty scores/wake_words list is not proof of a low model score. Inserting this
prototype into that loop unchanged could leave a keyword latched indefinitely.

The thermal-blocker test uses the real AlertDecisionEngine: voice confidence .40
with negative thermal evidence is advisory; unchanged .40 with positive thermal
evidence is critical. The score-only prototype emits nothing for that unchanged
second observation. Therefore an upstream latch could suppress required escalation.
A confidence-upgrade exception alone does not solve thermal transitions, lost initial
candidates, downstream cooldown rejection, app dismissal or backend restarts.

The prototype reports eligibility, not successful publication. Blindly latching
before dispatcher acceptance can lose a candidate rejected by cooldown or tulong/help
fusion. Retaining the old two-second cooldown also defeats the prompt separate-episode
fixture and can block the prototype's critical_upgrade. No unreviewed bypass was added.

Other limits: per-keyword single-threaded state, no persistence across process restart,
no cross-engine episode identity, no bounded live vocabulary registration, and no
claim about acoustic accuracy or physical siren frequency. Test imports stub engines;
synthetic outputs do not measure recognition precision, recall or rescue effectiveness.

These are the reasons to stop at the isolated prototype under the user's safety rule.

## F. Exact proposed changes for later reviewed deployment

Deploy none of the prototype today. It is not wired into any service.

A later integration must first specify and verify:
1. Per-model raw-score observations on every successful prediction, independent of
   VAD presentation filtering; explicit unavailable/missing observations on failures.
2. A reviewed release criterion and gap bound, validated on separately authorized,
   representative distress episodes and noise/silence fixtures. No arbitrary threshold
   increases and no recording access are authorized by this task.
3. A decision-aware episode/update contract that preserves advisory-to-critical thermal
   transitions, score upgrades, restart and acknowledgement behavior. Reusing an event
   ID with a changed payload currently conflicts with backend fingerprints, so do not
   silently mutate or resend changed events under the same ID.
4. Dispatcher acceptance feedback before consuming episode eligibility, and a reviewed
   interaction with the existing cooldown and tulong/help suppression. Prompt new
   episodes and critical upgrades must not be silently rejected downstream.
5. Mocked end-to-end fixtures from scores through dispatcher, backend decisions,
   persistence, replay and phone disposition before wiring suppression into capture.
6. Preserve all configured keywords; keep distinct-label candidates pending evidence
   for safe correlation. Retain evaluation's existing worker-only posting and Flutter
   superseded-event fixes without duplicating them.

Next safe action: review the thermal-aware episode/update contract and collect only
already-authorized, suitably de-identified score traces if available. Any new audio
access, model inference, hardware test or deployment needs separate authorization.
