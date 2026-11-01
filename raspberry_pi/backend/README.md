# Project Pi Backend

FastAPI backend for Raspberry Pi thermal data, audio RMS levels, keyword alerts, ReSpeaker LEDs, GPIO 17 button status, and safe reboot/shutdown.

Run manually:

```bash
source ~/thermal-env-sys/bin/activate
cd ~/Project_Pi/raspberry_pi/backend
uvicorn main:app --host 0.0.0.0 --port 8765
```

Headless boot and refresh: see [`../../docs/headless_setup.md`](../../docs/headless_setup.md).

Main endpoints. `PROJECT_PI_API_AUTH` in `/etc/project-pi/backend.env` selects the mode, reported as `api_auth_mode` in `/api/status`. `open` (default): no authentication, every route is open to anyone on the network (isolated hotspot only; the old app's token is not security). `required`: every `/api` and `/ws` route needs `Authorization: Bearer <PROJECT_PI_API_TOKEN>` (16+ characters, never the legacy token), except `/ws/alerts?protocol=2`, which authenticates caregiver phones itself:

- `GET /api/status`
- `POST /api/leds`
- `GET /api/button`
- `POST /api/alerts`
- `GET /api/alerts`
- `POST /api/refresh` — restart KWS (and optionally the backend) via the root-owned helper; `git_pull` returns 409 unless `/etc/project-pi/allow-app-git-deploy` exists; never reinstalls units
- `POST /api/shutdown`
- `POST /api/reboot`
- `WS /ws/thermal`
- `WS /ws/audio`
- `WS /ws/alerts`
