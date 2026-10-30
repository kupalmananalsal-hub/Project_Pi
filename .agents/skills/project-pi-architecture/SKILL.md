---
name: project-pi-architecture
description: Trace Project_Pi component interfaces and ownership from the checked-out source.
---

# project-pi-architecture

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

1. Read `raspberry_pi/backend/main.py` as text: FastAPI endpoints, ThermalSensor, AudioStream, GPIO button, AlertStore and training routes. Do not import the backend just to inspect it: module initialization can acquire devices.
2. Follow `raspberry_pi/kws/kws_alert_dual.py` through audio preprocessing, openWakeWord, Vosk/Snowboy and the POST of event_id to /api/alerts. Inspect systemd unit environment without printing credentials.
3. Read `raspberry_pi/alert_decision.py`, `raspberry_pi/config/alert_policy.yaml`, `raspberry_pi/alert_delivery.py`, and Flutter alert providers/services. Identify persistence-before-publication, protocol-v2 acknowledgements and replay gates from source, rather than assuming transport reliability.
4. Report thermal 32x24 frames, configured audio formats, endpoint ownership and error paths with file/line evidence. Distinguish Resident manual panic from Caregiver presentation. Do not infer deployed Git revision from this checkout.

## Errors and verification
Stop the failing operation and report its exact stage. Preserve raw local logs;
redact secrets before sharing. Do not silently escalate privileges or retry a
mutation. Verify conclusions against the checked-out source and report exact
passed/failed/errored/skipped counts. Distinguish mocks, offline files and physical tests.

## Expected output
An evidence-linked architecture map, interface contracts, and unresolved runtime facts.

## References
- [raspberry_pi/backend/main.py](../../../raspberry_pi/backend/main.py)
- [raspberry_pi/alert_delivery.py](../../../raspberry_pi/alert_delivery.py)
- [raspberry_pi/kws/kws_alert_dual.py](../../../raspberry_pi/kws/kws_alert_dual.py)
