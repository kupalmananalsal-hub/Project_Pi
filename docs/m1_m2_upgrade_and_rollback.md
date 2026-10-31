# Milestone 1–2 upgrade and rollback (Raspberry Pi + Android)

**Status: prepared, not executed.** Running any part of this on the Pi is a
Level 4 deployment under the [shared policy](agent_integrations/policy.md) and
needs explicit owner authorization. Software tests are not physical certification.

Milestone 1–2 is a set of **reviewed product changes**, not tooling: it adds
API authentication (`required` for any shared network; a missing or incomplete
configuration fails closed), and changes sudoers, systemd units,
root-run scripts, microphone ownership, the KWS alert outbox and Android
background behavior. It does **not** change the alert decision policy, models,
detection thresholds, keyword lists, VAD settings, the SQLite schema, datasets or
recordings, and it never installs or upgrades packages.

Baseline it must reproduce (read-only audit of the deployed Pi, 2026-10-31): commit
`1a5c309`; Python 3.11.2 venvs whose packages are recorded in
`raspberry_pi/requirements/kws-env.lock.txt` and `thermal-env-sys.lock.txt`;
`LGPIO_CHIP=11` (deployed value; the header-to-controller mapping is not physically
verified); MLX90640 at 4 Hz (variant not verified); `kws-alert.service` identical to
the repo; four untracked production files (`raspberry_pi/config/protected_assets.txt`).

**Thermal model and threshold: deployed, not validated.** The metadata of
`thermal_human_detector.tflite` says `optimal_threshold` 0.05, chosen on validation
data without negative examples, so its false-positive rate is unmeasured. That is
the metadata value, not necessarily what runs: the installed unit may point at
`thermal_human_shape.tflite` with `THERMAL_HUMAN_MODEL_THRESHOLD` (the repo's
`1a5c309` unit used 0.65). The live model and threshold are whatever the installed
unit sets; record them in step 0. The upgrade preserves them unchanged (copied into
the local drop-in) and claims nothing about their accuracy.

## What changes on the Pi

| Area | Before | After |
|---|---|---|
| API auth | Token checked on 5 endpoints; public default `project-pi-local-token` (published in the source, so no security) | `required`: a bearer token (16+ characters) on every `/api` and `/ws` route except `/ws/alerts?protocol=2` (per-phone caregiver secret); new APK only. `open`: **no authentication**, only with `PROJECT_PI_OPEN_MODE_ACK=isolated-network-verified`. Anything else (no `backend.env`, no or unknown mode, missing/short/legacy token, open without the acknowledgment) runs **locked**: every `/api` and `/ws` request is refused, including protocol v2, while detection keeps running. The legacy token is never authentication. |
| Auth configuration | Hard-coded default | `/etc/project-pi/backend.env` (root, `0600`), created once by the installer with the mode chosen by `--api-auth` (a generated token for `required`), never overwritten |
| Root-run scripts | `pi_refresh.sh`, `headless_boot.sh`, `log_cleanup.sh` run from the thesis-writable repo | Root-owned copies `/usr/local/sbin/project-pi-{refresh,boot,log-cleanup}`, installed only by `install_headless.sh --apply` |
| sudoers | thesis may run repo scripts as root | Exact commands only (see `raspberry_pi/sudoers/project-pi-thesis`); no repo paths |
| Unit files | Re-copied from the repo by the boot service on every boot | Installed only by `install_headless.sh --apply` |
| Installer | Writes immediately, upgrades packages, runs nmcli, restarts services | Dry run by default (NEW / IDENTICAL / CHANGED with diffs, package drift report); `--apply` refuses unless the pre-upgrade backup gate passes (it re-runs the read-only inventory itself), backs up every replaced file first and rolls back every file and unit change if any step fails; restarts only with `--restart`; never installs packages; never touches NetworkManager |
| Startup | Detection units waited for `network-online.target` and the boot script (up to 120 s network wait plus `apt-get update`) | `thermal-backend` and `kws-alert` depend only on `sound.target` (KWS also on the backend): they start without Wi-Fi or internet. The boot script waits for the network only when managing the hotspot and no longer runs `apt-get`; `project-pi-apt-update.timer` does that 15 min after boot, off the critical path |
| `/api/refresh` | Root script does `git pull` and reinstalls units | `git_pull` refused (409) unless the root-owned `/etc/project-pi/allow-app-git-deploy` exists; restart without pull always works |
| Wi-Fi | Boot script could create/modify/activate the hotspot profile | Changed only when `hotspot.env` sets `PROJECT_PI_FORCE_HOTSPOT=1`; otherwise the boot logs the current SSID/IPv4 and changes nothing |
| Microphone | Backend and KWS could both open the ReSpeaker | KWS is the single capture owner (`Conflicts=kws-alert-vosk.service`, legacy unit masked); backend reads KWS's published audio status |
| KWS outbox | `/tmp/project_pi_alerts.jsonl` (tmpfs), truncated by log cleanup | `/var/lib/project-pi/backend/alerts.jsonl`, fsynced; the legacy file is merged in on first start and renamed `*.migrated`; bounded by retention tier (below) |
| Thermal | Hard-coded 4 Hz; installed unit differs from the repo | Generic unit: detector model + metadata, no threshold override, no rate. Rate, variant and `LGPIO_CHIP` live in the local drop-in `thermal-backend.service.d/10-local.conf`, created once from the installed unit |
| Caregiver credentials | `PROJECT_PI_CAREGIVER_CREDENTIALS` unset | Set in `backend.env` to `/var/lib/project-pi/backend/caregivers.json` |
| Backend-rejected alerts | HTTP 4xx (except 401/408/429) silently dropped as "delivered" | Moved, fsynced, to `alerts.rejected.jsonl` (kept for review, never retried, never blocking later alerts; possibly-critical records dropped only at the hard limits, and every such loss counted in the durable `alerts.losses.json`); a possibly-critical rejection or any recorded loss raises a health fault until reviewed |
| Health | Silent | One `system_fault` event (never critical/siren) per outage of KWS, thermal, a possibly-critical outbox eviction, a possibly-critical backend rejection, KWS alerts refused with 401, or a locked API |

Unchanged and untouched by upgrade and rollback: `raspberry_pi/backend/alerts.db`
(no schema change), `dataset/`, `~/thesis_dataset`, `~/voice_samples`,
`~/vosk-models`, `~/snowboy`, model files, the noise suppression config,
`/etc/project-pi/*.env` other than creating `backend.env` if absent. `.gitignore`
now lists `raspberry_pi/backend/alerts.db*` so the database is never staged; that is
not a backup (step 0 makes and verifies one).

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

Every possibly-critical event that is lost (a `possible_critical` outbox eviction at
the soft limit, any `possible_critical` or `certain_critical` eviction at the hard
limit, or a possibly-critical quarantine eviction) is counted, with a summary of the
event (event ID, reason, retention tier), in
`/var/lib/project-pi/backend/alerts.losses.json`, written before the event leaves
the outbox or quarantine; if that write fails the event is kept (over the limit,
with an error) rather than lost unrecorded. The eviction order is unchanged. Each
write is a fsynced temporary file, an atomic rename, then a directory fsync. The
counts survive KWS restarts and keep the health fault raised until an
operator acknowledges them; the file keeps the last 100 summaries but its counts
are never trimmed. Power-cut survival relies on ext4 honouring these fsyncs and has
only been tested on Windows, not by cutting power on the Pi. An unreadable ledger
is moved aside unmodified (`alerts.losses.json.unreadable-<ns>`); as long as such a
file is in the state directory the fault stays raised, across any number of
restarts.

### Reviewing rejected and lost alerts (operator only)

Nothing is ever re-sent automatically. As `thesis`:

1. Read `alerts.rejected.jsonl`, `alerts.losses.json` and any
   `alerts.losses.json.unreadable-*` and record what happened.
2. Acknowledge by **moving** (not deleting) the reviewed files out of
   `/var/lib/project-pi/backend/` into a reviewed folder, e.g.
   `mkdir -p /var/lib/project-pi/backend/reviewed-$(date -u +%Y%m%dT%H%M%SZ)` and
   `mv` them there; they are the only trace of these events. No restart is needed:
   the running KWS notices the change within 5 seconds and drops the cleared counts
   from its next status, and the backend's next health check clears the fault.
   KWS's own writes never count as an acknowledgment.
3. If a new rejection or loss arrives while you move the file, KWS rewrites the
   file with everything it still holds, so the fault comes back: review again.
4. Re-sending a rejected event is a per-event decision, made only after fixing
   the cause: stop `kws-alert`, append the chosen lines to `alerts.jsonl`, start
   `kws-alert`. Never bulk-copy the file back.

## Compatibility rules that set the order

- **New APK + old Pi: works.** With no token entered, the app sends no
  `Authorization` header, which the old backend does not require.
- **Old APK + new Pi in required mode (shared Wi-Fi): does not work** (401
  everywhere, including the old alert socket). Every phone gets the new APK first.
- **Old APK + new Pi in acknowledged open mode: expected to work**, and only on a
  verified isolated hotspot. The old app's request shapes (no header, the old public
  token, any header) pass; this is tested at the HTTP/WebSocket level, not with an
  installed old APK. Open mode is compatibility, not security.
- **Any APK + locked Pi: nothing connects** until `backend.env` is fixed.
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
git status --short                      # read it: local edits block; the four ?? files are expected
git rev-parse HEAD                      # record as ROLLBACK_COMMIT
ls -la /tmp/project_pi_alerts.jsonl     # undelivered legacy alerts, if any (merged automatically)
ls /etc/sudoers.d/                      # expect project-pi-thesis (and optionally project-pi-power, power commands only)
systemctl show -p Environment thermal-backend.service | tr ' ' '\n' | grep -E 'CAREGIVER|ALERT_DB_PATH|LGPIO|THERMAL' || true
systemctl cat thermal-backend.service kws-alert.service | grep -n '^# /' # lists drop-in overrides, if any
systemctl show -p Environment thermal-backend.service | tr ' ' '\n' | grep THERMAL_HUMAN_MODEL  # live model + threshold
ls -la raspberry_pi/backend/alerts.db* dataset/thermal/models/thermal_human_shape*  # confirm the manifest paths
```


If `PROJECT_PI_CAREGIVER_CREDENTIALS` was already set (drop-in), note its path:
`EnvironmentFile=` values take precedence over `Environment=`, so after the
upgrade `backend.env` must point at the same file (step 4).

### 0a. Get the reviewed preflight tools without changing the checkout

The backup and inventory scripts are new in the reviewed commit and do not exist in
the deployed `1a5c309` checkout. Extract them from git's object store into a
separate directory; the working tree, branch and running services do not change
(`git fetch` only adds objects under `.git`). This is itself part of the separately
authorized upgrade, not a read-only step.

```bash
cd ~/Project_Pi
git fetch origin
git merge-base --is-ancestor <REVIEWED_COMMIT> origin/main || echo "STOP: not on origin/main"
T=~/project-pi-preflight/<REVIEWED_COMMIT>
mkdir -p "$T"
TOOLS="raspberry_pi/scripts/preupgrade_backup.sh raspberry_pi/scripts/preupgrade_inventory.sh raspberry_pi/config/protected_assets.txt"
git archive <REVIEWED_COMMIT> $TOOLS | tar -x -C "$T"
for f in $TOOLS; do                     # each extracted file is byte-identical to the reviewed blob
  [ "$(git rev-parse "<REVIEWED_COMMIT>:$f")" = "$(git hash-object "$T/$f")" ] || echo "STOP: $f differs"
done
```

### 0b. Confirm the protected-file paths (read-only)

`protected_assets.txt` marks the two thermal model paths `? ` (provisional): the
audit gave only file names. Both scripts refuse a manifest with `? ` entries, so
this step cannot be skipped. Check each path with the `ls -la` above, then make the
confirmed copy (the reviewed file stays unchanged):

```bash
sed 's/^? //' "$T/raspberry_pi/config/protected_assets.txt" > "$T/protected_assets.confirmed.txt"
grep -v '^#' "$T/protected_assets.confirmed.txt" | while read -r p; do ls -la "$p" || echo "STOP: $p"; done
```

If a file is elsewhere, put its real path in the confirmed copy; never move the file
to fit the manifest.

### 0c. Back up, then run the gate

Back up the protected production files (authorized; it writes only into a new `$B`),
then run the read-only gate against the commit you will deploy:

```bash
B=~/project-pi-backups/pre-m1m2-$(date +%Y%m%d-%H%M)
bash "$T/raspberry_pi/scripts/preupgrade_backup.sh" --repo="$HOME/Project_Pi" \
  --manifest="$T/protected_assets.confirmed.txt" --backup-dir="$B"   # also writes $B/ROLLBACK_COMMIT
bash "$T/raspberry_pi/scripts/preupgrade_inventory.sh" --repo="$HOME/Project_Pi" \
  --target=<REVIEWED_COMMIT> --backup-dir="$B"
```

The backup opens the live database read-only (SQLite URI `mode=ro`: a missing file is
never created, the database file is never written), takes a consistent snapshot with
SQLite's online backup API and checks it with `PRAGMA integrity_check`; the other
files are copied. The manifest used is copied into `$B`, and `$B/SHA256SUMS` covers
every copy and that manifest. The live database is never hashed (it keeps changing).
If the database was closed, SQLite creates empty `-wal`/`-shm` files next to it; the
backup reports them and leaves them (harmless).

The inventory writes nothing and must print `PASS`: backup intact, manifest
confirmed, tracked files unedited, each protected file present and backed up, and no
local untracked or **ignored** file (models, datasets, recordings included) at a
path `<REVIEWED_COMMIT>` tracks, or inside one it tracks as a file: a plain
`git switch` overwrites or deletes such files, no force needed. Other local files
are listed as `LOCAL`/`WARN` and do not block. On `BLOCKED`, stop; never use
`git clean`, `git reset --hard` or `git checkout -f`.

Also back up the system configuration:

```bash
sha256sum dataset/audio/openwakeword_models/* dataset/thermal/models/* > "$B/models.sha256" 2>/dev/null || true
sudo cp -a /etc/sudoers.d /etc/project-pi "$B/" 2>/dev/null || true
sudo cp -a /etc/systemd/system/thermal-backend.service /etc/systemd/system/kws-alert.service \
  /etc/systemd/system/apk-server.service /etc/systemd/system/project-pi-boot.service \
  /etc/systemd/system/project-pi-log-cleanup.service /etc/systemd/system/project-pi-apt-update.service \
  /etc/systemd/system/project-pi-apt-update.timer /etc/systemd/system/project-pi-log-cleanup.timer \
  /etc/systemd/system/project-pi.target "$B/" 2>/dev/null || true
sudo cp -a /etc/systemd/system/thermal-backend.service.d /etc/systemd/system/kws-alert.service.d "$B/" 2>/dev/null || true
```

Run both scripts as `thesis`, never as root: root would leave root-owned
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
   Leave the API token field empty for now (the old Pi needs none).

## 2. Pi code (as `thesis`)

Deploy only after the PR is merged: `<REVIEWED_COMMIT>` must be on `origin/main`
(the repo squash-merges, so a PR-branch commit would leave `main` diverged and every
later pull would fail). The Pi stays on a `main` branch that tracks `origin/main`.

```bash
cd ~/Project_Pi
bash "$T/raspberry_pi/scripts/preupgrade_inventory.sh" --repo="$HOME/Project_Pi" \
  --target=<REVIEWED_COMMIT> --backup-dir="$B"                      # PASS again, right before
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
the model, metadata and threshold settings recorded in step 0, and
`THERMAL_REFRESH_HZ=4`. Then apply, on the Pi console:

```bash
sudo bash raspberry_pi/scripts/install_headless.sh --apply --api-auth=required \
  --backup-dir="$B" --rollback-commit="$(cat "$B/ROLLBACK_COMMIT")"   # installs, restarts nothing
sudo systemctl restart thermal-backend.service kws-alert.service      # backend, then KWS, together
```

`--backup-dir` is required with `--apply`: the installer runs the inventory itself
(as `thesis`, against the now checked-out `HEAD`) and refuses, with nothing changed,
unless it passes and the backup was made at `--rollback-commit`. There is no PASS
file to forge, and no option to skip it.

`--api-auth` is required with `--apply`. `required` (the choice on any shared Wi-Fi)
creates `backend.env` with a random 64-hex token that is never printed: every diff
shows `PROJECT_PI_API_TOKEN=<redacted>`. `open` also needs
`--i-verified-network-isolation` and is only for a verified isolated hotspot. If
`backend.env` already exists it is never edited, and `--apply` refuses unless it
already gives the requested mode (an `open` line without the acknowledgment, a
short or legacy token, or no mode all count as locked).

The restart switches the Pi from today's state straight to `required`; it is never
in open mode on the shared network. From then until each phone has the token
(step 5) phones cannot connect; KWS keeps any alerts in its durable outbox and
retries them, with the same `event_id`, once delivery is authorized (see "Delivery
guarantees").

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
state is then checked (files equal their backups in contents, owner, group and
mode, created files gone, unit
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

## 5. API token on the phones (required mode)

On the Pi console only (never over chat, email, a URL, a screenshot or git):

```bash
sudo sed -n 's/^PROJECT_PI_API_TOKEN=//p' /etc/project-pi/backend.env
```

Type it into **Settings → Pi API token (optional)** in the caregiver app and in
the resident app (stored in Android secure storage), then clear the terminal.
Without it the phones show "The Pi refused the request (401)…" and the red
"Alerts are NOT being received" banner. Open mode: leave the field empty.

## 6. Verification (Level 4, with authorization)

```bash
systemctl is-active thermal-backend.service kws-alert.service
# token read from the root-only file into a header file, never onto the command line
sudo sed -n 's/^PROJECT_PI_API_TOKEN=/Authorization: Bearer /p' /etc/project-pi/backend.env \
  | curl -s -H @- http://127.0.0.1:8765/api/status | python3 -m json.tool \
  | grep -E 'api_auth_mode|thermal_refresh|mlx90640_variant|alert_outbox' -A1   # expect required
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/api/status            # expect 401
sudo cat /var/lib/project-pi/backend/auth_fault 2>/dev/null || echo "no auth fault"
journalctl -u thermal-backend -n 80 --no-pager | grep -E 'api_auth_mode|API LOCKED|PROJECT_PI_API_AUTH=open|THERMAL_REFRESH_HZ'
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

## Locked mode (missing or invalid auth configuration)

If `backend.env` is missing, has no or an unknown `PROJECT_PI_API_AUTH`, `required`
with a missing, short or legacy token, or `open` without
`PROJECT_PI_OPEN_MODE_ACK=isolated-network-verified`, the backend starts **locked**:
thermal capture and keyword detection keep running, but every `/api` and `/ws`
request is refused (including the caregiver protocol-v2 socket and KWS's own alert
posts). It never falls back to open. Nothing on the network can read the status
while locked, so the fault is visible only on the Pi:

- `journalctl -u thermal-backend`: `ERROR: API LOCKED: <reason>` at start and every
  60 s; `api_auth_mode=locked`.
- `/var/lib/project-pi/backend/auth_fault` holds the reason (removed when fixed).
- `journalctl -u kws-alert`: `ERROR: backend refused alerts with HTTP 401 …` every
  60 s, with the number of alerts held in the outbox; health faults "API
  authentication locked" and "alert delivery unauthorized" are stored locally.

Alerts are held, not delivered: KWS keeps them in its outbox with their `event_id`
and retries them after `backend.env` is fixed and `thermal-backend` then
`kws-alert` are restarted (see "Delivery guarantees").

## Delivery guarantees (what is tested, and what is not)

- KWS → backend is **at-least-once**: an alert leaves the outbox only after the
  backend answers 2xx (or a non-retryable 4xx moves it to quarantine). A lost
  acknowledgement, a crash after the backend stored it, or a restart can send it
  again. The backend looks the `event_id` up in `alerts.db` (unique index) before
  any side effect, so a repeat is stored and broadcast once while that row exists
  (tested, including after a 401 period); a different payload under the same
  `event_id` is refused with 409. That is deduplication, not exactly-once transport.
- The outbox is durable only while its writes succeed. A failed write (for example a
  full disk) is logged as `NOT durable` and raises the health fault "alert storage
  failing"; affected alerts are then held in memory only and are lost if KWS stops.
- Evictions at the limits are recorded in the loss ledger first; an eviction whose
  record cannot be written does not happen (the outbox exceeds its limit instead).
- Phone presentation is separate (see `docs/phase3_delivery_design.md`): there is
  no exactly-once physical alert guarantee.

## Network and transport security

Bearer-token authentication refuses clients without the token; it does **not**
encrypt anything. The backend and the apps use plain HTTP and WebSocket: anyone who
can observe the Wi-Fi traffic (an open network, or any member of a shared WPA2-PSK
network who captures the handshake) can read the token, alerts, thermal frames and
audio levels, and reuse the token. Authentication therefore does not make a shared
network safe.

Deployment requires one of:

- **A trusted, isolated network**: the Pi's own hotspot (or a dedicated access
  point) with a private WPA2/WPA3 password, joined only by the project phones; or
- **Encrypted transport** (TLS in front of the backend, or a VPN). PR #9 does not
  provide this; it would be separate, reviewed work.

Until one of these is verified, deploying on the existing shared Wi-Fi stays
blocked, in `required` and `open` mode alike. The APK server (port 8080, plain HTTP,
no authentication) falls under the same rule.

## Open mode: what is exposed

With `PROJECT_PI_API_AUTH=open` and the isolation acknowledgment, anyone who can reach the Pi on the network can call
every route without credentials: read status, thermal frames, audio levels and
alert history; post or delete alerts; change noise suppression; set LEDs;
upload training data; deploy a keyword model (which restarts KWS); `refresh`
(service restart, and git pull only if the deploy flag exists); `reboot`;
`shutdown`. Nothing about this is secure, and the old app's built-in token is
not security: it relies entirely on the network being isolated (the defense hotspot
with a private password). The caregiver protocol-v2 alert socket keeps its own
per-phone authentication in both modes.

## Token rotation, revocation and the APK server

Rotate (on the Pi console): generate a new token without echoing it,
`sudo sed -i "s/^PROJECT_PI_API_TOKEN=.*/PROJECT_PI_API_TOKEN=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')/" /etc/project-pi/backend.env`,
keep the file root `0600`, restart `thermal-backend` then `kws-alert`, and enter
the new token on every phone (step 5). A typo or deleted token later makes the
backend run locked, never open. Switching to open mode needs both
`PROJECT_PI_API_AUTH=open` and `PROJECT_PI_OPEN_MODE_ACK=isolated-network-verified`
and is only for a verified isolated hotspot.

The API token protects only the FastAPI backend (port 8765). `apk-server.service`
serves `build/app/outputs/flutter-apk/` over plain HTTP on port 8080 to anyone on
the network, without authentication. On shared Wi-Fi, stop it once every phone has
the new APK (`sudo systemctl disable --now apk-server.service`) and start it only
for a supervised phone update.
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
  to the old outbox: review and acknowledge them as in "Reviewing rejected and lost
  alerts" before deciding to re-send anything.
- Leave `/etc/project-pi/backend.env`, `/var/lib/project-pi/backend/` and the
  `/usr/local/sbin/project-pi-*` helpers in place; the old units do not use them.
  Remove them only once rollback is confirmed final.
- Phones need no rollback: the new APK works with the old backend. Clear the
  token field to avoid sending it to the old backend.
- Only restore `$B/raspberry_pi/backend/alerts.db` if the live database is damaged:
  stop `thermal-backend`, copy it back as `thesis`, start the service. Restoring it
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
