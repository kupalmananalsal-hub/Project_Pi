# C1.58 backend / KWS integration gates

Development source only. No Pi file, service, device, credential, or production
database was accessed or changed. Integrate only after reviewing the actual
unmerged Pi reliability work and a backup/rollback plan.

## Required configuration

| Setting | Default / requirement |
| --- | --- |
| `PROJECT_PI_API_AUTH` | Existing backend must be in valid `required` mode; never enable controls in open/locked mode |
| `PROJECT_PI_API_TOKEN` | Existing private Main/admin API token; never share with Resident |
| `PROJECT_PI_RESIDENT_TEST_MODE` | Absent/off by default; exact `1` enables authenticated development TEST controls |
| `PROJECT_PI_RESIDENT_CREDENTIALS` | No default; separate private JSON of anonymous ID → SHA-256 secret verifier |
| `WEB_CONCURRENCY` | Exactly one backend process; known configured values other than `1` disable TEST mode |
| `PROJECT_PI_REMOTE_MUTE_ENABLED` | Absent/off by default; exact `1` additionally required in backend and KWS |
| `PROJECT_PI_REMOTE_MUTE_MAX_SECONDS` | **[REQUIRES SAFETY APPROVAL]** — no production default, not configured by this implementation |
| `PROJECT_PI_REMOTE_MUTE_DIR` | No default; pre-created canonical private IPC directory, same service UID, mode 0700 on Linux |

Until safety approval, leave remote mute disabled and its duration unset. Missing,
empty, zero, negative, nonnumeric or nonfinite durations fail closed. Fixture-only
three-second durations in unit tests are not production defaults. TEST events can
be enabled with scoped credentials independently of mute. The backend advertises
`remote_mute_available=false` when configuration, pairing, fresh worker contact,
directory safety, or local authorization is missing.

Run exactly one KWS capture owner and one backend worker. The control plane is
not a multiprocess lease coordinator. `WEB_CONCURRENCY` catches explicit common
misconfiguration; it cannot discover every externally launched extra process.
Deployment review must verify actual process ownership. No service file changed.

## Protocol and state

Resident sends a scoped bearer and `X-Resident-Id` to POST
`/api/resident/control`. It obtains a new session, then uses command UUIDs and
increasing sequences for `keyword_test`, `full_test`, `mute_start`, `mute_renew`,
`mute_end`, and `disconnect`. Heartbeats are authenticated; stale sessions cannot
renew and reconnect never restores a hold. Main's existing admin bearer accesses
GET/POST `/api/resident/main`; Resident secrets cannot access Main or real alarms.

The backend publishes fixed `request.json` inside the configured private directory;
KWS publishes fixed `ack.json` there. Writes are atomic, regular files are bounded,
links/unsafe paths are rejected, and no directory is automatically created. IPC is
a trusted same-UID local boundary, not protection against a compromised backend,
KWS account, root, or other process with that private-directory access.

The lease binds backend boot, client session, worker UUID, lease ID and monotonic
expiry. KWS checks independently every capture boundary. Its actual acknowledgement
is separate from request receipt and is invalidated by lease expiry, restart,
worker replacement, or stale/missing acknowledgement. Main/Resident expire displayed
acknowledgements using the remaining lease/freshness lifetime minus request RTT.

Mute transitions serialize against recognition, clear fallback queues, reset
openWakeWord/Vosk/Snowboy history, fence packet/candidate epochs and discard the
transition frame. Muted capture drains input without recognition or noise learning.
Unapproved delayed Snowboy candidates are cancelled; already-authorized poster
outboxes are never cleared. Thermal, manual panic, real SQLite history, replay,
acknowledgements and notification sirens retain their original authority paths.
Offline replay explicitly forces this optional IPC feature off and restores its
caller's environment afterward.

## Override and failures

Main exposes “Disable remote recognition mute” in the authenticated TEST controls.
It releases the request and writes `remote-mute.disabled`. An administrator can
also create that file locally in the private IPC directory. It blocks KWS mute
even if the backend still requests it. Re-enabling requires local review/removal
of the override and backend restart; Resident cannot enable it remotely.

Release/cancellation/backgrounding attempts immediate release/disconnect. Failed
delivery is bounded by KWS's monotonic lease expiry after the last renewal.
Backend restart writes an inactive request. KWS restart changes worker identity
and cannot restore the previous mute. Invalid/unavailable IPC fails unmuted;
clients show unavailable/unknown rather than pretending acknowledgement.

The lease is renewable while an authenticated hold remains active. There is no
invented cumulative production hold threshold. The persistent visible local
override must remain usable during operations. Native engine/capture/reset stalls,
latency, permissions and performance still need controlled physical verification;
fixture-clock tests do not certify a hard real-time bound.

## Verification and release blockers

See `C1_58_resident_main_app_compatibility.md` for actual test results and the
three-device procedure. New tests use temporary files, synthetic engines, mocked
hardware and isolated FastAPI clients only. Existing real-alert authority/durable
delivery tests remain part of the full regression suite.

Blockers: independent source review, reconcile unmerged Pi work, approve the lease
**[REQUIRES SAFETY APPROVAL]**, review private same-UID IPC/service sandboxes and
single-process ownership, physically verify stop/resume and network recovery,
review transport security and production signing, and obtain explicit deployment
authorization. No remote mute production activation is authorized here.
