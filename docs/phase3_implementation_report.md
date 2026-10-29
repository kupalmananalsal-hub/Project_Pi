# Phase 3 implementation report

Date: 2026-10-30 (Asia/Manila). Baseline: `cf9fd0e8817094617ea1f38ff05e25156c8e720f`.

Implementation commits (local, not pushed):

- Backend: `4fa21c51c7213e4e1b3d8b1667727ccfdf0f9007`.
- Flutter: `2b7f004e2ec8939a49a2176e1932f1d264bd02fc`.

The user explicitly authorized development before device testing and approved recovery of unresolved critical events up to five minutes old, without restarting an event already presented on that installation. Physical Raspberry Pi 5 and Android validation is still required before release. No physical devices were tested for this report.

## Delivered behavior

SQLite retains event IDs, complete classified envelopes, schema version, persistence timestamps and request fingerprints. Existing AUTOINCREMENT IDs are the server sequence. Migration adds nullable columns and tables without replacing legacy rows. A partial unique index protects new event IDs. WAL and an immediate insert transaction prevent duplicate rows across independent connections. Retry lookup precedes thermal reclassification; a changed request under the same ID returns HTTP 409. Manual alert submissions now accept producer IDs. Existing REST history fields and the legacy WebSocket stream remain available.

Version 2 WebSocket delivery reads durable database rows rather than depending on the lossy publication queue. Recovery uses ascending sequences and pages of at most 100, with a fixed initial high-water boundary. Once recovery finishes, a 250 ms poll offers new rows as live events. A persistence-before-publication crash therefore does not require another publication to recover the event. Suppressed/advisory/live confirmed/live critical classification behavior remains under the existing provider policy.

Per-installation delivery records distinguish offered, received, presented and user-confirmed timestamps. The paired phone authenticates with its own secret; the backend stores only SHA-256 verifiers. Identity comes from that session, not acknowledgement payloads. Acknowledgements validate UUID, sequence and prior offer, and repeat acknowledgements retain their first timestamp. A server send alone does not mark receipt.

Flutter stores credentials through platform secure storage. Its inbox and acknowledgement outbox use alternating, flushed JSON snapshots in application support storage. Processing is serialized; receipt is persisted before acknowledgement, and presentation intent before output execution. A completed-page cursor is saved only after all preceding event dispositions, so an interrupted page is replayed. Duplicate UUIDs do not restart outputs. Uncommitted acknowledgements resend on reconnect. Explicit dismissal sends user confirmation; disposal and network cleanup do not.

Only a replayed `critical` event aged 0–300 seconds by the server persistence clock, with neither presentation nor user confirmation recorded for that phone, is eligible for emergency presentation. Other recovery events are history-only. Local durable dispositions also suppress repeats when an acknowledgement was lost. Freshness expires automatic presentation, not event storage. No retention deletion was enabled.

Socket readiness is bounded at 10 seconds, reconnect backoff at 2–30 seconds and teardown attempts at 2 seconds. Generations invalidate stale callbacks. The server sends a heartbeat every 15 seconds and requires its nonce within 10 seconds; the client watchdog reconnects after 35 seconds without protocol traffic. An already-active installation session is rejected; cancellation now removes the session before awaited cleanup.

Emergency stop invalidates startup immediately and runs independently of pending start Futures. Native operations have five-second bounds and generation checks between asynchronous preparation steps. Audio session configuration is shared and awaited by the audio path, independently of notification permissions. Late notification completions cancel their own generation-specific notification; late vibration completions attempt cancellation when no emergency remains active. Authoritative thermal labels use event-associated backend evidence, and no unrelated local frame is attached to the emergency overlay.

## Verification

Tests ran on the Windows development host. Python integration uses real FastAPI HTTP/WebSocket routing and temporary SQLite databases; sensor and ML imports are stubbed. Flutter tests use fake native outputs. These are software results, not hardware or acoustic-accuracy measurements.

| Check | Result |
| --- | --- |
| Complete Python suite, including ASGI integration | 195 passed, 9.209 seconds in the recorded run |
| Complete Flutter suite | 54 passed, 13 seconds in the recorded run |
| Dart analysis | No issues found |
| Final targeted delivery/runtime regression after acknowledgement batching change | 5 passed |
| Dart formatting, changed sources/tests | 13 files checked; 0 changes |
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

The base Python environment lacks FastAPI/HTTPX; integration tests explicitly skip there. The recorded 195-test run used the provisioned environment and had no skips. The first analyzer run failed on its shared Windows performance-cache directory; the successful run set LOCALAPPDATA to the ignored `build/phase3-local` directory. Initial integration failures exposed cancellation cleanup and test-loader registration issues, both repaired. The widget smoke test now pumps teardown so bounded cleanup timers can finish.

### Reproduced event traces

The ASGI tests assert IDs, decisions and acknowledgement state rather than treating trace counts as delivery proof. The local execution log is `build/phase3-python.log` (ignored generated output).

| Event ID | Verified sequence and last successful stage |
| --- | --- |
| `integration-critical` | POST → backend critical/manual classification → SQLite sequence 1 → phone-a replay send → `ack_received` committed → `ack_presented` committed → store/registry restart → same-ID POST returns original record → phone-a replay has `present=false` → phone-b replay has `present=true`. Last stage: independent replay classification; no physical output claim. |
| `missed-0`, `missed-1`, `missed-2` | Phone disconnects → POST/persist with no subscriber → reconnect → all three original IDs delivered in order → replay complete. Last stage: replay completion. |
| `two-live` | Two authenticated phones connected → POST/persist → both receive live event → phone-a receipt committed, phone-b receipt remains unset. Last stage: per-phone acknowledgement persistence. |
| `overflow-0` through `overflow-104` | 105 POSTs persist → legacy queue holds only 100 → version 2 replay retrieves all 105 in pages of 100 and 5. Last stage: durable recovery completion. |
| `spoof-target` | POST/persist → phone-a offer → acknowledgement claiming phone-b rejected → phone-b receipt remains unset. Last stage: offer/send; failure at acknowledgement validation. |
| Flutter `recent`, `old` | `recent` presents once, duplicates and process-style inbox reload do not repeat output; `old` is history-only. Last stage: client disposition/outbox persistence using a fake output callback. |
| Flutter `stalled` | Notification/preparation Futures held unresolved → dismissal completes → late preparation cannot invoke playback → later emergency starts. Last stage: runtime execution with fake plugins. |
| Flutter `stale-local` | Earlier local human-positive state → authoritative critical/negative event → emergency activates with human label false and no local thermal frame. Last stage: provider state. |

Additional tests cover legacy migration, concurrent duplicate inserts, fingerprint conflicts, request bounds, unoffered and mismatched acknowledgements, 300-second expiration boundaries, heartbeat timeout/reconnect and stalled readiness teardown. The existing publication, authority, detector and training regressions remain included.

The backup test keeps a WAL-mode source connection open, commits a marker, invokes the backup helper, verifies that marker and the complete envelope in the restored database, and verifies that a second invocation refuses to overwrite the backup.

## Protocol and operations

Connect to `/ws/alerts?protocol=2`. All messages contain `protocol_version: 2` and `type`. The first message must be `authenticate` with `installation_id` and `token` within ten seconds. No credential is sent in URLs or diagnostic traces. Incoming controls are capped at 16 KiB after decoding; also configure the ASGI server's WebSocket frame-size limit for transport-level resource protection.

Server `connected` returns `instance` and `high_water`. Client `replay_request` supplies that instance and a nonnegative cursor. `alert` carries original `event`, UUID, sequence, persistence time, `delivery_mode` and `present`. `replay_complete` carries cursor, high-water, instance and `more`; clients request the next page when needed. Acknowledgements carry UUID and sequence. `ack_committed` echoes their kind only after database commit. `heartbeat`/`heartbeat_ack` use a matching nonce. Unknown versions/types, oversized controls, wrong event/sequence pairs and claimed acknowledgement identities close the session. Database clear rotates the instance identifier; instance changes or a cursor beyond the advertised boundary reset discovery while retaining local UUID dispositions.

Pair each phone using **Connection → Pair reliable alert delivery**. Copy its installation ID to the Pi administrator. On the Pi, run:

```sh
python raspberry_pi/scripts/provision_caregiver.py --installation PHONE_ID --file /secure/path/caregivers.json
```

Enter the generated secret on that phone, save, and reconnect. Set `PROJECT_PI_CAREGIVER_CREDENTIALS` to the verifier file path in the backend environment. Restrict the file to the backend account. Remove an installation's verifier to prevent future authentication; disconnect/restart the backend to terminate an already authenticated session. Provisioning refuses to replace an existing verifier implicitly. The app uses the existing local `ws://` connection configuration: credentials are not protected against network interception on an untrusted network. Use a trusted isolated network for development; protected transport deployment remains a release requirement. Unpaired phones remain legacy best-effort clients; no automatic downgrade occurs after a paired version 2 setup failure.

## Migration and rollback

Before running the new backend on a real database, create a consistent backup:

```sh
python raspberry_pi/scripts/backup_alerts.py /path/alerts.db /path/alerts-before-phase3.db
```

The helper uses SQLite's backup API, includes committed WAL contents, checks integrity and refuses to overwrite a destination. Startup migrates in a transaction. Legacy IDs and rows remain intact; unknown historical UUIDs and decision factors are not fabricated. The migration test starts with legacy row ID 8 and confirms the next new sequence is 9.

Stop the backend before rollback. The Phase 2 code can read the additive schema, but its new writes lack version 2 UUID/envelope data and cannot participate in durable recovery. To restore the backup instead, explicitly account for all events written since backup; restoring loses those writes. Never delete live WAL/SHM files while a database is open. No automatic database pruning, dataset deletion, model changes, threshold changes or research-data modifications were made.

## Remaining limits

- A crash after committing presentation intent but before invoking the overlay leaves an uncertain attempt. It is conservatively kept silent on duplicate replay rather than claiming exactly-once physical presentation. Receipt, intent, app presentation and human confirmation remain different evidence.
- Dart timeouts cannot forcibly cancel an already submitted native operation. Generation checks prevent later Dart stages, and cleanup is attempted, but a permanently wedged native plugin or OS can still defeat physical output or cleanup. Device tests remain required.
- Flush-backed JSON snapshots are not a power-loss-certified mobile database. There is no automatic inbox retention; large histories increase disk use and snapshot write cost. Corrupt snapshots and exhausted storage are reported rather than acknowledged as received.
- Legacy rows, legacy unpaired clients, and legacy manual callers without producer IDs retain their compatibility limits. New manual calls accept an optional event ID for callers to reuse on retries; there is no Resident offline submission queue in this phase.
- The protocol does not guarantee notification delivery while Android has killed the app. No background-service or push-notification redesign was included. App-level presentation acknowledgements do not prove visibility, sound, vibration or human action.
- Tests do not measure physical end-to-end latency, Pi SD-card durability, TLS deployment, Android secure-storage integration, or Wi-Fi recovery on hardware. Use `phase2_physical_baseline_worksheet.md` to record those results before release.

No Phase 3 push is covered by the earlier exact-commit Phase 2 approval. These changes are prepared for source review as a development milestone.
