---
name: kws-vad-regression
description: Reproduce KWS and VAD misses/false triggers separately from backend policy.
---

# kws-vad-regression

## Trigger and prerequisites
Use when the user requests this workflow. Start at the repository root and identify
the current branch. Python 3.10+ and the referenced source are required; physical
hardware is optional, never assumed. Missing optional tools are reported as blockers.

## Safe boundaries and approvals
Apply the [shared policy](../../../docs/agent_integrations/policy.md). Default Level 0
is documentation/local analysis. Level 1 needs explicit connection approval;
Level 2 needs explicit capture/sensor-test approval; Level 3 changes and Level 4
deployment need separate reviewed authorization. These instructions grant no shell
permissions. No global installation, private-data upload or automatic merge.

## Required tools and procedure
Use file reads, Git diff and appropriate existing test runners. The bundled Python
helpers are optional and have no import-time hardware actions.

1. Read deployed vocabulary and service thresholds. Keep exactly the existing 17 phrases; do not add unverified Cebuano labels. Do not change thresholds or models.
2. Run isolated Python keyword fusion, alert decision and trace tests; keep test fixtures separate from recognition evidence. Never POST synthetic emergencies to a live backend.
3. For an explicitly approved offline acoustic experiment, freeze model hashes, audio preprocessing, speaker/session splits and source licenses. Include help, tulong, saklolo, sunog, the remaining inventory, hi/hello/kamusta, real silence and environmental/fan noise.
4. Record per-class misses and false activations, speech/nonspeech gating, frame latency and false alarms per observation time. Retain full error traces and denominator values. No model execution tool is activated by this skill.
5. Separately apply policy fixtures for suppressed/advisory/critical/confirmed decisions. An acoustic score or Snowboy placeholder confidence is not a calibrated emergency probability.

## Errors and verification
Stop the failing operation and report its exact stage. Preserve raw local logs;
redact secrets before sharing. Do not silently escalate privileges or retry a
mutation. Verify conclusions against the checked-out source and report exact
passed/failed/errored/skipped counts. Distinguish mocks, offline files and physical tests.

## Expected output
Software test counts plus a separately labeled acoustic evaluation result or blocker.

## References
- [test/test_keyword_fusion.py](../../../test/test_keyword_fusion.py)
- [test/test_alert_decision.py](../../../test/test_alert_decision.py)
- [raspberry_pi/kws/evaluate_keyword_models.py](../../../raspberry_pi/kws/evaluate_keyword_models.py)
