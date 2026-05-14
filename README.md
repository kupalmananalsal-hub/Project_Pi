# Thermal Audio Monitor

Flutter mobile app for the Raspberry Pi 5 thermal camera and voice alert backend.

## Backend Defaults

- Current hotspot Pi IP: `10.156.203.236`
- Router fallback Pi IP: `192.168.1.34`
- Port: `8765`
- Hostname fallback: `raspberrypi.local`
- REST base URL: `http://10.156.203.236:8765/api/`
- Thermal WebSocket: `ws://10.156.203.236:8765/ws/thermal`
- Audio WebSocket: `ws://10.156.203.236:8765/ws/audio`
- Alert WebSocket: `ws://10.156.203.236:8765/ws/alerts`

## Flutter Setup

1. Install Flutter and verify with `flutter doctor`.
2. Run `flutter pub get`.
3. Start the Pi backend on port `8765`.
4. Run the app with `flutter run`.

## Features

- Manual Pi IP/port connection with persisted settings.
- System status polling for CPU temperature, RAM, uptime, and I2C devices.
- Auto-reconnecting WebSockets for thermal frames, audio RMS, and keyword alerts.
- 32x24 thermal display with color maps, temperature range slider, tapped-pixel readout, FPS, and gallery screenshots.
- Dual microphone meters with a short live chart.
- Full-screen alert overlay for `Help` and `Tulong`, notification, alarm tone, and vibration until dismissed.
- RGB control for 3 LEDs with solid, breathing, and rainbow client-side patterns.
- GPIO button monitor plus confirmed reboot and shutdown actions.

## Mobile Notes

Android uses cleartext local-network traffic for the Pi HTTP/WebSocket server. The app also requests notification, vibration, full-screen intent, and gallery-save permissions.

iOS local-network and photo-library permissions are declared. Time-sensitive notifications work when allowed by the device settings; critical silent-switch bypass requires Apple entitlement approval.
