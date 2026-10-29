# Phase 2 — Caregiver emergency execution repair

Baseline: `525d22a479a922779978c22e22ebbca59f40d9cc`.

## Behavior

| Alert | Before | After |
| --- | --- | --- |
| Suppressed | No emergency | Unchanged |
| Advisory | Notice and soft beep | Unchanged |
| Confirmed with human evidence | Full emergency | Unchanged |
| Critical with negative, stale, or unavailable thermal evidence | Notice only | Overlay, sound, vibration |
| Manual critical panic | Emergency falsely marked human-positive | Emergency with actual thermal evidence |
| Historical / duplicate response | History only / ignored for output | Unchanged |

Looping playback now starts without awaiting its completion. Notification, sound, and vibration have independent exception boundaries and begin concurrently. Start and stop transitions are serialized; dismissal checks that the displayed event has not been replaced before clearing state. Cleanup attempts each channel even when another fails.

## Changed code

- `lib/providers/alerts_provider.dart`: `_startAuthoritativeEmergencyAlert` honors critical decisions and separates manual authorization from human evidence; `dismissActiveAlert` protects newer state.
- `lib/services/alert_runtime_service.dart`: `startEmergency`, `stopEmergency`, `dispose`, and audio preparation/playback isolate failures and serialize transitions. Notification text reports thermal state. Output methods provide test seams for simulated plugins.
- `lib/widgets/alert_overlay.dart`: displays backend thermal status when no human evidence exists.
- `lib/services/reconnecting_web_socket_service.dart`: logs connection attempts, readiness, failures, reconnects and disconnects with host, port and generation, without URI credentials.
- `raspberry_pi/backend/main.py`: `AlertHub.publish` reports enqueue counts, failed enqueues, overflow drops and zero subscribers; `api_alerts` distinguishes received requests from claim outcomes.

## Verification

- `py -m unittest discover -s test -p 'test_*.py'`: 180 tests passed, including backend smoke tests and the new no-subscriber/overflow test.
- `flutter test --concurrency=1`: 49 tests passed. Added tests cover unavailable/stale/negative critical events, historical handling, looping playback with vibration, notification failure, and socket failure/reconnect diagnostics. An earlier real refused-socket test timed out during cleanup; the final test injects a connection failure deterministically.
- `dart analyze lib test`: no issues. Dart formatting and `git diff --check` passed.
- Tests use fake plugin outputs and an injected failing socket connector. These results are not physical-device validation. Running tests outside the sandbox resolved Phase 1's temp/cache limitations.

## Known limits and device checklist

Historical SQLite rows still omit the original event ID and complete decision envelope. Phase 3 should migrate storage and add acknowledgement/replay; enqueue and send records do not prove phone handling. Existing recognition models and decision thresholds were not changed. Serialized operations still depend on native plugin calls completing; OS permission, audio focus, background restrictions and vibration hardware require device testing.

On a Raspberry Pi 5 and Android phone, capture one stable event ID per scenario: thermal-positive confirmed, critical with sensor disconnected, critical with thermal-negative evidence, and manual double-tap. Observe overlay, accurate thermal label, audible alarm, vibration and dismissal. Repeat with notifications denied, two rapid emergencies, and dismissal during startup. Interrupt Wi-Fi and verify connection diagnostics after reconnect. Record actual results and remaining failures before release; no such device tests were performed here.
