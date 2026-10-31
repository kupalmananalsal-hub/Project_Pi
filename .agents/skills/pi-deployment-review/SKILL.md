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
   - `required` is the mode for any shared network: every `/api` and `/ws` route requires `Authorization: Bearer` except `/ws/alerts?protocol=2` (caregiver secret), and APKs without the token get 401. `open` (**no authentication**) needs `PROJECT_PI_OPEN_MODE_ACK=isolated-network-verified` and an isolated hotspot; never describe it as secure, and never treat the old app's public legacy token as authentication. Anything missing or invalid runs **locked** (every request refused, protocol v2 included; detection keeps running; KWS holds alerts); check `journalctl -u thermal-backend` for `api_auth_mode=` and `API LOCKED`, and `/var/lib/project-pi/backend/auth_fault`. The installer's `--apply` needs `--api-auth`, never prints the token, and never edits an existing `backend.env`. Port 8080 (`apk-server.service`) is unauthenticated: include it in the network review. The token travels over plain HTTP: authentication is not encryption, so deployment needs a trusted isolated network or encrypted transport (not provided); shared Wi-Fi stays blocked until one is verified.
   - The Pi's untracked production files are listed in `raspberry_pi/config/protected_assets.txt`; `? ` entries are provisional and block both scripts until confirmed read-only on the Pi. The scripts are new in the reviewed commit, so they are first extracted with `git archive` into a separate directory (step 0a), never by switching the checkout. `preupgrade_backup.sh` (authorized) snapshots them; `preupgrade_inventory.sh` (read-only) must print `PASS` for the target commit before any checkout, and blocks any local untracked or ignored file that the target would overwrite. The checkout moves only through `preupgrade_switch.sh` (fatal checks: reviewed blobs, on `origin/main`, inventory for the exact target; then a fast-forward and `PRESWITCH_VERIFIED`); runbook blocks run in `bash -euo pipefail` so a `STOP` exits. `install_headless.sh --apply` requires `--backup-dir`, refuses unless `PRESWITCH_VERIFIED` names `HEAD`, and re-runs the gate. Tokens are rotated only with `rotate_api_token.sh` (never on a command line). Never `git clean`, `reset --hard` or `checkout -f`.
   - The thermal metadata threshold (0.05) is not proof of the runtime threshold: record the installed unit's `THERMAL_HUMAN_MODEL_*` values; treat model, threshold, `LGPIO_CHIP` and MLX90640 variant as deployed-but-unvalidated.
   - Root runs only `/usr/local/sbin/project-pi-{refresh,boot,log-cleanup}`, copied by `install_headless.sh --apply`; sudoers lists exact commands and no repo path. The installer is a dry run unless `--apply` (which requires `--rollback-commit=SHA`, `--api-auth` and `--backup-dir`; on any failure it undoes files and units, reports `ROLLBACK VERIFIED` or `ROLLBACK INCOMPLETE`, and never changes the git checkout), backs up replaced files to `/var/lib/project-pi/install-backups/`, never installs packages or runs nmcli, and restarts only with `--restart`. `/api/refresh` pulls only when `/etc/project-pi/allow-app-git-deploy` exists.
   - Device-specific thermal settings (`LGPIO_CHIP`, rate, variant, model paths) live in `thermal-backend.service.d/10-local.conf`, created once and never overwritten. Package versions must match `raspberry_pi/requirements/*.lock.txt`.
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
