# Milestone 1–2 upgrade and rollback (Raspberry Pi + Android)

**Status: prepared, not executed.** Running any part of this on the Pi is a
Level 4 deployment under the [shared policy](agent_integrations/policy.md) and
needs explicit owner authorization. Software tests are not physical certification.

Milestone 1–2 is a set of **reviewed product changes**, not tooling: it adds
optional API authentication (open by default), and changes sudoers, systemd units,
root-run scripts, microphone ownership, the KWS alert outbox and Android
background behavior. It does **not** change the alert decision policy, models,
detection thresholds, keyword lists, VAD settings, the SQLite schema, datasets or
recordings, and it never installs or upgrades packages.

Baseline it must reproduce (read-only audit of the deployed Pi, 2026-10-31): commit
`1a5c309`; Python 3.11.2 venvs whose packages are recorded in
`raspberry_pi/requirements/kws-env.lock.txt` and `thermal-env-sys.lock.txt`; thermal
detector model `thermal_human_detector.tflite` with its metadata threshold (0.05);
`LGPIO_CHIP=11`; MLX90640 at 4 Hz; `kws-alert.service` identical to the repo.

## What changes on the Pi

| Area | Before | After |
|---|---|---|
| API auth | Token checked on 5 endpoints; public default `project-pi-local-token` | `PROJECT_PI_API_AUTH=open` (default): **no authentication**, isolated hotspot only, startup warning. `required`: a bearer token (16+ characters) on every `/api` and `/ws` route except `/ws/alerts?protocol=2` (per-phone caregiver secret); new APK only. The legacy token is never accepted as authentication. `required` with a missing, short or legacy token, or an unknown mode, stops the backend. |
| Auth configuration | Hard-coded default | `/etc/project-pi/backend.env` (root, `0600`), created once by the installer in open mode, never overwritten |
| Root-run scripts | `pi_refresh.sh`, `headless_boot.sh`, `log_cleanup.sh` run from the thesis-writable repo | Root-owned copies `/usr/local/sbin/project-pi-{refresh,boot,log-cleanup}`, installed only by `install_headless.sh --apply` |
| sudoers | thesis may run repo scripts as root | Exact commands only (see `raspberry_pi/sudoers/project-pi-thesis`); no repo paths |
| Unit files | Re-copied from the repo by the boot service on every boot | Installed only by `install_headless.sh --apply` |
| Installer | Writes immediately, upgrades packages, runs nmcli, restarts services | Dry run by default (NEW / IDENTICAL / CHANGED with diffs, package drift report); `--apply` backs up every replaced file first and rolls back every file and unit change if any step fails; restarts only with `--restart`; never installs packages; never touches NetworkManager |
| Startup | Detection units waited for `network-online.target` and the boot script (up to 120 s network wait plus `apt-get update`) | `thermal-backend` and `kws-alert` depend only on `sound.target` (KWS also on the backend): they start without Wi-Fi or internet. The boot script waits for the network only when managing the hotspot and no longer runs `apt-get`; `project-pi-apt-update.timer` does that 15 min after boot, off the critical path |
| `/api/refresh` | Root script does `git pull` and reinstalls units | `git_pull` refused (409) unless the root-owned `/etc/project-pi/allow-app-git-deploy` exists; restart without pull always works |
| Wi-Fi | Boot script could create/modify/activate the hotspot profile | Changed only when `hotspot.env` sets `PROJECT_PI_FORCE_HOTSPOT=1`; otherwise the boot logs the current SSID/IPv4 and changes nothing |
| Microphone | Backend and KWS could both open the ReSpeaker | KWS is the single capture owner (`Conflicts=kws-alert-vosk.service`, legacy unit masked); backend reads KWS's published audio status |
| KWS outbox | `/tmp/project_pi_alerts.jsonl` (tmpfs), truncated by log cleanup | `/var/lib/project-pi/backend/alerts.jsonl`, fsynced; the legacy file is merged in on first start and renamed `*.migrated`; bounded by retention tier (below) |
| Thermal | Hard-coded 4 Hz; installed unit differs from the repo | Generic unit: detector model + metadata, no threshold override, no rate. Rate, variant and `LGPIO_CHIP` live in the local drop-in `thermal-backend.service.d/10-local.conf`, created once from the installed unit |
| Caregiver credentials | `PROJECT_PI_CAREGIVER_CREDENTIALS` unset | Set in `backend.env` to `/var/lib/project-pi/backend/caregivers.json` |
| Backend-rejected alerts | HTTP 4xx (except 401/408/429) silently dropped as "delivered" | Moved, fsynced, to `alerts.rejected.jsonl` (kept for review, never retried, never blocking later alerts; possibly-critical records dropped only at the hard limits, and every such loss counted in the durable `alerts.losses.json`); a possibly-critical rejection or any recorded loss raises a health fault until reviewed |
| Health | Silent | One `system_fault` event (never critical/siren) per outage of KWS, thermal, a `certain_critical` outbox eviction, or a possibly-critical backend rejection |

Unchanged and untouched by upgrade and rollback: `raspberry_pi/backend/alerts.db`
(no schema change), `dataset/`, `~/thesis_dataset`, `~/voice_samples`,
`~/vosk-models`, `~/snowboy`, model files, the noise suppression config,
`/etc/project-pi/*.env` other than creating `backend.env` if absent.

### Thermal refresh rate

The right MLX90640 rate depends on the variant (BAA 110° vs BAB 55°), which has not
been verified on this Pi. The installer therefore seeds the drop-in with
`MLX90640_VARIANT=unverified` and `THERMAL_REFRESH_HZ=4`, labelled
"baseline-preserving, variant not verified": 4 Hz is what this Pi has run at, not a
claim that 4 Hz is right for every variant. If `THERMAL_REFRESH_HZ` is unset the
backend also uses 4 Hz for compatibility, logs a startup warning and reports
`thermal_refresh_source: legacy_default` in `/api/status`. Nothing changes the rate
silently in either direction; change it only in the drop-in, after identifying the
variant.

### KWS outbox retention

An undelivered event has **not** been classified: the backend decides with thermal
evidence when it arrives. KWS tags each queued event with a retention tier from
queue-time facts only, using the same `alert_policy.yaml` (and safe-default
fallback) as the backend. **Tiers are retention hints, not classifications.**

| Tier | Meaning | Events |
|---|---|---|
| 3 `certain_critical` | CRITICAL whatever the thermal state | `manual_button`; voice confidence ≥ `critical_threshold` |
| 2 `possible_critical` | CRITICAL if thermal is positive, else advisory | `advisory_threshold` ≤ confidence < `critical_threshold`; `manual_button_single`; `health_monitor` |
| 1 `certain_suppressed` | Suppressed whatever the thermal state | confidence < `advisory_threshold` |

Above 500 events the oldest tier 1, then tier 2 events are evicted (each logged,
`outbox_pressure` published in the KWS audio status and `/api/status`). Tier 3 is
evicted only at the hard limit (5,000 events or 5 MB), oldest first, with an
error log and a health fault. Disk use is bounded and evictions are never silent.

### Alerts the backend rejects

HTTP 401, 408, 429, 5xx and network errors are retried. Any other 4xx (400 bad
`event_id`, 409 the backend already holds a *different* event under this
`event_id`, 422 invalid payload) can never succeed on retry, so the event is moved
to `/var/lib/project-pi/backend/alerts.rejected.jsonl` with `rejected_status`,
`rejected_detail` and `rejected_at`, written and fsynced before it leaves the
outbox. It is never retried automatically (no retry loop) and never blocks later
alerts. Each rejection is traced (`quarantined`) and logged; a `certain_critical`
or `possible_critical` rejection is logged as an error and raises the health fault
"alert rejected by backend", which stays raised (also across KWS restarts) until
the file is reviewed. Above 500 records only `certain_suppressed` ones are
dropped; possibly-critical rejections are dropped only at the outbox hard limits
(5,000 records or 5 MB), oldest first, each logged as an error.

### Durable loss ledger

Every possibly-critical event that is lost (a `certain_critical` outbox eviction at
the hard limit, or a possibly-critical quarantine eviction) is counted, with a
summary of the event, in `/var/lib/project-pi/backend/alerts.losses.json`, written
and fsynced at the moment of loss. The counts survive KWS restarts and power cuts
and keep the health fault raised until an operator resolves them; the file keeps
the last 100 summaries but its counts are never trimmed. An unreadable ledger is
moved aside (`*.unreadable-<time>`) and itself raises the fault.

### Reviewing rejected and lost alerts (operator only)

Nothing is ever re-sent automatically. As `thesis`:

1. Read `alerts.rejected.jsonl` and `alerts.losses.json` and record what happened.
2. Archive both (`cp -a` to the evidence folder); they are the only trace of these
   events.
3. Re-sending a rejected event is a per-event decision, made only after fixing
   the cause: stop `kws-alert`, append the chosen lines to `alerts.jsonl`, start
   `kws-alert`. Never bulk-copy the file back.
4. Clear the faults by deleting the reviewed files; KWS recreates them on the next
   rejection or loss.

## Compatibility rules that set the order

- **New APK + old Pi: works.** With no token entered, the app sends no
  `Authorization` header, which the old backend does not require.
- **Old APK + new Pi in open mode (the default): expected to work.** The old
  app's request shapes (no header, the old public token, any header) pass in open
  mode; this is tested at the HTTP/WebSocket level, not with an installed old APK.
  Open mode is compatibility, not security. The old APK lacks the background
  monitoring, retry and banner improvements, so upgrade phones anyway.
- **Old APK + new Pi in required mode: does not work** (401 everywhere).
- **Heartbeat:** the caregiver link uses a 5 s heartbeat interval and 5 s timeout
  (`PROJECT_PI_HEARTBEAT_INTERVAL_SECONDS` / `_TIMEOUT_SECONDS` in `backend.env`).
  The pre-PR #9 values were 15 s / 10 s; set those if old APKs churn connections.
- **New code before the installer runs:** the old unit files are still in place;
  root helpers, sudoers, the drop-in and the outbox path take effect only after
  `--apply` and a restart. Run the installer straight after the checkout.

## 0. Pre-upgrade checks and backups (on the Pi, as `thesis`)

Stop if any check fails.

```bash
cd ~/Project_Pi
git status --short                      # must be empty; stop if the Pi checkout has local edits
git rev-parse HEAD                      # record as ROLLBACK_COMMIT
ls -la /tmp/project_pi_alerts.jsonl     # undelivered legacy alerts, if any (merged automatically)
ls /etc/sudoers.d/                      # expect project-pi-thesis (and optionally project-pi-power, power commands only)
systemctl show -p Environment thermal-backend.service | tr ' ' '\n' | grep -E 'CAREGIVER|ALERT_DB_PATH|LGPIO|THERMAL' || true
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
sha256sum dataset/audio/openwakeword_models/* dataset/thermal/models/* > "$B/models.sha256" 2>/dev/null || true
sudo cp -a /etc/sudoers.d /etc/project-pi "$B/" 2>/dev/null || true
sudo cp -a /etc/systemd/system/thermal-backend.service /etc/systemd/system/kws-alert.service \
  /etc/systemd/system/apk-server.service /etc/systemd/system/project-pi-boot.service \
  /etc/systemd/system/project-pi-log-cleanup.service /etc/systemd/system/project-pi-apt-update.service \
  /etc/systemd/system/project-pi-apt-update.timer /etc/systemd/system/project-pi-log-cleanup.timer \
  /etc/systemd/system/project-pi.target "$B/" 2>/dev/null || true
sudo cp -a /etc/systemd/system/thermal-backend.service.d /etc/systemd/system/kws-alert.service.d "$B/" 2>/dev/null || true
```

Run the SQLite backup as `thesis`, never as root: root would leave root-owned
`-wal`/`-shm` files that the backend cannot open. (The installer also backs up
every file it replaces, see step 3; this backup additionally covers rollback of
the code.)

## 1. Phones first (Pi still on the old version)

1. Build the APK from the reviewed commit and install it on every caregiver and
   resident phone.
2. Open the app. On first connect Android shows the persistent "Monitoring for
   distress alerts" notification and asks to exempt the app from battery
   optimization; accept.
3. Confirm the app still connects to the **old** Pi (status, thermal, alerts).
   Leave the API token field empty (open mode).

## 2. Pi code (as `thesis`)

Deploy only after the PR is merged: `<REVIEWED_COMMIT>` must be on `origin/main`
(the repo squash-merges, so a PR-branch commit would leave `main` diverged and every
later pull would fail). The Pi stays on a `main` branch that tracks `origin/main`.

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

First the dry run. It writes nothing and prints the package drift against the lock
files, every target file as NEW / IDENTICAL / CHANGED with a unified diff, the
units it would enable and mask, and whether anything would restart:

```bash
sudo bash raspberry_pi/scripts/install_headless.sh
```

Review it. Stop if the drift section shows a package difference you cannot
explain, or if the seeded `10-local.conf` does not show this Pi's `LGPIO_CHIP=11`,
the detector model and metadata paths, and `THERMAL_REFRESH_HZ=4`. Then apply:

```bash
sudo bash raspberry_pi/scripts/install_headless.sh --apply \
  --rollback-commit="$(cat "$B/ROLLBACK_COMMIT")"                     # installs, restarts nothing
sudo systemctl restart thermal-backend.service kws-alert.service      # or add --restart above
```

`--rollback-commit` is required with `--apply`: the application commit that ran
before this upgrade (the one recorded in step 0; for a reinstall without a code
change, pass the current `HEAD`). The installer only reads git: if `--apply` fails
it reports this commit next to the current `HEAD`, and never changes the checkout.

`--apply` refuses to run on package drift unless `--accept-env-drift` is given
after review. It backs up every replaced file to
`/var/lib/project-pi/install-backups/<UTC timestamp>/` (root, `0700`), creates
`backend.env` and the thermal drop-in only if absent, never edits anything else
in `/etc/systemd/system/*.service.d/`, and stops then masks
`kws-alert-vosk.service` (its unit file is kept in the backup); it aborts rather
than leave a second microphone owner. `thesis-camera.service` is only reported.
If any step of `--apply` fails (including the stop, the mask, enabling units or
`--restart`), it rolls back: replaced files are restored from the backup, files it
created are removed, units it newly enabled are disabled, the legacy unit's file,
mask, enabled and active state are restored (a mask that existed before, e.g. from
an earlier install, is left in place), and with `--restart` the old configuration
is restarted. Each step that fails is recorded, the rest still run, and the end
state is then checked (files equal their backups, created files gone, unit
enable/mask/active states, services active after a restart). The outcome is one of:

- `ROLLBACK VERIFIED` (exit 1): every installer change was undone and checked.
- `ROLLBACK INCOMPLETE` (exit 3): the previous system is **not** restored; the
  exact failed or unverified operations are listed. Fix them by hand from the
  backup before restarting anything.

Either way the installer prints `CODE:` with the current `HEAD` and the recorded
rollback commit, and `CODE MISMATCH` when they differ: the installer-managed files
are back, but the application code is still the new one. Restoring the code is a
separate, explicitly authorized step (Rollback, below). The backup is kept. It also warns, without changing
anything, if `hotspot.env` or `backend.env` is not root-owned `600` (the boot
script refuses to source a `hotspot.env` that is not root-owned or is
group/world-writable).
`/etc/project-pi/hotspot.env` changes only with `--configure-hotspot` (needs
`PROJECT_PI_HOTSPOT_PASSWORD`), which also lets the boot script manage the hotspot.

Expect a brief alert outage during the restart. On its first start the new KWS
merges `/tmp/project_pi_alerts.jsonl` into the durable outbox by `event_id`, then
renames it `/tmp/project_pi_alerts.jsonl.migrated` (never deleted). Check:

```bash
systemctl is-active kws-alert.service kws-alert-vosk.service   # expect: active, inactive
systemctl is-enabled kws-alert-vosk.service                    # expect: masked
systemctl cat thermal-backend.service | grep -E 'LGPIO_CHIP|THERMAL_'   # drop-in values win
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

## 5. API token on the phones: only in required mode

Open mode (default): nothing to enter; leave **Settings → Pi API token
(optional)** empty in both apps.

In required mode (see "Requiring authentication"):

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
curl -s http://127.0.0.1:8765/api/status | python3 -m json.tool | grep -E 'api_auth_mode|thermal_refresh|mlx90640_variant|alert_outbox' -A1
journalctl -u thermal-backend -n 80 --no-pager | grep -E 'api_auth_mode|PROJECT_PI_API_AUTH=open|THERMAL_REFRESH_HZ'
sudo -l -U thesis                        # only /usr/local/sbin/project-pi-refresh, systemctl restart x3, power
journalctl -u kws-alert -n 50 --no-pager | grep -E 'Listening|disabled|died|alert outbox'
journalctl -u thermal-backend -n 50 --no-pager | grep -E 'ERROR|Health monitor'
journalctl -u project-pi-boot -b --no-pager | grep 'Network unchanged'   # after the next reboot
sha256sum -c "$B/models.sha256"          # models unchanged
python3 tools/agent_integrations/read_only_pi_preflight.py --execute-local --approved-read-only \
  --probe capture_owner --probe kws_main_pid   # expect MIC_OWNER_KWS_ONLY while KWS runs
```

Then on a phone: banner gone, thermal/audio live, a spoken test keyword produces
an alert, and the panic button reports "EMERGENCY ALERT SENT".

## Open mode: what is exposed

With `PROJECT_PI_API_AUTH=open`, anyone who can reach the Pi on the network can call
every route without credentials: read status, thermal frames, audio levels and
alert history; post or delete alerts; change noise suppression; set LEDs;
upload training data; deploy a keyword model (which restarts KWS); `refresh`
(service restart, and git pull only if the deploy flag exists); `reboot`;
`shutdown`. Nothing about this is secure, and the old app's built-in token is
not security: it relies entirely on the network being isolated (the defense hotspot
with a private password). The caregiver protocol-v2 alert socket keeps its own
per-phone authentication in both modes.

## Requiring authentication, rotation and revocation

1. Generate a token: `python3 -c 'import secrets; print(secrets.token_hex(32))'`.
2. In `/etc/project-pi/backend.env` (`sudo nano`, keep `0600`), set
   `PROJECT_PI_API_AUTH=required` and `PROJECT_PI_API_TOKEN=<token>`.
3. `sudo systemctl restart thermal-backend.service kws-alert.service`.
4. Enter the token on every phone (step 5). Old APKs stop working.

In required mode a later typo, deleted token or unknown mode stops the backend
instead of silently reopening every route. Rotate by replacing the token and
repeating steps 3–4; go back to open mode by setting `PROJECT_PI_API_AUTH=open`.
Revoke one caregiver phone's alert delivery by deleting its entry from
`caregivers.json` and restarting `thermal-backend`.

## App-triggered git deploy (optional, off by default)

`/api/refresh` with `git_pull` returns 409 unless `/etc/project-pi/allow-app-git-deploy`
exists, because a pull without the installer leaves new code running on old units,
sudoers and helpers. Create it (`sudo touch`, root-owned) only as part of an
authorized upgrade whose changes need no installer run, and remove it afterwards.
The pull also needs the tracking `main` from step 2.

## Rollback

Restores the previous code and system configuration; preserves SQLite data,
recordings, models and datasets (none are modified by the upgrade). This is a
separate, explicitly authorized operation; the installer never performs it. After
an `--apply` failure, first make sure it reported `ROLLBACK VERIFIED` (or fix the
listed items), then decide whether to roll back the code as well.

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

- The rollback checkout is detached on purpose, so a pull cannot move the Pi back
  onto the new code.
- The installer's own backups of every replaced file are in
  `/var/lib/project-pi/install-backups/<timestamp>/` (paths mirror `/`).
- `kws-alert-vosk.service` stays masked; it was disabled and inactive before.
  `sudo systemctl unmask kws-alert-vosk.service` only if the old setup needs it.
- `thermal-backend.service.d/10-local.conf` holds the same values the old unit had
  (plus a rate and variant the old code ignores), so it can stay.
- Queued events carry a `retention_tier` field that the old backend ignores.
- Only the outbox (`alerts.jsonl`) is carried back to the old path.
  `alerts.rejected.jsonl` and `alerts.losses.json` stay untouched in
  `/var/lib/project-pi/backend/`; the old KWS does not read them. Never append them
  to the old outbox: review and archive them as in "Reviewing rejected and lost
  alerts" before deciding to re-send anything.
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

## Kept from PR #9 but requiring physical validation

None of these is claimed as an improvement until tested on the Pi: single
microphone owner; durable outbox and its migration; worker-thread alert posting;
engine fail-fast; MLX90640 I2C recovery and re-init backoff; health-monitor
`system_fault` alerts; the 5 s heartbeat (old-APK churn risk); offline startup;
installer rollback on a real systemd.

## Remaining physical tests (not covered by software tests)

1. `install_headless.sh` dry run and `--apply` on the Pi, including `visudo`
   validation, the drift report against both lock files and the seeded drop-in.
2. ReSpeaker single-owner capture: KWS restarts (x5) while the app streams
   `/ws/audio`; KWS must come back every time and the preflight must report
   `MIC_OWNER_KWS_ONLY`.
3. MLX90640 at the drop-in rate (4 Hz) on the fitted variant; unplug for 30 s and
   re-plug; the backend must recover without restart and its open file count must
   stay flat.
4. Health monitor: stop `kws-alert` for over 1 minute; exactly one
   `system_fault` reaches the phone, with no siren.
5. Android: screen off for 10 minutes, then a spoken keyword alarms within about
   5 s; app swiped from recents still alarms; battery drain over 8 hours recorded.
6. Wi-Fi drop of 20 s: the alert link must recover within about 10 s; Pi power
   cut with the app open: the app must reconnect without a tap. Old APK on the
   new Pi with the 5 s heartbeat: no reconnect churn.
7. Panic button during a Wi-Fi blip of under 30 s: one alert recorded, not
   duplicates.
8. Reboot with `hotspot.env` lacking `PROJECT_PI_FORCE_HOTSPOT`: the Pi stays on
   its current Wi-Fi profile.
9. Offline boot: power on with Wi-Fi off (or the access point down); thermal and
   KWS must be active and a spoken keyword must reach the backend
   (`journalctl -u thermal-backend`) within the normal start time, with no wait
   for the network.
10. `--apply` failure on the Pi (for example a deliberately invalid unit): the
    rollback must restore the previous units and services.
