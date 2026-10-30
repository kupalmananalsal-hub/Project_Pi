# Phase 3 implementation report

Date: 2026-10-30 (Asia/Manila). Baseline: `cf9fd0e8817094617ea1f38ff05e25156c8e720f`.

Original Phase 3 commits (included in the review branch):

- Backend: `4fa21c51c7213e4e1b3d8b1667727ccfdf0f9007`.
- Flutter: `2b7f004e2ec8939a49a2176e1932f1d264bd02fc`.
- Documentation: `5792e17a3e8964a15dbf816923a9985686341cea`, adding `docs/phase2_physical_baseline_worksheet.md`, `docs/phase3_delivery_design.md`, and this report. It records deployment prerequisites, protocol/migration design, verification evidence and release limitations; it makes no runtime changes.

The user explicitly authorized development before device testing and approved recovery of unresolved critical events up to five minutes old, with the review correction that previously presented but unconfirmed events can reactivate after app restart. An event that is currently active must not duplicate; explicit user confirmation prevents reactivation. Physical Raspberry Pi 5 and Android validation is still required before release. No physical devices were tested for this report.

## Delivered behavior

SQLite retains event IDs, complete classified envelopes, schema version, persistence timestamps and request fingerprints. Existing AUTOINCREMENT IDs are the server sequence. Migration adds nullable columns and tables without replacing legacy rows. A partial unique index protects new event IDs. WAL and an immediate insert transaction prevent duplicate rows across independent connections. Retry lookup precedes thermal reclassification; a changed request under the same ID returns HTTP 409. Manual alert submissions now accept producer IDs. Existing REST history fields and the legacy WebSocket stream remain available.

Version 2 WebSocket delivery reads durable database rows rather than depending on the lossy publication queue. Recovery uses ascending sequences and pages of at most 100, with a fixed initial high-water boundary. Once recovery finishes, a 250 ms poll offers new rows as live events. A persistence-before-publication crash therefore does not require another publication to recover the event. Suppressed/advisory/live confirmed/live critical classification behavior remains under the existing provider policy.

Per-installation delivery records distinguish offered, received, presented and user-confirmed timestamps. The paired phone authenticates with its own secret; the backend stores only SHA-256 verifiers. Identity comes from that session, not acknowledgement payloads. Acknowledgements validate UUID, sequence and prior offer, and repeat acknowledgements retain their first timestamp. A server send alone does not mark receipt.

Flutter stores credentials through platform secure storage. Its inbox and acknowledgement outbox use alternating, flushed JSON snapshots in application support storage. Processing is serialized; receipt is persisted before acknowledgement, and presentation intent before output execution. A completed-page cursor is saved only after all preceding event dispositions, so an interrupted page is replayed. Duplicate UUIDs within the current run and currently active events do not restart outputs. Durable intent/processed flags are not confirmation and do not veto eligible restart recovery. Uncommitted acknowledgements resend on reconnect. Explicit dismissal sends user confirmation; disposal and network cleanup do not.

Only a replayed `critical` event aged 0–300 seconds by the server persistence clock, with no explicit user confirmation recorded for that phone, is eligible for emergency presentation. Other recovery events are history-only. Local durable user confirmation suppresses repeats even if its server acknowledgement was lost. Active-alert state and a per-run handled set suppress duplicates during ordinary reconnection; a new app run may reactivate an eligible, unconfirmed event. Freshness expires automatic presentation, not event storage. No retention deletion was enabled.

Socket readiness is bounded at 10 seconds, reconnect backoff at 2–30 seconds and teardown attempts at 2 seconds. Generations invalidate stale callbacks. The server sends a heartbeat every 15 seconds and requires its nonce within 10 seconds; the client watchdog reconnects after 35 seconds without protocol traffic. An already-active installation session is rejected; cancellation now removes the session before awaited cleanup.

Emergency stop invalidates startup immediately and runs independently of pending start Futures. Native operations have five-second bounds and generation checks between asynchronous preparation steps. Audio session configuration is shared and awaited by the audio path, independently of notification permissions. Late notification completions cancel their own generation-specific notification; late vibration completions attempt cancellation when no emergency remains active. Authoritative thermal labels use event-associated backend evidence, and no unrelated local frame is attached to the emergency overlay.

## Verification

The full suites ran on the Windows development host; Linux backup permission tests also ran on GitHub Actions Ubuntu 24.04. Python integration uses real FastAPI HTTP/WebSocket routing and temporary SQLite databases; sensor and ML imports are stubbed. Flutter tests use fake native outputs. These are software results, not hardware or acoustic-accuracy measurements.

| Check | Result |
| --- | --- |
| Complete Python suite on Windows, including ASGI integration | 203 discovered: 200 passed, 3 Linux-only permission tests skipped; 11.330 seconds |
| Complete Flutter suite | 69 passed, 17 seconds in the recorded run |
| Linux backup permission tests (Ubuntu 24.04 CI) | 3 passed; no skips |
| Dart analysis | No issues found |
| Review recovery/storage regression | Intent crash, confirmation, expiry, failed writes, stale sessions and acknowledgement retry covered |
| Dart formatting, review correction sources/tests | Checked; 0 pending format changes |
| Python compilation and Git whitespace check | Passed |
| Physical Pi 5 / Android sound, vibration, lock screen, focus, battery restrictions | NOT RUN |

Reproduce from the repository root:

```powershell
py -m venv build/phase3-test-env
build/phase3-test-env/Scripts/python.exe -m pip install -r test/requirements-delivery.txt numpy
build/phase3-test-env/Scripts/python.exe -m unittest discover -s test -p 'test_*.py'
flutter test --concurrency=1
dart analyze lib test
```

The base Python environment lacks FastAPI/HTTPX; integration tests explicitly skip there. The latest run used the provisioned environment; its three skips are explicitly Linux-only permission tests, covered separately by the Linux workflow. The first analyzer run failed on its shared Windows performance-cache directory; the successful run set LOCALAPPDATA to the ignored `build/phase3-local` directory. Initial integration failures exposed cancellation cleanup and test-loader registration issues, both repaired. The widget smoke test now pumps teardown so bounded cleanup timers can finish.

### Reproduced event traces

The ASGI tests assert IDs, decisions and acknowledgement state rather than treating trace counts as delivery proof. The latest local execution logs are `build/pr4-followup-python.log` and `build/pr4-followup-flutter-full.log` (ignored generated output).

| Event ID | Verified sequence and last successful stage |
| --- | --- |
| `integration-critical` | POST → backend critical/manual classification → SQLite sequence 1 → phone-a replay send → `ack_received` committed → `ack_presented` committed → store/registry restart → same-ID POST returns original record → phone-a replay has `present=true` because presentation alone does not confirm resolution → phone-b replay has `present=true`. Last stage: independent replay classification; no physical output claim. |
| `missed-0`, `missed-1`, `missed-2` | Phone disconnects → POST/persist with no subscriber → reconnect → all three original IDs delivered in order → replay complete. Last stage: replay completion. |
| `two-live` | Two authenticated phones connected → POST/persist → both receive live event → phone-a receipt committed, phone-b receipt remains unset. Last stage: per-phone acknowledgement persistence. |
| `overflow-0` through `overflow-104` | 105 POSTs persist → legacy queue holds only 100 → version 2 replay retrieves all 105 in pages of 100 and 5. Last stage: durable recovery completion. |
| `spoof-target` | POST/persist → phone-a offer → acknowledgement claiming phone-b rejected → phone-b receipt remains unset. Last stage: offer/send; failure at acknowledgement validation. |
| Flutter `recent`, `old` | `recent` presents once per app run, duplicates do not repeat output, and an unconfirmed restart can reactivate; `old` is history-only. Last stage: client disposition/outbox persistence using a fake output callback. |
| Flutter `stalled` | Notification/preparation Futures held unresolved → dismissal completes → late preparation cannot invoke playback → later emergency starts. Last stage: runtime execution with fake plugins. |
| Flutter `stale-local` | Earlier local human-positive state → authoritative critical/negative event → emergency activates with human label false and no local thermal frame. Last stage: provider state. |

Additional tests cover legacy migration, concurrent duplicate inserts, fingerprint conflicts, request bounds, unoffered and mismatched acknowledgements, 300-second expiration boundaries, heartbeat timeout/reconnect and stalled readiness teardown. The existing publication, authority, detector and training regressions remain included.

The backup test keeps a WAL-mode source connection open, commits a marker, invokes the backup helper, verifies that marker and the complete envelope in the restored database, and verifies that a second invocation refuses to overwrite the backup.

## Protocol and operations

Connect to `/ws/alerts?protocol=2`. All messages contain `protocol_version: 2` and `type`. The first message must be `authenticate` with `installation_id` and `token` within ten seconds. No credential is sent in URLs or diagnostic traces. Incoming controls are capped at 16 KiB after decoding; also configure the ASGI server's WebSocket frame-size limit for transport-level resource protection.

Server `connected` returns `instance`, `high_water`, and `recovery_cursor`. The client takes the minimum of its completed-page cursor and the server recovery cursor, which precedes the earliest recent unconfirmed critical event for that installation. This revisits unresolved emergencies even when their original page was completed. Client `replay_request` supplies that instance and a nonnegative cursor. `alert` carries original `event`, UUID, sequence, persistence time, `delivery_mode` and `present`. `replay_complete` carries cursor, high-water, instance and `more`; clients request the next page when needed. Acknowledgements carry UUID and sequence. `ack_committed` echoes their kind only after database commit. `heartbeat`/`heartbeat_ack` use a matching nonce. Unknown versions/types, oversized controls, wrong event/sequence pairs and claimed acknowledgement identities close the session. Database clear rotates the instance identifier; instance changes or a cursor beyond the advertised boundary reset discovery while retaining local UUID dispositions.

Pair each phone using **Connection → Pair reliable alert delivery**. Copy its installation ID to the Pi administrator. On the Pi, run:

```sh
python raspberry_pi/scripts/provision_caregiver.py --installation PHONE_ID --file /secure/path/caregivers.json
```

Enter the generated secret on that phone, save, and reconnect. Set `PROJECT_PI_CAREGIVER_CREDENTIALS` to the verifier file path in the backend environment. Restrict the file to the backend account. Remove an installation's verifier to prevent future authentication; disconnect/restart the backend to terminate an already authenticated session. Provisioning refuses to replace an existing verifier implicitly. The app uses the existing local `ws://` connection configuration: credentials are not protected against network interception on an untrusted network. Use a trusted isolated network for development; protected transport deployment remains a release requirement. Fresh installations may use legacy best-effort delivery. Once any endpoint is paired, an installation-level secure-storage marker requires reliable delivery independently of hostname. Missing credentials for a changed endpoint block connection and show a reconfiguration state. Pre-marker installations migrate by detecting any saved endpoint credential. Re-pair via the existing pairing dialog, or deliberately unpair via the administrator action requiring an existing pairing secret. Interrupted pairing/unpair writes leave the marker enabled; legacy mode is permitted only after all token deletions and the final explicit unpair write succeed. Backend revocation is still a separate administrator operation.

## Migration and rollback

Before running the new backend on a real database, create a consistent backup:

```sh
python raspberry_pi/scripts/backup_alerts.py /path/alerts.db /path/alerts-before-phase3.db
```

The helper uses SQLite's backup API, includes committed WAL contents, checks integrity and refuses to overwrite a destination. On Linux/POSIX, prepare an owner-only backup directory (for example `install -d -m 700 /secure/backup-directory`). The helper rejects a destination directory not owned by the effective user or accessible to group/others, and creates each backup with explicit 0600 permissions even under a permissive umask. It does not silently change directory permissions. Windows operators must restrict destination directory ACLs separately. Startup migrates in a transaction. Legacy IDs and rows remain intact; unknown historical UUIDs and decision factors are not fabricated. The migration test starts with legacy row ID 8 and confirms the next new sequence is 9.

Stop the backend before rollback. The Phase 2 code can read the additive schema, but its new writes lack version 2 UUID/envelope data and cannot participate in durable recovery. To restore the backup instead, explicitly account for all events written since backup; restoring loses those writes. Never delete live WAL/SHM files while a database is open. No automatic database pruning, dataset deletion, model changes, threshold changes or research-data modifications were made.

## Remaining limits

- A crash after committing presentation intent but before invoking the overlay leaves an uncertain attempt. Restart recovery may retry it within the five-minute window unless explicitly confirmed. Receipt, intent, processed presentation, current active state and human confirmation are separate. There is no exactly-once physical-output guarantee.
- Dart timeouts cannot forcibly cancel an already submitted native operation. Generation checks prevent later Dart stages, and cleanup is attempted, but a permanently wedged native plugin or OS can still defeat physical output or cleanup. Device tests remain required.
- Flush-backed JSON snapshots are not a power-loss-certified mobile database. There is no automatic inbox retention; large histories increase disk use and snapshot write cost. Corrupt snapshots and exhausted storage are reported rather than acknowledged as received.
- Legacy rows, legacy unpaired clients, and legacy manual callers without producer IDs retain their compatibility limits. New manual calls accept an optional event ID for callers to reuse on retries; there is no Resident offline submission queue in this phase.
- The protocol does not guarantee notification delivery while Android has killed the app. No background-service or push-notification redesign was included. App-level presentation acknowledgements do not prove visibility, sound, vibration or human action.
- Tests do not measure physical end-to-end latency, Pi SD-card durability, TLS deployment, Android secure-storage integration, or Wi-Fi recovery on hardware. Use `phase2_physical_baseline_worksheet.md` to record those results before release.

The Phase 3 review explicitly authorizes publishing a separate review branch and PR. Direct updates to origin/main and merging remain unapproved. Physical Pi/Android testing remains NOT RUN.


## Review corrections and threat model

The review's required restart behavior supersedes the earlier blanket suppression of previously presented events. The server's eligibility check now depends on critical classification, the inclusive 0–300-second server-clock window, and absence of user confirmation. A deterministic clock is injectable for tests. Presentation timestamps remain audit evidence, not resolution. Recovery discovery rewinds independently of delivery receipt.

The client persists intent without marking processing complete. Only after the presentation callback returns does it persist the processed disposition and enqueue `ack_presented`, and only if the callback reports that this event became the provider's active overlay state. Thus intent alone never sends a presentation acknowledgement. This is app-state presentation evidence, not proof that an Android frame was visible or outputs physically worked. Explicit dismissal separately persists `user_confirmed` and its outbox entry; acknowledgement removal does not remove that durable fact.

Failed snapshot writes restore the last committed in-memory state and propagate the error, so an unsuccessful receipt write cannot send `ack_received`. Interrupted acknowledgement-removal writes restore the pending acknowledgement for retry. The two snapshot slots allow a partial newest write to fall back to the preceding parseable snapshot; corruption of both fails closed. This is still not a transactional or power-loss-certified database. Loss/corruption of the latest confirmation before it reaches the server may lose that local evidence; backup redundancy and a transactional inbox remain deployment follow-up work.

Credentials are random per installation, kept in Android platform secure storage and represented by a SHA-256 verifier on the Pi. This protects against casual file disclosure of plaintext credentials and cross-installation acknowledgement claims; it does not protect a compromised endpoint or transport. Current `ws://` exposes the bearer secret and alert content to network observers and modification to active attackers. Deployment outside an isolated controlled development network requires authenticated `wss://` with certificate/hostname validation (no accept-all certificate callback), secure provisioning, protected verifier-file access, credential revocation, and equivalent protection for HTTP management/event endpoints. TLS is not implemented or certified by these corrections. Revocation takes effect on subsequent authentication; terminate existing sessions when revoking. Retention remains disabled: monitor Pi and phone free disk space, alert operators before exhaustion, back up before any approved pruning, and never silently drop unresolved records. No automatic deletion is authorized.

Regression evidence added for intent-crash restart, previously presented/unconfirmed restart, active reconnect and replay/live duplicate suppression, explicit confirmation before server commit, expiry, independent phones, interrupted server acknowledgement commit, interrupted client acknowledgement removal, malformed acknowledgement and duplicate session rejection, partial/corrupt snapshots, and injected full storage. Server expiry tests use fixed offsets of 120 and 301 seconds instead of sleeping; native/storage failure tests inject deterministic failures.


Credential audit: tracked filenames contained no generated `caregivers.json`/`credentials.json`, mobile inbox snapshots, PEM/key files; the tracked-content scan found no GitHub token/private-key patterns. The source contains only explicit test credentials, secure-storage key names and provisioning logic. No provisioning command was run for a real phone. `.cursor/` remains excluded. This is a scoped source audit, not a claim that arbitrary secrets can always be detected automatically.


## Review branch changed-file list

Compared with the approved Phase 2 baseline; includes the original Phase 3 commits and review corrections.

- `docs/phase2_physical_baseline_worksheet.md`
- `docs/phase3_delivery_design.md`
- `docs/phase3_implementation_report.md`
- `lib/providers/alerts_provider.dart`
- `lib/screens/connection_status_screen.dart`
- `lib/services/alert_delivery_service.dart`
- `lib/services/alert_runtime_service.dart`
- `lib/services/reconnecting_web_socket_service.dart`
- `lib/services/resident_alert_service.dart`
- `pubspec.lock`
- `pubspec.yaml`
- `raspberry_pi/alert_delivery.py`
- `raspberry_pi/backend/main.py`
- `raspberry_pi/scripts/backup_alerts.py`
- `raspberry_pi/scripts/provision_caregiver.py`
- `test/__init__.py`
- `test/alert_authority_test.dart`
- `test/alert_delivery_test.dart`
- `test/alert_recovery_failure_test.dart`
- `test/alert_runtime_execution_test.dart`
- `test/alert_socket_diagnostics_test.dart`
- `test/alert_socket_lifecycle_test.dart`
- `test/requirements-delivery.txt`
- `test/resident_app_test.dart`
- `test/test_alert_delivery.py`
- `test/test_backend_alert_smoke.py`
- `test/test_delivery_integration.py`
- `test/widget_test.dart`


## PR #4 source-review follow-up

Reviewed head: `03f5793da484869dfe163b6c2c7023cf47f13209`. The follow-up preserves replay, classification, model and dataset behavior and corrects all three requested code paths:

1. A hostname/IP change cannot silently downgrade an already paired installation. A durable installation marker and explicit endpoint state block the legacy socket path; the UI offers re-pairing and deliberate administrator-secret-controlled unpairing. This is local possession-of-pairing-secret authorization, not a separate administrator-account system.
2. Audio initialization retains single-flight behavior while in progress, clears the cached Future on failure before notifying callers, and logs `audio_configuration` failure with the initiating event ID. Concurrent callers share one attempt; the next emergency may retry after a transient failure. A permanently hung native call still has the previously documented OS/plugin limitations.
3. Backups use exclusive creation with mode 0600 and validate owner-only destination directory access on POSIX. The new Linux workflow checks actual mode/ownership under umask 000, consistent contents, integrity, refusal to overwrite, shared-directory rejection and symlink destination protection.

Local regression results: full Python suite discovered 203 tests (200 passed, three Linux-only permission skips); full Flutter suite passed 69 tests. Additional tests cover the pre-marker paired-host migration, explicit re-pair/unpair, wrong administrator secret, interrupted pairing marker, audio failure then recovery, concurrent audio callers, 20 reconnects without repeating an active alarm, a 10,000-row inbox reload plus injected disk exhaustion, and storage/registry recreation during six live ASGI deliveries. The latter is an in-process backend restart simulation, not an OS process kill or physical-device trial. `ack_presented` remains app overlay-state acceptance, not physical output success, and the intent-before-callback regression remains included.

Linux permission execution completed through `.github/workflows/backup-permissions.yml` because this Windows host has no installed WSL distribution. All three tests passed on Ubuntu 24.04 in [PR workflow run 40980616360](https://github.com/kupalmananalsal-hub/Project_Pi/actions/runs/40980616360/job/123819453836), testing the PR merge ref for source head `8d48d947b5a32e1f72e0620121fb44f1ced67fe5`. The push workflow also succeeded. These are actual Linux CI results, reported separately from the Windows skips. Physical Raspberry Pi/Android results remain **NOT RUN**. Large-inbox coverage is a correctness stress test, not a mobile performance or storage-retention certification.

Exact follow-up file set:

- `.github/workflows/backup-permissions.yml`
- `docs/phase3_implementation_report.md`
- `lib/providers/alerts_provider.dart`
- `lib/screens/connection_status_screen.dart`
- `lib/services/alert_delivery_service.dart`
- `lib/services/alert_runtime_service.dart`
- `raspberry_pi/scripts/backup_alerts.py`
- `test/alert_pairing_test.dart`
- `test/alert_recovery_failure_test.dart`
- `test/alert_runtime_execution_test.dart`
- `test/test_backup_permissions.py`
- `test/test_delivery_integration.py`
