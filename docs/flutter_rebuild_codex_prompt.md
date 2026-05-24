# Codex 5.5 Prompt: Rebuild Flutter App with Existing Pi Backend

Use this prompt in Codex 5.5, Cursor, or another AI coding tool when rebuilding the mobile app.

````text
I need you to rebuild a Flutter mobile application from scratch that connects to my fully functional Raspberry Pi 5 backend. The backend is already tested and working. I only need the Flutter frontend.

## Current Project State
- Raspberry Pi 5 backend is COMPLETE and RUNNING
- MLX90640 thermal camera is working (I2C address 0x10)
- ReSpeaker 2-Mics Pi HAT is working (audio codec at 0x1A)
- FastAPI + WebSocket server is in `/home/thesis/thermal_cam_project/backend/main.py`
- Keyword spotting for "Help" / "Tulong" is configured in `picovoice-env`
- Flutter app was RESET and needs complete rebuild

## Backend API

The Pi server runs on port 8765 and provides these endpoints.

### WebSocket
- `ws://<pi-ip>:8765/ws/thermal` streams 32x24 thermal array JSON every 250 ms
- `ws://<pi-ip>:8765/ws/audio` streams mic levels, 2-channel RMS, every 50 ms
- `ws://<pi-ip>:8765/ws/alerts` pushes keyword detection events:

```json
{"event": "keyword_detected", "keyword": "tulong", "confidence": 0.95, "timestamp": "..."}
```

### REST Endpoints
- `GET /api/status` returns CPU temp, RAM usage, uptime, I2C devices
- `POST /api/leds` controls ReSpeaker RGB LEDs:

```json
{"led": 0, "r": 255, "g": 0, "b": 0}
```

- `GET /api/button` returns last button press events from GPIO 17
- `POST /api/shutdown` safely shuts down the Pi
- `POST /api/reboot` safely reboots the Pi

## Flutter App Requirements

### Screen 1: Connection and Status
- Manual IP entry field, pre-filled with `10.118.136.32`
- Port field, default `8765`
- Connect and Disconnect buttons
- Connection status indicator: green dot when connected, red dot when disconnected
- Pi system status display: CPU temp, RAM, uptime

### Screen 2: Thermal Camera
- Real-time thermal image display, 32x24 upscaled to 640x480
- Color map selector: Jet, Inferno, Magma, Hot, Bone
- Temperature range sliders for min and max
- Center pixel temperature display
- Tap to read temperature at any pixel
- Screenshot button that saves to gallery
- Frame rate indicator

### Screen 3: Audio and Alerts
- Dual microphone level meters
- Keyword detection log with timestamps
- Full-screen red alert when "Tulong" or "Help" is detected:
  - Pulsing animation
  - Loud alarm sound, even in silent mode where supported
  - Continuous vibration until dismissed
  - Dismiss button
- Alert history list

### Screen 4: Controls
- RGB LED color picker for 3 individual LEDs
- Preset patterns: solid, breathing, rainbow
- LED brightness slider
- User button status monitor
- Shutdown Pi button with confirmation dialog
- Reboot Pi button with confirmation dialog

### Screen 5: Settings
- Pi IP or hostname configuration
- Port configuration
- Alert sound selection
- Theme toggle: dark/light
- About section

## Technical Requirements
- State management: Riverpod
- WebSocket: `web_socket_channel`
- HTTP: `dio`
- Local notifications: `flutter_local_notifications` with alarm importance
- Sound: `just_audio`
- Vibration: `vibration`
- Charts: `fl_chart`
- Color picker: `flutter_colorpicker`
- Image save: `gal` or `image_gallery_saver`
- Persistence: `shared_preferences`
- Theme: Material Design 3, dark theme default
- Navigation: bottom navigation bar with 5 tabs

## Pi Connection Info
- IP: `10.118.136.32`
- Port: `8765`
- Hostname fallback: `raspberrypi.local`

The Pi connects to the phone hotspot as a DHCP client. The hotspot may assign a
different IP later, so keep manual IP entry available in Settings.

## Deliverables
1. Complete `pubspec.yaml` with all dependencies
2. `lib/main.dart` with app entry, theme, and Riverpod setup
3. All 5 screens as separate files
4. WebSocket service class with auto-reconnect
5. Models for thermal data, audio data, alerts, and system status
6. Providers for connection, thermal, audio, and alerts state
7. Reusable widgets: thermal display, audio meter, LED control, status card
8. `README.md` with setup instructions

Generate the code file by file, starting with `pubspec.yaml` and `lib/main.dart`.
````
