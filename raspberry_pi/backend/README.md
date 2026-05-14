# Project Pi Backend

FastAPI backend for Raspberry Pi thermal data, audio RMS levels, keyword alerts, ReSpeaker LEDs, GPIO 17 button status, and safe reboot/shutdown.

Run manually:

```bash
source ~/thermal-env-sys/bin/activate
cd ~/Project_Pi/raspberry_pi/backend
uvicorn main:app --host 0.0.0.0 --port 8765
```

Main endpoints:

- `GET /api/status`
- `POST /api/leds`
- `GET /api/button`
- `POST /api/alerts`
- `GET /api/alerts`
- `POST /api/shutdown`
- `POST /api/reboot`
- `WS /ws/thermal`
- `WS /ws/audio`
- `WS /ws/alerts`
