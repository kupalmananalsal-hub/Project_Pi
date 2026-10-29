# Phase 1 alert diagnostics — October 29, 2026

## Verified findings

The detector already creates a UUID before queuing each keyword event. The backend preserves that ID, makes POST retries idempotent while its registry entry is live, persists the classified event, and publishes it to connected WebSocket queues. The client parses the ID and authoritative decision. These facts establish a traceable code path; they do not establish delivery to a particular phone.

The backend suppresses a low raw voice score (`voice_below_threshold`) and produces an advisory for a midrange score with unavailable thermal evidence. The Caregiver intentionally shows a notice for advisory and no emergency for suppressed. Its current thermal gate also changes a backend `critical` voice-only event into a notice. The existing `alert_authority_test.dart` explicitly expects that behavior. The runtime awaits looping alarm playback before calling vibration, so vibration may not begin while the alarm runs. These are verified code-level explanations, not a diagnosis of a captured physical-device incident.

## Instrumentation and trace interpretation

Each diagnostic line has `kind: alert_trace`, UTC `timestamp`, `event_id`, `stage`, and `outcome`. Relevant extra fields include decision state and reason, thermal state, client count, and exception type. No raw audio is logged. Search logs from the detector, backend, and Caregiver for one `event_id`, then order the records by timestamp and stage. A successful POST records backend acceptance, not phone handling. A successful WebSocket send records transport write, not client receipt.

| Scenario | Expected last client stage under current policy | Reason |
| --- | --- | --- |
| Low-score suppressed | `provider_disposition: suppressed` | Backend voice score is below policy threshold. |
| Advisory, thermal unavailable | `provider_disposition: notice` | Advisory intentionally produces a keyword notice. |
| Thermal-confirmed emergency | `overlay: activated`, followed by output attempts | Client accepts the authoritative emergency with human evidence. |
| Voice-only critical, thermal unavailable | `provider_disposition: thermal_gate_notice` | Current client thermal gate blocks the full emergency. This is the Phase 2 policy conflict. |

For an output failure, the relevant `notification`, `alarm_audio`, or `vibration` record has `outcome: failed` and `error_type`. If an earlier output fails, later output stages currently remain unattempted. A queue overflow produces `queue_publish: overflow`; Phase 3 must add durable replay and delivery acknowledgements before lost delivery can be ruled out.

## Verification performed

- Python syntax compilation and `git diff --check`: passed.
- `test_alert_trace.py`: passed; verifies machine-readable event ID, stage, and failure type.
- `test_kws_event_id.py`: seven tests passed with the workspace temporary directory; default Windows sandbox temp storage produced permission errors on a separate run.
- Dart analyzer on changed Dart files and the alert authority test: passed.
- Flutter tests: not completed. The local runner attempted to contact `pub.dev` for `flutter_lints` and the network request failed. No Android or Raspberry Pi hardware was available or tested.
- Backend smoke suite: attempted, but did not complete in this environment. Its temporary-directory setup initially failed under the sandbox default path; the workspace-temp rerun stalled and was stopped. Its existing assertions are therefore not reported as passing.

## Phase 2 patch proposal

1. Make the backend decision authoritative for `critical` voice-only events: activate the full overlay, alarm, and vibration while showing the actual unavailable, stale, or negative thermal state. Keep suppressed and advisory behavior; retain emergency behavior for thermal-confirmed and Resident double-tap events.
2. Update the existing voice-only authority test and add explicit unavailable/stale/negative thermal cases. Keep duplicate-event handling idempotent.
3. Configure and load alarm audio, then start looping playback without waiting for playback completion before vibration. Give notification, audio, and vibration separate error boundaries and test that vibration starts while sound remains active, including when notification fails.
4. Verify those changes on a physical Android phone with a Raspberry Pi test event. Record the event ID, all stage outcomes, overlay and output observations, and the last successful stage for any failure.
