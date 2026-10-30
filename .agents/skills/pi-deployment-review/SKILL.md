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
6. Check the deployment surface introduced by Milestone 1–2 (reviewed product changes, not tooling) against [the upgrade and rollback procedure](../../../docs/m1_m2_upgrade_and_rollback.md):
   - `/etc/project-pi/backend.env` (root `0600`, created once by the installer, never overwritten) holds the API auth choice (`PROJECT_PI_API_AUTH`, `PROJECT_PI_API_TOKEN`) and `PROJECT_PI_CAREGIVER_CREDENTIALS`; both units load it with `EnvironmentFile=-`, which overrides `Environment=` drop-ins. Never print, log or put a token in a URL.
   - API auth is **off by default (no-token mode)**: every route, including refresh, reboot, shutdown and model deploy, is open to anyone on the network, and the backend logs a warning at start. Treat that as acceptable only on an isolated, trusted network; never describe it as secure. When a token is set (or `PROJECT_PI_API_AUTH=required`), every `/api` and `/ws` route requires `Authorization: Bearer` except `/ws/alerts?protocol=2` (caregiver secret), APKs without the token get 401, and a missing, short or public-default token stops the backend at start. Record which mode the deployment uses.
   - Root runs only `/usr/local/sbin/project-pi-{refresh,boot,log-cleanup}`, copied by `install_headless.sh`; sudoers lists exact commands and no repo path. Unit, sudoers and helper changes take effect only when the installer is re-run.
   - Restart order: `thermal-backend` before `kws-alert` (KWS posts alerts to the backend and keeps them in its outbox meanwhile).
   - KWS is the single ReSpeaker capture owner; the backend only reads its published audio status.
   - The KWS outbox lives at `/var/lib/project-pi/backend/alerts.jsonl` (`StateDirectory`, thesis `0700`); log cleanup must never truncate it.
   - Android: the optional API token is entered in Settings (secure storage) only when auth is enabled; a `connectedDevice` foreground service keeps alerts arriving with the screen off.
   - Rollback restores code, sudoers and units from a pre-upgrade backup and leaves SQLite, datasets, recordings and models untouched.

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
- [docs/m1_m2_upgrade_and_rollback.md](../../../docs/m1_m2_upgrade_and_rollback.md)
- [raspberry_pi/sudoers/project-pi-thesis](../../../raspberry_pi/sudoers/project-pi-thesis)
- [raspberry_pi/scripts/install_headless.sh](../../../raspberry_pi/scripts/install_headless.sh)
