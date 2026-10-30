# Project Pi Backend

FastAPI backend for Raspberry Pi thermal data, audio RMS levels, keyword alerts, ReSpeaker LEDs, GPIO 17 button status, and safe reboot/shutdown.

Run manually:

```bash
source ~/thermal-env-sys/bin/activate
cd ~/Project_Pi/raspberry_pi/backend
uvicorn main:app --host 0.0.0.0 --port 8765
```

Headless boot and refresh: see [`../../docs/headless_setup.md`](../../docs/headless_setup.md).

Main endpoints. API authentication is optional and off by default: in no-token mode every route is open to anyone on the network. When `PROJECT_PI_API_TOKEN` is set in `/etc/project-pi/backend.env`, every `/api` and `/ws` route needs `Authorization: Bearer <token>`, except `/ws/alerts?protocol=2`, which authenticates caregiver phones itself:

- `GET /api/status`
- `POST /api/leds`
- `GET /api/button`
- `POST /api/alerts`
- `GET /api/alerts`
- `POST /api/refresh` — optional `git pull` (as thesis), then restart KWS via the root-owned helper; does not reinstall units
- `POST /api/shutdown`
- `POST /api/reboot`
- `WS /ws/thermal`
- `WS /ws/audio`
- `WS /ws/alerts`
