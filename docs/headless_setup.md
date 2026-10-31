# Headless Raspberry Pi 5 Setup

Power-on only operation: the Pi joins hotspot **Teddy**, updates packages, starts all services, and accepts mobile-app commands (including **Refresh KWS** without SSH).

## What Runs Automatically

| Component | Purpose |
|:---|:---|
| `project-pi-boot.service` | Hotspot connect, apt update (≤1×/24h), log cleanup (runs the root-owned `/usr/local/sbin/project-pi-boot`; unit files are only installed by `install_headless.sh`) |
| `thermal-backend.service` | FastAPI on port **8765** (`~/thermal-env-sys`) |
| `kws-alert.service` | Triple-engine KWS (`~/kws-env`) |
| `apk-server.service` | APK HTTP server on port **8080** |
| `project-pi-apt-update.timer` | Daily `apt-get update` |
| `project-pi-log-cleanup.timer` | Daily journal vacuum + temp log trim |

## One-Time Install (on the Pi)

SSH in once, clone or pull the repo, then run:

```bash
cd ~/Project_Pi
git pull
chmod +x raspberry_pi/scripts/*.sh
sudo PROJECT_PI_HOTSPOT_SSID=Teddy \
     PROJECT_PI_HOTSPOT_PASSWORD='<hotspot password>' \
     bash raspberry_pi/scripts/install_headless.sh
```

No password is shipped: the first install needs `PROJECT_PI_HOTSPOT_PASSWORD`;
later runs without it keep the existing `/etc/project-pi/hotspot.env` (mode `600`,
not in git).

The installer also:

- creates `/etc/project-pi/backend.env` (root, mode `600`) once, with API
  authentication **off** (no-token mode): the app needs no token, and every
  `/api`/`/ws` route, including reboot, shutdown, refresh and model deploy, is open
  to anyone on the network. Use this only on an isolated, trusted hotspot. To turn
  authentication on, follow the comments in that file (or "Enabling authentication
  later" in [m1_m2_upgrade_and_rollback.md](m1_m2_upgrade_and_rollback.md)) and
  enter the token in each app under **Settings → Pi API token (optional)**.
- copies the root-run scripts to `/usr/local/sbin/project-pi-{refresh,boot,log-cleanup}`
  and installs `/etc/sudoers.d/project-pi-thesis`, which allows only those exact
  commands, three `systemctl restart`s and the power commands.

Upgrading an existing Pi from before this change: follow
[m1_m2_upgrade_and_rollback.md](m1_m2_upgrade_and_rollback.md) (phones first).

## After Install — Normal Use

1. Power on the Pi (no monitor/keyboard).
2. Wait ~1–2 minutes for hotspot association and services.
3. Open the Flutter app (Controls tab shows connection; Monitor shows thermal/audio).
4. Use **Refresh KWS Service** on the Controls tab instead of manual `systemctl`/`cp` commands.

## Service Order

```text
boot → project-pi-boot (oneshot)
     → thermal-backend
     → kws-alert
     → apk-server
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

# Backend health (the header is ignored in no-token mode and required when auth is on;
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

With `git_pull`, the backend runs `git pull --ff-only` as `thesis`; the Pi checkout
must be on a branch tracking `origin/main` (a detached checkout returns `ok: false`
and restarts nothing; see `docs/m1_m2_upgrade_and_rollback.md`, step 2). It then runs the
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

```bash
cd ~/Project_Pi && git pull
sudo bash raspberry_pi/scripts/install_headless.sh
```

The app's **Refresh KWS Service** can pull and restart, but it never reinstalls
units, sudoers or root scripts; re-run the installer when those change.

## Troubleshooting

| Symptom | Check |
|:---|:---|
| `thermal-backend` stops right after start | Do not run `daemon-reload` while it is running. Kill stuck boot: `pgrep -af headless_boot`. Then `sudo systemctl start thermal-backend --no-block` |
| `systemctl start` hangs | `sudo systemctl stop project-pi-boot; sudo systemctl cancel` |
| No Wi-Fi | `cat /etc/project-pi/hotspot.env`, `nmcli dev wifi list`, `journalctl -u project-pi-boot` |
| KWS not running | `systemctl status kws-alert`, `journalctl -u kws-alert -n 80` |
| Refresh fails | `ls -l /usr/local/sbin/project-pi-refresh` (re-run installer if missing), `sudo visudo -cf /etc/sudoers.d/project-pi-thesis` |
| App shows "The Pi requires an API token" | Auth is on: enter the token from `/etc/project-pi/backend.env` in Settings, or turn auth off in that file |
| `thermal-backend` exits at start: `API authentication is enabled but PROJECT_PI_API_TOKEN is missing…` | Set a token of 16+ random characters in `/etc/project-pi/backend.env`, or comment out `PROJECT_PI_API_AUTH=required` |
| Disk full | `df -h /`, `systemctl start project-pi-log-cleanup.service` |
| Old `kws-alert-vosk.service` | Deprecated; use `kws-alert.service` (installed by `install_headless.sh`) |

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
dynamically. For unusual deployments, an administrator can temporarily set
`LGPIO_CHIP=<chip-number>`, but the default service does not assume a fixed
GPIO chip number.

## File Locations

```text
/usr/local/sbin/project-pi-boot                      # boot orchestration (root-owned copy of headless_boot.sh)
/usr/local/sbin/project-pi-refresh                   # mobile refresh (root-owned copy of pi_refresh.sh)
/usr/local/sbin/project-pi-log-cleanup               # journal vacuum (root-owned copy of log_cleanup.sh)
~/Project_Pi/raspberry_pi/systemd/kws-alert.service  # canonical KWS unit (installed by install_headless.sh)
/etc/project-pi/hotspot.env                          # SSID/password (root, 600)
/etc/project-pi/backend.env                          # API auth mode/token (off by default), caregiver credentials path (root, 600)
/var/lib/project-pi/backend/alerts.jsonl             # KWS outbox of undelivered alerts (thesis, 700 dir)
/var/lib/project-pi/backend/caregivers.json          # caregiver phone verifiers
/var/lib/project-pi/last-apt-update                  # apt throttle stamp
```
