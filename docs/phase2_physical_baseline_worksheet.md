# Phase 2 physical baseline worksheet

Status: NOT RUN. Prepared 2026-10-30. Baseline commit: `cf9fd0e8817094617ea1f38ff05e25156c8e720f`.

This worksheet does not establish device success. Complete it on the deployed Raspberry Pi 5 and Android Caregiver before Phase 3 architectural changes, unless the prerequisite is explicitly deferred. Automated tests and synthetic HTTP input must be identified separately from real keyword-detector trials.

## Record the deployment

Record Pi model, OS, backend and detector commit/configuration identifiers, Android model and OS, installed app build/commit, notification permissions, volume/DND state, battery restrictions, network arrangement and whether the app is foreground or background. Record clock offsets or synchronization method; cross-device wall-clock latency is not valid without accounting for clock offset. Do not record secrets or raw audio.

## Trials

Use a new event ID for each distinct event. For a duplicate trial, resend the identical original request with the same event ID. Preserve the producer timestamp and request fields; changing those fields is a conflict test, not an identical retry. Obtain the backend-generated event ID for Resident manual alerts from the response or trace.

| Trial | Expected Phase 2 disposition | Actual result |
| --- | --- | --- |
| Thermal-confirmed `confirmed` | Full overlay, alarm and vibration; thermal label agrees with event evidence | NOT RUN |
| Voice-only `critical`, thermal negative | Full overlay, alarm and vibration; no positive thermal claim | NOT RUN |
| Voice-only `critical`, thermal unavailable/stale | Full overlay, alarm and vibration; actual thermal state shown | NOT RUN |
| Resident double tap | Full emergency; manual source does not itself imply human presence | NOT RUN |
| Advisory | Notice only | NOT RUN |
| Suppressed | No emergency outputs | NOT RUN |
| Identical event ID retry | No repeated handling | NOT RUN |
| Dismiss while alarm runs | Overlay, alarm and vibration stop; subsequent new event still works | NOT RUN |
| Earlier local positive thermal frame, current backend negative | Label follows current backend evidence; record any discrepancy | NOT RUN |

Run each required emergency type with the intended deployment app state and record that state. Do not infer background, locked-screen or DND performance from a foreground trial. Any simulated detector or thermal input must be labeled as simulated; do not change recognition thresholds or research data for these trials.

## Evidence for each trial

Record the trial identifier, event UUID, input method (real detector / synthetic POST / Resident double tap), UTC timestamps and log locations. Copy the exact structured records from detector, HTTP result, backend decision, persistence, publication, WebSocket send, Flutter receipt/parsing, provider disposition, overlay and each output attempt. Mark missing stages as unobserved rather than successful.

Separately record what a person observed: overlay wording, audible sound, vibration, dismissal response and whether another event could activate afterward. An `initiated` or `completed` plugin trace alone is not a physical sound/vibration result. Record last successful software stage and last physically observed action separately, including any error or suppression reason.

For elapsed time, use one clock or synchronized clocks with the offset recorded. Keep individual trial measurements; report sample count and measurement method with any aggregates. Do not substitute test counts for delivery reliability or latency measurements.

## Result record template

```text
Trial / event_id:
Pi / Android build identifiers:
Input method and app state:
Clock synchronization / offset:
Backend decision / thermal state / reason:
Exact trace records or evidence paths:
Last successful software stage:
First failed or unobserved stage / reason:
Overlay observed / actual wording:
Sound observed:
Vibration observed:
Dismissal observed:
Subsequent alert observed:
Measured latency / measurement method:
Outcome: PASS / FAIL / INCONCLUSIVE
Operator / UTC time:
```

Keep failures in the baseline record. A known source defect is not a physical observation until reproduced on the device. Document whether architectural work was permitted after these results or explicitly authorized before hardware validation.
