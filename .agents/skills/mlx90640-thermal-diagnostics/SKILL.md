---
name: mlx90640-thermal-diagnostics
description: Inspect MLX90640 failures and validate offline thermal frames safely.
---

# mlx90640-thermal-diagnostics

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

1. Read ThermalCamera initialization/read retry logic and the Adafruit interface. The backend tries addresses 0x10 and 0x33. The refresh rate comes from `THERMAL_REFRESH_HZ`: the source default is `2` (`raspberry_pi/backend/main.py`) and `thermal-backend.service` sets `Environment=THERMAL_REFRESH_HZ=2`; an unsupported value leaves the sensor unavailable with an explicit error. I2C `OSError`s and bad frames are retried, then the bus is released and re-initialised at most every 2 s. These are code settings, not evidence of connected hardware or of the fitted BAA/BAB variant. Do not change the refresh rate as part of a diagnosis.
2. Approved Level 1 probes may list /dev/i2c-*; do not treat i2cdetect bus scans or getFrame calls as passive filesystem inspection.
3. Validate an offline frame fixture with offline_hil.py --thermal-json PATH: 768 finite values, timestamp freshness, read latency and reported refresh rate. A 32x24 heat map can reveal missing rows or orientation errors but does not prove human detection.
4. Live initialization/frame reads are Level 2 and may conflict with the backend. Require explicit device-read approval and exclusive ownership/maintenance coordination. Stop after bounded failures; no bus reset, clock adjustment or restart.
5. Use Adafruit source as the primary driver reference. Do not route raw MLX frames through LabIR .lrc tooling unless a compatible file format is actually present.

## Errors and verification
Stop the failing operation and report its exact stage. Preserve raw local logs;
redact secrets before sharing. Do not silently escalate privileges or retry a
mutation. Verify conclusions against the checked-out source and report exact
passed/failed/errored/skipped counts. Distinguish mocks, offline files and physical tests.

## Expected output
Frame shape/freshness/latency findings and separate hardware versus fixture evidence.

## References
- [tools/agent_integrations/offline_hil.py](../../../tools/agent_integrations/offline_hil.py)
- [raspberry_pi/backend/main.py](../../../raspberry_pi/backend/main.py)
- [test/test_thermal_confidence.py](../../../test/test_thermal_confidence.py)
