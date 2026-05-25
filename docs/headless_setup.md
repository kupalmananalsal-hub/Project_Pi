# Headless Raspberry Pi 5 Setup

Power-on only operation: the Pi joins hotspot **Teddy**, updates packages, starts all services, and accepts mobile-app commands (including **Refresh KWS** without SSH).

## What Runs Automatically

| Component | Purpose |
|:---|:---|
| `project-pi-boot.service` | Hotspot connect, sync systemd units from repo, apt update (≤1×/24h), log cleanup, start stack |
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
     PROJECT_PI_HOTSPOT_PASSWORD=bayadkamuna \
     bash raspberry_pi/scripts/install_headless.sh
```

Custom hotspot credentials:

```bash
sudo PROJECT_PI_HOTSPOT_SSID=Teddy \
     PROJECT_PI_HOTSPOT_PASSWORD='your-password' \
     bash raspberry_pi/scripts/install_headless.sh
```

Credentials are stored in `/etc/project-pi/hotspot.env` (mode `600`, not in git).

### Optional: passwordless sudo for shutdown/reboot (if not already set)

`install_headless.sh` installs `/etc/sudoers.d/project-pi-thesis` for refresh and power actions.

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

# Backend health
curl -s http://127.0.0.1:8765/api/status | python3 -m json.tool

# Refresh API (same as mobile app)
curl -s -X POST http://127.0.0.1:8765/api/refresh \
  -H 'Content-Type: application/json' \
  -d '{"git_pull": false, "restart_backend": false}'

# Re-run full boot script
sudo /home/thesis/Project_Pi/raspberry_pi/scripts/headless_boot.sh
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

Runs `raspberry_pi/scripts/pi_refresh.sh` via passwordless sudo.

## APK Over-the-Air

```bash
cd ~/Project_Pi
flutter build apk --debug
cp raspberry_pi/apk_server/index.html build/app/outputs/flutter-apk/index.html
```

Phone browser: `http://10.159.83.236:8080/`

If the hotspot gives the Pi a different address, check `hostname -I` and use
`http://<PI_IP>:8080/` instead.

## Updating the Pi After Git Push

On the Pi (once):

```bash
cd ~/Project_Pi && git pull
sudo bash raspberry_pi/scripts/install_headless.sh
```

Or from the app: **Refresh KWS Service**.

## Troubleshooting

| Symptom | Check |
|:---|:---|
| `thermal-backend` stops right after start | Do not run `daemon-reload` while it is running. Kill stuck boot: `pgrep -af headless_boot`. Then `sudo systemctl start thermal-backend --no-block` |
| `systemctl start` hangs | `sudo systemctl stop project-pi-boot; sudo systemctl cancel` |
| No Wi-Fi | `cat /etc/project-pi/hotspot.env`, `nmcli dev wifi list`, `journalctl -u project-pi-boot` |
| KWS not running | `systemctl status kws-alert`, `journalctl -u kws-alert -n 80` |
| Refresh fails | `sudo visudo -cf /etc/sudoers.d/project-pi-thesis`, script executable |
| Disk full | `df -h /`, `systemctl start project-pi-log-cleanup.service` |
| Old `kws-alert-vosk.service` | Deprecated; use `kws-alert.service` (boot script installs it every boot) |

## File Locations

```text
~/Project_Pi/raspberry_pi/scripts/headless_boot.sh   # boot orchestration
~/Project_Pi/raspberry_pi/scripts/pi_refresh.sh      # mobile refresh
~/Project_Pi/raspberry_pi/scripts/log_cleanup.sh     # journal vacuum
~/Project_Pi/raspberry_pi/systemd/kws-alert.service  # canonical KWS unit
/etc/project-pi/hotspot.env                          # SSID/password
/var/lib/project-pi/last-apt-update                  # apt throttle stamp
```
