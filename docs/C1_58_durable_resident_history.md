# Durable Phone 2 history correction

Baseline: `387dd710ca91c4a6f03b685d2b2f079ba0f6795c`.
Branch: `codex/c158-durable-resident-history`.

Resident commands now commit manual records using the same backend SQLite AlertStore as KWS records, before publishing to the existing alert WebSocket and returning history_persisted to Phone 2. GET /api/alerts retrieves both sources. Main restores this history on connection and merges it with incoming events by event ID. Dismissal and acknowledgement change presentation/delivery state; they do not remove history rows. Explicit operator Clear history remains the existing destructive history action.

Single tap stores an advisory manual keyword record titled KEYWORD SPOTTED. Main shows it without a confirmation dialog and loops its local keyword beep until dismissal, disconnection of Main, or emergency preemption. Double tap stores a critical manual emergency record titled EMERGENCY!, linked through supersedes_event_id to the keyword record. This immutable two-record trail preserves both tap timestamps and avoids mutating previously delivered sequence/ACK identities. Each stage has a deterministic event ID, so repeated command delivery does not create additional history rows. The existing command/gesture idempotency and authenticated Resident session remain in use.

Stored source is resident_manual, event is manual_trigger, and manual_event_type distinguishes keyword/emergency. gesture_id and supersedes_event_id preserve the trail. is_simulation is true. Confidence is zero rather than a fabricated ML score, human_detected is false, and thermal_state is unknown rather than invented evidence. These explicit manual decisions do not pass through KWS confidence classification and do not claim openWakeWord inference. No external dispatch action is introduced.

Main uses its normal durable delivery/alert controller rather than the transient ResidentTestLayer. Its manual keyword notice is acknowledged as presented, receives an explicit dismiss control, and uses repeating local audio. Manual emergency presentation uses EMERGENCY! and the siren regardless of the selected non-siren sound. Real emergencies retain priority over manual presentations. History and overlay details identify Manual trigger / Simulation; History does not show a fictitious confidence score for these records. Existing history/replay gates determine whether reconnecting events present or remain historical; no general replay-window policy change is made.

Phone 2 retains the previous immediate tap/double-tap gesture and foreground audio. Its response now distinguishes durable history acceptance from a backend requiring an update. Saved history is not represented as proof of physical sound or Main presentation. Pairing, endpoint configuration, authorization, thermal processing, KWS models/thresholds and the disabled-by-default remote-mute gates remain unchanged.

## Changed files

- lib/models/alert_event.dart
- lib/providers/alerts_provider.dart
- lib/screens/app_shell.dart
- lib/screens/history_screen.dart
- lib/screens/monitor_screen.dart
- lib/services/alert_runtime_service.dart
- lib/services/resident_control_client.dart
- lib/widgets/alert_overlay.dart
- raspberry_pi/backend/main.py
- raspberry_pi/resident_control.py
- docs/C1_58_durable_resident_history.md

## Handoff and limitations

Both Android release flavors are compiled with the original IDs and signing configuration. Local generated Android build metadata uses version code 3, version name 1.0.0. No tests, pytest, Flutter tests, Flutter analysis, acoustic inference or physical validation are performed by explicit instruction. These are untested development changes; successful compilation is not integration certification.

The Pi backend source update is mandatory: installing the APKs alone cannot persist events on an older backend. The local handoff includes the current Pi-only patch against 387dd71, a cumulative Pi patch against 7155269, source snapshots, APKs and build logs. Review/integrate in an isolated development checkout, preserving intervening Pi changes. No production checkout is modified, no Pi transfer/restart/deployment is performed, and no push or merge is performed.

Existing previously transient events were never persisted and are not reconstructed or fabricated by this change. Their original timestamps cannot be recovered after the old backend has discarded them. New records survive application/backend restart through SQLite. As with existing history, the UI loads the latest 100 records and an explicit operator database/history deletion can remove records.

Android volume, focus, routing and background restrictions can affect sound. The previous unsafe APK packaging cache is addressed by scheduling Flutter compilation before forced JNI merge/strip/package tasks. No additional validation suite is run.
