# Milestone 1–2 upgrade and rollback (Raspberry Pi + Android)

**Status: prepared, not executed.** Running any part of this on the Pi is a
Level 4 deployment under the [shared policy](agent_integrations/policy.md) and
needs explicit owner authorization. Software tests are not physical certification.

Milestone 1–2 is a set of **reviewed product changes**, not tooling: it adds
optional API authentication (off by default), and changes sudoers, systemd units,
root-run scripts, microphone ownership, the KWS alert outbox location and Android
background behavior. It does
**not** change the alert decision policy, models, thresholds, SQLite schema,
datasets or recordings.

## What changes on the Pi

| Area | Before | After |
|---|---|---|
| API auth | Token checked on 5 endpoints; public default `project-pi-local-token` | **Off by default (no-token mode)**: every route is open and the backend logs a warning at start. Enabled by setting `PROJECT_PI_API_TOKEN` (and optionally `PROJECT_PI_API_AUTH=required`): then a bearer token is required on every `/api` and `/ws` route except `/ws/alerts?protocol=2` (caregiver secret). Enabled with a missing, short (<16) or public-default token: the backend refuses to start. |
| Auth configuration | Hard-coded default | `/etc/project-pi/backend.env` (root, `0600`), created once by the installer with auth off, never overwritten; loaded by systemd `EnvironmentFile=-` (optional) into `thermal-backend` and `kws-alert` |
| Root-run scripts | `pi_refresh.sh`, `headless_boot.sh`, `log_cleanup.sh` run from the thesis-writable repo | Root-owned copies `/usr/local/sbin/project-pi-{refresh,boot,log-cleanup}`, installed only by `install_headless.sh` |
| sudoers | thesis may run repo scripts as root | Exact commands only (see `raspberry_pi/sudoers/project-pi-thesis`); no repo paths |
| Unit files | Re-copied from the repo by the boot service on every boot | Installed only when an admin runs `install_headless.sh` |
| `/api/refresh` | Root script does `git pull` and reinstalls units | Backend runs `git pull` as thesis; root helper only restarts services |
| Microphone | Backend and KWS could both open the ReSpeaker | KWS is the single capture owner; backend reads KWS's published audio status |
| KWS outbox | `/tmp/project_pi_alerts.jsonl` (tmpfs), truncated by log cleanup | `/var/lib/project-pi/backend/alerts.jsonl` (systemd `StateDirectory`, thesis `0700`), fsynced, capped at 500 |
| Caregiver credentials | `PROJECT_PI_CAREGIVER_CREDENTIALS` unset | Set in `backend.env` to `/var/lib/project-pi/backend/caregivers.json` |
| Thermal refresh | Hard-coded 4 Hz | `THERMAL_REFRESH_HZ` in the unit, default 2 Hz |
| Health | Silent | Backend raises a `system_fault` event (never critical/siren) once per outage of KWS or thermal |

Unchanged and untouched by both upgrade and rollback: `raspberry_pi/backend/alerts.db`
(no schema change), `dataset/`, `~/voice_samples`, model files, the noise
suppression config.

## Compatibility rules that set the order

- **New APK + old Pi: works.** With no token entered, the app sends no
  `Authorization` header, which the old backend does not require.
- **Old APK + new Pi in no-token mode (the default): expected to work.** The old
  app's request shapes (no header; the old public token on control routes) pass
  the middleware in no-token mode; this is tested at the HTTP/WebSocket level, not
  with an installed old APK. The old APK lacks the background monitoring, retry
  and banner improvements, so upgrade phones anyway.
- **Old APK + new Pi with auth enabled: does not work** (401 everywhere).
- **New code before the installer runs:** the old unit files are still in place,
  so the backend starts in no-token mode; root helpers, sudoers and the new outbox
  path take effect only after the installer. Run it straight after the checkout.

## 0. Pre-upgrade checks and backups (on the Pi, as `thesis`)

Stop if any check fails.

```bash
cd ~/Project_Pi
git status --short                      # must be empty; stop if the Pi checkout has local edits
git rev-parse HEAD                      # record as ROLLBACK_COMMIT
ls -la /tmp/project_pi_alerts.jsonl     # should not exist (= no undelivered alerts); see step 3 if it does
ls /etc/sudoers.d/                      # expect project-pi-thesis (and optionally project-pi-power, power commands only)
systemctl show -p Environment thermal-backend.service | tr ' ' '\n' | grep -E 'CAREGIVER|ALERT_DB_PATH' || true
systemctl cat thermal-backend.service kws-alert.service | grep -n '^# /' # lists drop-in overrides, if any
```

If `PROJECT_PI_CAREGIVER_CREDENTIALS` was already set (drop-in), note its path:
`EnvironmentFile=` values take precedence over `Environment=`, so after the
upgrade `backend.env` must point at the same file (step 4).

Back up (read-only for project data; nothing is modified):

```bash
B=~/project-pi-backups/pre-m1m2-$(date +%Y%m%d-%H%M)
mkdir -p "$B" && chmod 700 "$B"
git rev-parse HEAD > "$B/ROLLBACK_COMMIT"
python3 -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close()" \
  raspberry_pi/backend/alerts.db "$B/alerts.db"
sha256sum dataset/audio/openwakeword_models/* > "$B/models.sha256" 2>/dev/null || true
sudo cp -a /etc/sudoers.d /etc/project-pi "$B/" 2>/dev/null || true
sudo cp -a /etc/systemd/system/thermal-backend.service /etc/systemd/system/kws-alert.service \
  /etc/systemd/system/apk-server.service /etc/systemd/system/project-pi-boot.service \
  /etc/systemd/system/project-pi-log-cleanup.service /etc/systemd/system/project-pi-apt-update.service \
  /etc/systemd/system/project-pi-apt-update.timer /etc/systemd/system/project-pi-log-cleanup.timer \
  /etc/systemd/system/project-pi.target "$B/"
sudo cp -a /etc/systemd/system/thermal-backend.service.d /etc/systemd/system/kws-alert.service.d "$B/" 2>/dev/null || true
```

Run the SQLite backup as `thesis`, never as root: root would leave root-owned
`-wal`/`-shm` files that the backend cannot open.

## 1. Phones first (Pi still on the old version)

1. Build the APK from the reviewed commit and install it on every caregiver and
   resident phone.
2. Open the app. On first connect Android shows the persistent "Monitoring for
   distress alerts" notification and asks to exempt the app from battery
   optimization; accept.
3. Confirm the app still connects to the **old** Pi (status, thermal, alerts).
   Leave the API token field empty (no-token mode).

## 2. Pi code (as `thesis`)

Deploy only after the PR is merged: `<REVIEWED_COMMIT>` must be on `origin/main`
(the repo squash-merges, so a PR-branch commit would leave `main` diverged and every
later app Refresh would fail). The Pi stays on a `main` branch that tracks
`origin/main`, because the app's Refresh runs `git pull --ff-only` and refuses a
detached checkout.

```bash
cd ~/Project_Pi
git status --short                                    # must still be empty
git fetch origin
git merge-base --is-ancestor <REVIEWED_COMMIT> origin/main || echo "STOP: not on origin/main"
git switch main                                       # creates a tracking main from origin/main if absent
git branch --set-upstream-to=origin/main main
git merge --ff-only <REVIEWED_COMMIT>                 # STOP if this refuses: local main has diverged
git rev-parse HEAD                                    # must equal <REVIEWED_COMMIT>
```

If the fast-forward refuses, do not reset or discard anything: run
`git log --oneline origin/main..main` to see the local commits, back them up
(`git branch backup/pi-local-$(date +%Y%m%d)`) and get them reviewed before retrying.
Do not use the app's Refresh button for this step.

## 3. Installer, immediately after step 2 (as root)

```bash
sudo bash raspberry_pi/scripts/install_headless.sh
```

Add `PROJECT_PI_HOTSPOT_PASSWORD='<new password>'` before `bash` only if you are
rotating the hotspot password (recommended: the previous default is in git
history). Without it the existing `/etc/project-pi/hotspot.env` is kept.

The installer, in order: creates `backend.env` once with auth off (an existing
file, and the auth choice in it, is never overwritten), installs the root-owned helpers, validates then installs
sudoers, installs and enables the units, runs `install_kws_openwakeword_deps.sh`
if `~/kws-env` exists (network, pip), runs the boot script (nmcli, `apt-get
update`, log cleanup) and finally restarts `thermal-backend` and `kws-alert`.
Expect several minutes and a brief alert outage. KWS keeps undelivered alerts in
its outbox across the backend restart. Keyword detection is down from the moment
the installer stops the legacy `kws-alert-vosk.service` (if it is still running)
until `kws-alert` restarts at the end; the installer aborts rather than start a
second microphone owner if the legacy unit fails to stop. Afterwards check:

```bash
systemctl is-active kws-alert.service kws-alert-vosk.service   # expect: active, inactive
```

If `/tmp/project_pi_alerts.jsonl` existed in step 0 and still exists now:

```bash
sudo install -o thesis -g thesis -m 600 /tmp/project_pi_alerts.jsonl /var/lib/project-pi/backend/alerts.jsonl
sudo systemctl restart kws-alert.service
```

## 4. Caregiver credentials

- If step 0 found an existing credentials file, either set that path in
  `/etc/project-pi/backend.env` (`sudo nano`, keep `0600`) or copy it to
  `/var/lib/project-pi/backend/caregivers.json` owned by `thesis`, mode `0600`.
  Restart `thermal-backend`.
- Otherwise provision each phone (writes as `thesis` so the backend can read it):

```bash
sudo -u thesis python3 raspberry_pi/scripts/provision_caregiver.py \
  --installation <ID from the app pairing dialog> \
  --file /var/lib/project-pi/backend/caregivers.json
```

## 5. API token on the phones: only if authentication is enabled

No-token mode (default): nothing to enter; leave **Settings → Pi API token
(optional)** empty in both apps.

With authentication enabled (see "Enabling authentication later"):

```bash
sudo cat /etc/project-pi/backend.env    # PROJECT_PI_API_TOKEN=...
```

Type it into **Settings → Pi API token (optional)** in the caregiver app and in
the resident app. Do not send it by chat/email or paste it into a URL. Without
it the phones show "The Pi requires an API token" and the red "Alerts are NOT
being received" banner.

## 6. Verification (Level 4, with authorization)

```bash
systemctl is-active thermal-backend.service kws-alert.service
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/api/status   # no-token mode: 200; auth enabled: 401
journalctl -u thermal-backend -n 50 --no-pager | grep 'API authentication is DISABLED'   # present only in no-token mode
# Auth enabled only:
sudo bash -c 'source /etc/project-pi/backend.env; curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $PROJECT_PI_API_TOKEN" http://127.0.0.1:8765/api/status'   # expect 200
sudo -l -U thesis                        # only /usr/local/sbin/project-pi-refresh, systemctl restart x3, power
journalctl -u kws-alert -n 50 --no-pager | grep -E 'Listening|disabled|died'
journalctl -u thermal-backend -n 50 --no-pager | grep -E 'ERROR|Health monitor'
sha256sum -c "$B/models.sha256"          # models unchanged
```

Then on a phone: banner gone, thermal/audio live, a spoken test keyword produces
an alert, and the panic button reports "EMERGENCY ALERT SENT".

## No-token mode: what is open

With authentication off, anyone who can reach the Pi on the network can call
every route without credentials: read status, thermal frames, audio levels and
alert history; post or delete alerts; change noise suppression; set LEDs;
upload training data; deploy a keyword model (which restarts KWS); `refresh`
(git pull + service restart); `reboot`; `shutdown`. Nothing about this is secure:
it relies entirely on the network being isolated and trusted (the defense
hotspot with a private password). The caregiver protocol-v2 alert socket keeps its
own per-phone authentication in both modes.

## Enabling authentication later, rotation and revocation

1. Generate a token: `python3 -c 'import secrets; print(secrets.token_hex(32))'`.
2. In `/etc/project-pi/backend.env` (`sudo nano`, keep `0600`), uncomment
   `PROJECT_PI_API_AUTH=required` and set `PROJECT_PI_API_TOKEN=<token>`.
3. `sudo systemctl restart thermal-backend.service kws-alert.service`.
4. Enter the token on every phone (step 5).

`PROJECT_PI_API_AUTH=required` makes a later typo or deleted token stop the
backend instead of silently reopening every route. Rotate by replacing the token
and repeating steps 3–4; turn auth off by commenting both lines out again. Revoke one caregiver phone's alert delivery by deleting
its entry from `caregivers.json` and restarting `thermal-backend`.

## Rollback

Restores the previous code and system configuration; preserves SQLite data,
recordings, models and datasets (none are modified by the upgrade).

```bash
cd ~/Project_Pi
B=~/project-pi-backups/pre-m1m2-<timestamp>
git checkout "$(cat "$B/ROLLBACK_COMMIT")"                    # as thesis; detached on purpose
sudo visudo -cf "$B/sudoers.d/project-pi-thesis" && \
  sudo install -o root -g root -m 0440 "$B/sudoers.d/project-pi-thesis" /etc/sudoers.d/project-pi-thesis
sudo cp -a "$B"/*.service "$B"/*.timer "$B"/*.target /etc/systemd/system/
sudo cp -a "$B"/*.service.d /etc/systemd/system/ 2>/dev/null || true
sudo systemctl daemon-reload
# Carry undelivered KWS alerts back to the old outbox path:
if [ -s /var/lib/project-pi/backend/alerts.jsonl ]; then
  sudo install -o thesis -g thesis -m 600 /var/lib/project-pi/backend/alerts.jsonl /tmp/project_pi_alerts.jsonl
fi
sudo systemctl restart thermal-backend.service kws-alert.service
```

- The rollback checkout is detached on purpose, so the app's Refresh cannot
  fast-forward the Pi back onto the new code; Refresh with `git_pull` fails at
  `git pull` until someone runs step 2 again.
- Leave `/etc/project-pi/backend.env`, `/var/lib/project-pi/backend/` and the
  `/usr/local/sbin/project-pi-*` helpers in place; the old units do not use them.
  Remove them only once rollback is confirmed final.
- Phones need no rollback: the new APK works with the old backend. Clear the
  token field to avoid sending it to the old backend.
- Only restore `$B/alerts.db` if the live database is damaged: stop
  `thermal-backend`, copy it back as `thesis`, start the service. Restoring it
  otherwise discards alerts recorded after the backup.
- Rolling back reinstates the old sudoers, which lets `thesis` run repo scripts
  as root. Treat a rollback as temporary.

## Remaining physical tests (not covered by software tests)

1. `install_headless.sh` end to end on the Pi, including `visudo` validation.
2. ReSpeaker single-owner capture: KWS restarts (x5) while the app streams
   `/ws/audio`; KWS must come back every time.
3. MLX90640 at 2 Hz on the fitted variant; unplug for 30 s and re-plug; the
   backend must recover without restart and its open file count must stay flat.
4. Health monitor: stop `kws-alert` for over 1 minute; exactly one
   `system_fault` reaches the phone, with no siren.
5. Android: screen off for 10 minutes, then a spoken keyword alarms within about
   5 s; app swiped from recents still alarms; battery drain over 8 hours recorded.
6. Wi-Fi drop of 20 s: the alert link must recover within about 10 s; Pi power
   cut with the app open: the app must reconnect without a tap.
7. Panic button during a Wi-Fi blip of under 30 s: one alert recorded, not
   duplicates.
