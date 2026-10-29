# Phase 3 delivery design

Baseline: cf9fd0e8817094617ea1f38ff05e25156c8e720f.

On 2026-10-30 the user authorized development before physical testing and approved the five-minute critical replay policy below. Raspberry Pi/Android testing remains mandatory before release. No physical results have been supplied or observed. This document records design intent; phase3_implementation_report.md specifies delivered behavior and limitations.

## Storage

Keep the existing alerts table and REST history fields. Its AUTOINCREMENT id can serve as the server sequence. Add nullable event_id, envelope_version, envelope_json, persisted_at and request_fingerprint columns transactionally. A partial unique index on non-null event_id protects new events. Legacy rows retain their IDs and remain history-only; never fabricate original producer UUIDs or unavailable decision factors.

Store the original classified envelope, preserving decision and thermal fields. Resolve retries against the persisted fingerprint before reclassification: identical requests return the original record; conflicting reuse returns 409. The transaction must ensure concurrent inserts cannot produce duplicate rows. Test restart recovery and migration from populated legacy databases using isolated temporary files.

Add per-installation acknowledgement records keyed by caregiver_id and event_id, with independent received_at, presented_at and user_confirmed_at timestamps. These acknowledgements are distinct; none implies that native outputs worked or that a person responded unless explicitly recorded as such.

## Protocol

Negotiate a versioned protocol while preserving the current legacy stream for existing clients. New clients use alert, ack_received, ack_presented, ack_user_confirmed, heartbeat, heartbeat_ack, replay_request and replay_complete messages. Alert messages carry the original UUID, sequence and classified envelope.

Generate a persistent random installation identifier. Bind it to a locally provisioned per-installation credential; an identifier alone does not authenticate acknowledgements. Validate message type, protocol version, identity, event existence and sequence association; reject oversized messages. Credential provisioning and storage must be specified before enabling authenticated acknowledgements.

Subscribe before taking the replay high-water mark, replay up to that mark in sequence order, then drain live events with UUID deduplication. Page replay in batches of 100. Use a per-installation persisted receipt cursor for discovery, while retaining separate presentation and human-confirmation states. A receipt cursor must not suppress unresolved presentation work after an application crash.

## Approved replay policy

Approved default: only unresolved critical events persisted within the preceding five minutes may activate an emergency during recovery. Previously presented events on the same installation do not automatically restart sound/vibration. Older events remain visible in history. Record receipt and presentation separately; never treat network acknowledgement as human confirmation.

Order replay by server sequence. Preserve UUIDs and decisions. Propose 30-day retention with no automatic pruning of unresolved critical events; document the disk-growth tradeoff. Expiration governs automatic presentation, not silent deletion. Unknown or expired cursors must return an explicit recovery boundary rather than claiming complete delivery.

## Reliability and verification

Use generation-guarded socket teardown, readiness and heartbeat timeouts, and one reconnect coordinator. Native stop must invalidate startup immediately and operate independently of stalled start Futures. Timeouts alone do not cancel native side effects; late completions must be guarded or followed by cleanup. Configure the audio session on the audio path before playback, independently of notification permission prompts. Use backend-associated thermal evidence for authoritative alert labels.

Test migrations, durable idempotency, two Caregivers, disconnect-before-broadcast, overflow recovery, restart during acknowledgement, replay deduplication, expiration, heartbeat loss, malformed/unauthorized messages, stalled native Futures and stale thermal UI state. Capture POST-to-acknowledgement-and-replay integration evidence separately from physical-device observations.

Before migration, make a consistent SQLite backup using its backup API, including WAL contents. Roll back application code only against a compatible additive schema, or restore that backup with the backend stopped; restoring a backup loses events written afterward and requires explicit operational approval. Do not drop legacy rows or model/research files.

## Source inspection follow-up (2026-10-30)

These are code findings, not physical observations:

- `/ws/alerts` accepts clients without credentials, sends ten reconstructed history rows, then only waits for publication queue entries. Version 2 needs concurrent receive, delivery and heartbeat handling, with coordinated cancellation on disconnect. Legacy clients must never be allowed to submit acknowledgements.
- The existing HTTP bearer-token helper protects selected management endpoints, not the alert WebSocket. Its shared default token cannot establish independent Caregiver identity. Do not reuse that default as installation authentication.
- `/api/alerts` claims event IDs in process memory before classification and database insertion. Durable lookup must precede thermal evaluation on a retry, so a restarted process returns the original decision rather than classifying the same request against a newer thermal frame.
- `/api/alerts/manual` constructs an alert without forwarding a producer event ID. Add an optional client-generated UUID while preserving compatibility with older callers. New Resident clients must reuse that UUID on retry. Older requests without UUIDs cannot promise retry deduplication.
- The generic reconnecting socket is shared infrastructure. Alert protocol heartbeats must be opt-in; do not send alert protocol messages to unrelated stream endpoints.
- A successful native plugin call proves only that the plugin accepted/completed the request. `ack_presented` must describe app presentation, with output outcomes separately recorded. Dismissal may generate `ack_user_confirmed` only from an explicit user action; reconnect, disposal and timeout cleanup must not generate it.

## Proposed protocol contract

All version 2 messages carry `protocol_version: 2` and a known `type`. An `alert` carries `event_id`, `sequence`, `persisted_at`, `delivery_mode` (`live` or `replay`) and the immutable original `event` envelope. Acknowledgements carry `event_id` and `sequence`; the server derives installation identity from the authenticated connection, never from a claimed message field. Server timestamps record acknowledgement arrival; client timestamps are optional diagnostic evidence.

`ack_received` means that the client has committed the event to local durable storage. `ack_presented` means the app committed a presentation disposition; it does not mean audible playback or vibration was physically observed. Persist channel outcomes separately. `ack_user_confirmed` records the explicit action for that event. Each transition is idempotent and must retain earlier timestamps on duplicate messages. An acknowledgement cannot refer to an event that was never offered to that installation.

Use a durable client inbox and acknowledgement outbox. Persist an incoming event before sending receipt; restore unsent acknowledgements after restart. Persist presentation intent before invoking outputs to avoid restarting an already presented alarm after a crash. There is an unavoidable crash window between committing intent and performing a native side effect: record an uncertain disposition for investigation rather than claiming exactly-once physical presentation. The approved replay policy must determine whether that uncertain disposition permits another attempt.

Discovery cursors track the highest contiguous durably received sequence, not the maximum sequence observed. Replay completion identifies its high-water mark and whether more pages remain; it never asserts human acknowledgement. Resolve incomplete presentation independently of the receipt cursor. A database-instance identifier must accompany cursors so restoring an older database cannot silently turn a previously valid cursor into a false recovery success.

Proposed bounds for implementation and tests: replay pages of 100 events, incoming control messages at most 16 KiB, handshake readiness 10 seconds, heartbeat every 15 seconds with a 10-second response deadline, reconnect backoff from 2 to 30 seconds, and teardown bounded to 2 seconds. These are development defaults, not measured device limits. Reject unknown versions, invalid types, negative/non-integer cursors, mismatched UUID/sequence pairs and oversized frames before applying state changes. Heartbeat responses must match the outstanding nonce and connection generation.

Credential proposal: provision a random per-installation secret through an administrator-controlled local setup, store only its verifier on the backend and use platform secure storage on Android. Support revocation and reject duplicate active sessions for the same installation through a documented replacement rule. Do not log credentials or place them in URLs. Remote operation requires protected transport; plaintext WebSocket credentials do not resist network interception. Provisioning, secure transport and client storage integration remain implementation work, not existing capabilities.

## Focused implementation sequence after prerequisites

1. Extract a hardware-independent persistence boundary; add legacy migration, full-envelope storage, durable idempotency and restart tests. Keep classification untouched.
2. Add authenticated version 2 sessions, acknowledgement storage and bounded replay with in-process integration tests against the real FastAPI routes and temporary SQLite databases.
3. Add the Flutter durable inbox/outbox, connection recovery and approved replay disposition; preserve legacy stream compatibility.
4. Repair native-operation cancellation and backend thermal labels, with stalled-Future and stale-evidence regression tests.
5. Run complete suites and document exact commands, results, migration/rollback exercises and remaining physical limitations. Review focused commits before requesting any new push authorization.

Implementation and measured tests are documented in phase3_implementation_report.md. The physical baseline prerequisite was explicitly deferred until before release, and the five-minute replay policy was approved. The proposed 30-day retention is not permission to delete data; default to preserving records until retention is approved.
