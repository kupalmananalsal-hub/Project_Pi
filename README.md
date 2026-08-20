# Thermal Audio Monitor

Flutter mobile app for the Raspberry Pi 5 thermal camera and voice alert backend.

## Backend Defaults

- Current hotspot Pi IP: `10.129.205.32`
- Port: `8765`
- Hostname fallback: `raspberrypi.local`
- REST base URL: `http://10.129.205.32:8765/api/`
- Thermal WebSocket: `ws://10.129.205.32:8765/ws/thermal`
- Audio WebSocket: `ws://10.129.205.32:8765/ws/audio`
- Alert WebSocket: `ws://10.129.205.32:8765/ws/alerts`

The Pi connects to the phone hotspot as a client, so the hotspot may assign a
different IP later. If that happens, update the Pi IP in the Flutter app
settings. `raspberrypi.local` can be useful from laptops and some networks, but
Android may not resolve it reliably.

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
- Full-screen alert overlay for trained distress phrases such as `Help`, `Tulong`, `Save me`, and Tagalog help requests, with notification, alarm tone, and vibration until dismissed.
- RGB control for 3 LEDs with solid, breathing, and rainbow client-side patterns.
- GPIO button monitor plus confirmed reboot and shutdown actions.

## Distress Phrase Models

The Pi keyword service can load multiple openWakeWord `.tflite` distress phrase
models from `raspberry_pi/kws/openwakeword_models/`. Training guidance for the
expanded English and Tagalog phrase set is in
[`docs/openwakeword_distress_training_plan.md`](docs/openwakeword_distress_training_plan.md).

## Mobile Notes

Android uses cleartext local-network traffic for the Pi HTTP/WebSocket server. The app also requests notification, vibration, full-screen intent, and gallery-save permissions.

iOS local-network and photo-library permissions are declared. Time-sensitive notifications work when allowed by the device settings; critical silent-switch bypass requires Apple entitlement approval.
