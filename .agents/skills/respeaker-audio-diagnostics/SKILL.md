---
name: respeaker-audio-diagnostics
description: Diagnose ReSpeaker enumeration, format, silence and clipping without changing drivers.
---

# respeaker-audio-diagnostics

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

1. Establish exact HAT model/revision, codec, OS/kernel, ALSA card, overlays and currently working capture path. The service MIC_NAME_HINT is a hint, not hardware identity. Compare against official Seeed revision documentation.
2. Use approved read-only ALSA probes. Inspect KWS_CHANNELS/KWS_CHUNK_FRAMES and audio status code. Compare mono recognition preprocessing to stereo direction estimation; never discard raw stereo evidence.
3. Prefer an already consented local WAV: run offline_hil.py --audio-wav PATH for rate/channels/duration/RMS/clipping. This does not measure VAD or capture latency. For those, instrument a separately approved offline fixture runner with monotonic timestamps and preserve frame timings/results.
4. A new short capture is Level 2: obtain consent and explicit device/duration/output approval first, coordinate with running capture services, and use the project recorder only after checking its branch-specific implementation. Never transmit recordings or auto-edit ALSA/mixer/boot configuration.
5. Compare silence, fan noise and real speech; distinguish invalid capture from classifier misses. Stop on device contention and propose a maintenance window.

## Errors and verification
Stop the failing operation and report its exact stage. Preserve raw local logs;
redact secrets before sharing. Do not silently escalate privileges or retry a
mutation. Verify conclusions against the checked-out source and report exact
passed/failed/errored/skipped counts. Distinguish mocks, offline files and physical tests.

## Expected output
Format and signal findings, verified hardware facts, unknowns, and consented follow-up plan.

## References
- [tools/agent_integrations/offline_hil.py](../../../tools/agent_integrations/offline_hil.py)
- [raspberry_pi/kws/record_keyword_dataset.py](../../../raspberry_pi/kws/record_keyword_dataset.py)
- [docs/agent_integrations/raspberry_pi_diagnostics.md](../../../docs/agent_integrations/raspberry_pi_diagnostics.md)
