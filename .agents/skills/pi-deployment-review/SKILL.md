---
name: pi-deployment-review
description: Prepare a read-only Pi deployment preflight and rollback review without deploying.
---

# pi-deployment-review

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

1. Record local revision, base/head, dirty files and protected data/model paths. Read systemd diffs without applying units. Preserve .cursor and independent branches/PRs.
2. Review appropriate Python and Flutter test evidence, client/server protocol compatibility, model checksums, data/consent boundaries and backup/restore procedures. Tests alone are not physical certification.
3. Level 1 remote preflight is optional and requires approved read-only SSH. Do not fetch/pull on the Pi, run installers or restart services as a preflight side effect.
4. Write a concrete deployment proposal: exact reviewed commit, affected units/files, backups, rollback revision, health criteria and stop conditions. Deploying, changing configuration and controlling services are separate Level 3/4 operations requiring explicit authorization.
5. Do not merge, enable/disable units, alter boot overlays or overwrite models. Review toolkit uninstall separately from device rollback.

## Errors and verification
Stop the failing operation and report its exact stage. Preserve raw local logs;
redact secrets before sharing. Do not silently escalate privileges or retry a
mutation. Verify conclusions against the checked-out source and report exact
passed/failed/errored/skipped counts. Distinguish mocks, offline files and physical tests.

## Expected output
A reviewable preflight/rollback checklist with no deployment performed.

## References
- [raspberry_pi/systemd/kws-alert.service](../../../raspberry_pi/systemd/kws-alert.service)
- [raspberry_pi/systemd/thermal-backend.service](../../../raspberry_pi/systemd/thermal-backend.service)
- [docs/agent_integrations/rollback_guide.md](../../../docs/agent_integrations/rollback_guide.md)
