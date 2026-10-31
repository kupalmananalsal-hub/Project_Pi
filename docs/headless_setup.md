# Headless Raspberry Pi 5 Setup

Power-on only operation: the Pi starts all services on its existing Wi-Fi profile and accepts mobile-app commands (including **Refresh KWS** without SSH). It joins hotspot **Teddy** automatically only when the hotspot was configured explicitly (`--configure-hotspot`).

## What Runs Automatically

| Component | Purpose |
|:---|:---|
| `project-pi-boot.service` | Logs the current Wi-Fi (network wait and hotspot connect only with `PROJECT_PI_FORCE_HOTSPOT=1`), log cleanup (runs the root-owned `/usr/local/sbin/project-pi-boot`; unit files are only installed by `install_headless.sh --apply`). Detection services do not wait for it |
| `thermal-backend.service` | FastAPI on port **8765** (`~/thermal-env-sys`) |
| `kws-alert.service` | Triple-engine KWS (`~/kws-env`) |
| `apk-server.service` | APK HTTP server on port **8080** |
| `project-pi-apt-update.timer` | Daily `apt-get update` (package index only; first run 15 min after boot, never before detection starts) |
| `project-pi-log-cleanup.timer` | Daily journal vacuum + temp log trim |

## One-Time Install (on the Pi)

SSH in once, clone or pull the repo, then run:

```bash
cd ~/Project_Pi
sudo bash raspberry_pi/scripts/install_headless.sh            # dry run: review the report
sudo bash raspberry_pi/scripts/install_headless.sh --apply --restart \
  --rollback-commit="$(git rev-parse HEAD)"   # the code to restore if --apply fails
```

The default is a dry run that writes nothing: it reports package drift against
`raspberry_pi/requirements/*.lock.txt`, and every target file as NEW / IDENTICAL /
CHANGED with a diff. `--apply` backs up each replaced file to
`/var/lib/project-pi/install-backups/<UTC timestamp>/` first and refuses on package
drift unless `--accept-env-drift`; services restart only with `--restart`. If any
step fails it rolls back every file and unit change and returns the checkout to
`--rollback-commit`. The installer never installs packages and never runs `nmcli`.
When updating code, pass the commit that ran before the update instead (see
[m1_m2_upgrade_and_rollback.md](m1_m2_upgrade_and_rollback.md), steps 0–3).

To have the boot script join the hotspot (a fresh Pi with no Wi-Fi profile), add
`--configure-hotspot` with the password; no password is shipped:

```bash
sudo PROJECT_PI_HOTSPOT_SSID=Teddy PROJECT_PI_HOTSPOT_PASSWORD='<hotspot password>' \
  bash raspberry_pi/scripts/install_headless.sh --apply --configure-hotspot \
  --rollback-commit="$(git rev-parse HEAD)"
```

That writes `/etc/project-pi/hotspot.env` (mode `600`, not in git) with
`PROJECT_PI_FORCE_HOTSPOT=1`. Without that flag in the file, the boot script logs
the current SSID/IPv4 and never creates, modifies or activates a profile.

The installer also:

- creates `/etc/project-pi/backend.env` (root, mode `600`) once, in
  `PROJECT_PI_API_AUTH=open` mode: **no authentication**; the app needs no token,
  and every `/api`/`/ws` route, including reboot, shutdown, refresh, model deploy
  and alerts, is open to anyone on the network. Use it only on an isolated hotspot.
  To require a token, see "Requiring authentication" in
  [m1_m2_upgrade_and_rollback.md](m1_m2_upgrade_and_rollback.md) and enter the token
  in each app under **Settings → Pi API token (optional)**.
- creates `/etc/systemd/system/thermal-backend.service.d/10-local.conf` once, from
  the installed unit, for device-specific settings (`LGPIO_CHIP`, model paths,
  `THERMAL_REFRESH_HZ`, `MLX90640_VARIANT`); it never edits an existing drop-in.
- copies the root-run scripts to `/usr/local/sbin/project-pi-{refresh,boot,log-cleanup}`
  and installs `/etc/sudoers.d/project-pi-thesis`, which allows only those exact
  commands, three `systemctl restart`s and the power commands.
- masks the legacy `kws-alert-vosk.service` (a second ReSpeaker owner) and only
  reports `thesis-camera.service`.

Upgrading an existing Pi from before this change: follow
[m1_m2_upgrade_and_rollback.md](m1_m2_upgrade_and_rollback.md) (phones first).

## After Install — Normal Use

1. Power on the Pi (no monitor/keyboard).
2. Wait for the services (they start without waiting for Wi-Fi; the phone needs the Pi on its network).
3. Open the Flutter app (Controls tab shows connection; Monitor shows thermal/audio).
4. Use **Refresh KWS Service** on the Controls tab instead of manual `systemctl`/`cp` commands.

## Service Order

```text
boot → thermal-backend → kws-alert     (sound.target only; no network wait)
     → project-pi-boot (oneshot, after network-online; independent)
     → apk-server
     → project-pi-apt-update.timer (15 min after boot)
```

All application services use `Restart=always` and restart limits for crash recovery.

## Manual Commands (testing)

```bash
# Status
systemctl status project-pi-boot.service thermal-backend.service kws-alert.service apk-server.service --no-pager

# Logs
sudo journalctl -u kws-alert.service -f
sudo journalctl -u thermal-backend.service -f
sudo journalctl -u project-pi-boot.service -n 50 --no-pager

# Hotspot
nmcli con show --active
iwgetid -r
hostname -I

# Backend health (the header is ignored in open mode and required in required mode;
# never paste a token into a URL)
sudo bash -c 'source /etc/project-pi/backend.env; curl -s -H "Authorization: Bearer $PROJECT_PI_API_TOKEN" http://127.0.0.1:8765/api/status' | python3 -m json.tool

# Refresh API (same as mobile app)
sudo bash -c 'source /etc/project-pi/backend.env; curl -s -X POST http://127.0.0.1:8765/api/refresh \
  -H "Authorization: Bearer $PROJECT_PI_API_TOKEN" -H "Content-Type: application/json" \
  -d "{\"git_pull\": false, \"restart_backend\": false}"'

# Re-run full boot script (root-owned copy)
sudo /usr/local/sbin/project-pi-boot
```

## Mobile App Refresh Endpoint

`POST /api/refresh`

```json
{
  "git_pull": false,
  "restart_backend": false
}
```

Response:

```json
{
  "ok": true,
  "git_pull": false,
  "restart_backend": false,
  "returncode": 0,
  "stdout": "...",
  "stderr": ""
}
```

`git_pull` is refused with HTTP 409 unless the root-owned flag file
`/etc/project-pi/allow-app-git-deploy` exists (absent by default), so the app
cannot pull code that needs the installer. With the flag, the backend runs
`git pull --ff-only` as `thesis`; the Pi checkout must be on a branch tracking
`origin/main` (a detached checkout returns `ok: false` and restarts nothing; see
`docs/m1_m2_upgrade_and_rollback.md`, step 2). Either way it then runs the
root-owned `/usr/local/sbin/project-pi-refresh` via passwordless sudo, which only
restarts `kws-alert` (and `thermal-backend` with `restart_backend`). Pulled changes to
unit files, sudoers or root scripts take effect only after `install_headless.sh` is re-run.

## APK Over-the-Air

```bash
cd ~/Project_Pi
flutter build apk --debug
cp raspberry_pi/apk_server/index.html build/app/outputs/flutter-apk/index.html
```

Phone browser: `http://10.129.205.32:8080/`

If the hotspot gives the Pi a different address, check `hostname -I` and use
`http://<PI_IP>:8080/` instead.

## Updating the Pi After Git Push

On the Pi (once):

Follow [m1_m2_upgrade_and_rollback.md](m1_m2_upgrade_and_rollback.md) steps 0–3:
fast-forward `main` to the reviewed commit, run the installer dry run, then
`--apply`.

The app's **Refresh KWS Service** restarts services; it pulls only when the deploy
flag exists, and it never reinstalls units, sudoers or root scripts.

## Troubleshooting

| Symptom | Check |
|:---|:---|
| `thermal-backend` stops right after start | Do not run `daemon-reload` while it is running. Kill stuck boot: `pgrep -af headless_boot`. Then `sudo systemctl start thermal-backend --no-block` |
| `systemctl start` hangs | `sudo systemctl stop project-pi-boot; sudo systemctl cancel` |
| No Wi-Fi | `journalctl -u project-pi-boot` ("Network unchanged" = hotspot management off), `nmcli dev wifi list`, `sudo cat /etc/project-pi/hotspot.env` (`PROJECT_PI_FORCE_HOTSPOT=1`?) |
| Refresh returns 409 | App-triggered git deploy is off (no `/etc/project-pi/allow-app-git-deploy`); update with the upgrade procedure; restart without pull still works |
| KWS not running | `systemctl status kws-alert`, `journalctl -u kws-alert -n 80` |
| Refresh fails | `ls -l /usr/local/sbin/project-pi-refresh` (re-run installer if missing), `sudo visudo -cf /etc/sudoers.d/project-pi-thesis` |
| App shows "The Pi requires an API token" | Required mode: enter the token from `/etc/project-pi/backend.env` in Settings, or set `PROJECT_PI_API_AUTH=open` in that file |
| `thermal-backend` exits at start: `PROJECT_PI_API_AUTH=required but PROJECT_PI_API_TOKEN is missing…` (or an unknown mode) | Set a token of 16+ random characters in `/etc/project-pi/backend.env`, or set `PROJECT_PI_API_AUTH=open` |
| Disk full | `df -h /`, `systemctl start project-pi-log-cleanup.service` |
| Old `kws-alert-vosk.service` | Masked by `install_headless.sh --apply`; `kws-alert.service` declares `Conflicts=` with it |
| `/api/status` shows `alert_outbox.pressure` or a "alert outbox overflow" fault | Alerts are not reaching the backend; `journalctl -u kws-alert | grep 'alert outbox'` lists each eviction |

### Raspberry Pi 5 GPIO / Blinka Diagnostics

Raspberry Pi 5 GPIO chip numbers are not stable identifiers across OS and
kernel builds. For MLX90640/Blinka startup, the important controller label is
`pinctrl-rp1`, not a fixed number such as `gpiochip11` or `gpiochip15`.

Inspect the current kernel GPIO view:

```bash
gpiodetect
```

Example:

```text
gpiochip15 [pinctrl-rp1]
```

Run the non-destructive Project Pi diagnostic:

```bash
cd ~/Project_Pi
python raspberry_pi/scripts/patch_blinka_lgpio_pin.py --diagnose
```

Then check Blinka/MLX90640 imports with the thermal virtual environment:

```bash
GPIOZERO_PIN_FACTORY=lgpio \
/home/thesis/thermal-env-sys/bin/python -c \
"import board, adafruit_mlx90640; print('Blinka/MLX90640 imports OK')"
```

The repository service patches Blinka at startup to discover `pinctrl-rp1`
dynamically, and the generic unit does not assume a fixed GPIO chip number. A
host-specific `LGPIO_CHIP=<chip-number>` (the deployed Pi uses 11) belongs in
`/etc/systemd/system/thermal-backend.service.d/10-local.conf`, which the installer
seeds from the previously installed unit and never overwrites.

## File Locations

```text
/usr/local/sbin/project-pi-boot                      # boot orchestration (root-owned copy of headless_boot.sh)
/usr/local/sbin/project-pi-refresh                   # mobile refresh (root-owned copy of pi_refresh.sh)
/usr/local/sbin/project-pi-log-cleanup               # journal vacuum (root-owned copy of log_cleanup.sh)
~/Project_Pi/raspberry_pi/systemd/kws-alert.service  # canonical KWS unit (installed by install_headless.sh)
/etc/project-pi/hotspot.env                          # SSID/password, PROJECT_PI_FORCE_HOTSPOT (root, 600; only with --configure-hotspot)
/etc/project-pi/backend.env                          # API auth mode (open by default)/token, caregiver credentials path (root, 600)
/etc/project-pi/allow-app-git-deploy                 # optional flag: lets /api/refresh git pull (absent by default)
/etc/systemd/system/thermal-backend.service.d/10-local.conf  # device-specific thermal/GPIO settings (never overwritten)
/var/lib/project-pi/install-backups/                 # installer backups of replaced files (root, 700)
/var/lib/project-pi/backend/alerts.jsonl             # KWS outbox of undelivered alerts (thesis, 700 dir)
/var/lib/project-pi/backend/alerts.rejected.jsonl    # alerts the backend rejected (4xx), kept for review
/var/lib/project-pi/backend/caregivers.json          # caregiver phone verifiers
```
