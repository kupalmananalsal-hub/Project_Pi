---
name: pi-safe-diagnostics
description: Inspect Pi system health with bounded read-only probes after connection approval.
---

# pi-safe-diagnostics

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

1. Run the preflight helper without execution flags to print its fixed command plan. This default performs no subprocesses or networking.
2. Before Level 1, obtain explicit connection approval and an allowlisted host, non-root account, existing key and independently verified known-hosts entry. Follow the SSH example and security review. Never accept an unverified replacement host key.
3. Run only approved probes for OS/kernel, Python, CPU temperature, memory/storage, services, ALSA enumeration, interface filenames, model presence and loopback /api/status. Probes do not open microphones or I2C sensors.
4. Report missing dependencies and permission errors without installing software, retrying with sudo, restarting services or switching drivers. The default model path is a deployment assumption; absence is not proof that models are absent everywhere.

## Errors and verification
Stop the failing operation and report its exact stage. Preserve raw local logs;
redact secrets before sharing. Do not silently escalate privileges or retry a
mutation. Verify conclusions against the checked-out source and report exact
passed/failed/errored/skipped counts. Distinguish mocks, offline files and physical tests.

## Expected output
Probe statuses, truncated/timeout flags, local private audit-log location, and next proposed check.

## References
- [tools/agent_integrations/read_only_pi_preflight.py](../../../tools/agent_integrations/read_only_pi_preflight.py)
- [docs/agent_integrations/security_review.md](../../../docs/agent_integrations/security_review.md)
