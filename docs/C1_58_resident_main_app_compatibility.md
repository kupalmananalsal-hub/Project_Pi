# C1.58 — Main / Resident interoperability development handoff

Date: 2026-11-02. Development only; no physical-device certification or deployment.

## Source and baseline

Both applications are Flutter applications in this repository:

- Main: `lib/main.dart`, `lib/screens/app_shell.dart`.
- Resident: `lib/main_resident.dart`, `lib/screens/resident_mode_screen.dart`.
- Android: `android/app/build.gradle.kts`, `android/app/src/main/AndroidManifest.xml`.
- Authoritative development backend: `raspberry_pi/backend/main.py`.
- Acoustic capture and recognition: `raspberry_pi/kws/kws_alert_dual.py`.

Branch: `codex/c158-resident-interoperability`, created from clean local UI commit
`3921112b4365732e5d3bb461b2a382d5c905091a`. Cached `origin/main` was
`b6a2a20ded8df62cefb7ef6616710cbfdca140cf`; no fetch, pull, or overwrite occurred.
The previous UI branch remains preserved. The live Pi's reported 351-test,
unmerged reliability work was not accessed and cannot be assumed identical.

## Findings and chosen connection design

Verified source defects/incompatibilities:

1. Both entry points shared one Android application ID. Installing the other
   build could replace the existing app. Caregiver now retains
   `com.projectpi.thermalalert`; Resident uses `com.projectpi.thermalalert.resident`.
2. Resident gestures called the genuine `/api/alerts/manual` endpoint; this was
   not a TEST protocol. There was no recognition-mute API or KWS acknowledgement.
3. Resident only interpreted HTTP success as success, without Main presentation
   acknowledgement, scoped pairing, or lifecycle-controlled mute state.
4. Host/port normalization already existed. A stale DHCP address, mDNS failure,
   hotspot client isolation, or Android routing failure is **not established**
   from these source files and has not been physically diagnosed.

Both apps use the Pi's configurable host and port, normally 8765. Main uses its
existing REST/WebSocket monitoring and reliable alert delivery; Resident uses
authenticated local HTTP control polling. No internet or Phone 1 relay is required
by this source design. Reachability on the actual hotspot remains unverified;
there is no evidence authorizing a speculative relay implementation.

## Endpoints, pairing, and event identity

| Route | Role / authentication | Purpose |
| --- | --- | --- |
| Existing `/api/`, `/ws/thermal`, `/ws/audio` | Existing Main API bearer | Monitoring, preserved |
| Existing `/ws/alerts?protocol=2` | Existing per-installation caregiver secret | Real alerts, durable replay/ACKs, preserved |
| Existing `/api/alerts/manual` | Existing Main API bearer | Genuine legacy manual alert, preserved; no longer called by the Resident TEST button |
| POST `/api/resident/control` | Separate Resident bearer plus `X-Resident-Id` | Connect, heartbeat, sequenced TEST/mute commands, disconnect |
| GET `/api/resident/main` | Main API bearer | TEST state, recent Resident contact, actual KWS mute acknowledgement |
| POST `/api/resident/main` | Main API bearer | TEST presented/user acknowledgement, or local remote-mute disable |

All new routes require effective API authentication mode `required` and explicit
Resident TEST mode. Open/locked API modes never enable these controls. The exact
Resident control route authenticates its scoped credential itself; that secret
cannot call real alerts, thermal routes, or Main acknowledgement routes.

Provision a **separate**, private Resident verifier file mapping anonymous IDs to
SHA-256 verifiers. The existing administrator utility
`raspberry_pi/scripts/provision_caregiver.py --installation <32-hex-id> --file <new-private-resident-file>`
can generate the same verifier format; use a new Resident-only file and a new
random ID, never the caregiver file or a caregiver credential. This is an
instruction for a later authorized integration, not a command executed here.
Enter that ID and its generated secret in Resident Settings. Secrets are saved
in Android secure storage per normalized host and port, never in URLs or Git.

TEST events have independent `test-...` UUIDs, `is_test=true`, source
`resident_test`, command ID/sequence, backend boot ID, and creation time. Their
bounded in-memory store is separate from SQLite real history and outboxes.
It intentionally disappears on backend restart: this is not durable emergency
delivery. Session nonces and increasing sequences fence stale commands; repeated
identical command IDs are idempotent within the session, conflicting IDs fail.
Sessions cap at 16; each session caps at 300 commands; TEST events cap at 300 per
backend process. Capacity exhaustion fails closed rather than silently evicting
deduplication evidence.

Resident distinguishes backend acceptance, Main presentation, and Main user
acknowledgement. HTTP acceptance never claims a physical siren or vibration.
Connected indicators mean authenticated contact within the five-second contact
window, not proof of radio connectivity. Main renders the TEST presentation before
acknowledging it; actual TEST outputs additionally require successful authenticated
acknowledgement and explicit local Main authorization for that foreground session.

## Gestures and presentation

- Single tap: one Keyword Spotted TEST.
- Double tap: one Full Alert TEST, without a single-tap event.
- Recognized long press: request recognition mute; no tap action.
- Release, pointer cancellation, settings navigation, or backgrounding: request
  release/disconnect. Reconnect never replays a held gesture.

Flutter gesture recognizers replace the custom tap timer. The Resident screen
retains one red HELP button on black, explicit TEST instructions, connection and
acknowledgement status, pairing settings, and a scroll layout for enlarged text.
These TEST controls do not replace a real emergency call.

Main retains Monitor | History | Controls. The PART/None card, simulated distress
button, Training navigation tab, and Refresh KWS Service button remain absent.
The TEST layer is separate from real alert history/providers. Full TEST uses the
existing overlay with explicit simulation text and no fabricated detection or
thermal confidence. Audio/vibration are off until explicitly authorized locally.
Real emergencies preempt TEST output ownership; delayed TEST cleanup cannot stop
a real alarm. TEST presentation IDs are persisted before presentation on the same
installation, preventing reconnect/restart from restarting a presented test siren.
Its 4096-ID storage capacity fails closed. Test-channel loss or Main backgrounding
stops only TEST outputs; real monitoring/alerts retain their existing paths.

## Remote mute safety

**Remote mute is disabled by default. Maximum lease: [REQUIRES SAFETY APPROVAL].**
There is no production duration default. Missing, zero, negative, nonfinite, or
malformed duration leaves remote mute unavailable. TEST events work independently.
See `C1_58_backend_integration_report.md` for all gates and IPC preconditions.

The backend owns a lease addressed to one KWS worker UUID, backend boot, Resident
session, and lease ID. The worker acknowledges actual gating only at capture
boundaries, after serializing with fallback recognition, draining queues,
discarding the boundary frame, resetting recognition history, and cancelling
unapproved delayed candidates. No service restart occurs per hold. While muted,
capture is drained but PCM is not fed to openWakeWord, Vosk, Snowboy, the verifier,
or noise-profile learning. On resume, model state and packet epochs prevent old
audio/candidates from surfacing as fresh detections. Already-authorized outbox
events and thermal/manual/backend delivery are independent and remain untouched.

Renewals require a live authenticated session and the exact active lease; an
expired/released hold cannot renew. Reconnect invalidates the old session. Backend
restart clears its request; KWS restart changes worker identity so it cannot adopt
an old request. Worker expiry is independent of backend polling. Release loss or
network loss falls back to the explicitly configured maximum lease after the last
accepted renewal. A held gesture may renew while connected; the visible local
disable overrides further renewals. The Main control and administrator-owned
`remote-mute.disabled` file provide that override.

Neither client shows MUTED from a request acknowledgement alone. It requires a
fresh actual KWS acknowledgement and active lease. Display freshness is bounded
by the remaining lease and a two-second acknowledgement-freshness window, minus
the full request round-trip time; expiry returns the display to unknown. This
two-second display window is **not** a default mute lease. Audio frames explicitly
mark muted periods `muted_not_evidence`; the microphone card withholds live levels
and direction for those frames rather than calling them ordinary silence.

Clock-driven tests establish software behavior, not a real-time hardware bound.
Capture/model-reset/native-engine stalls and reset latency must be assessed on
the actual Pi before approving any lease or enabling the feature.

## Verification

| Check | Actual result |
| --- | --- |
| Full Python pytest suite | **399 passed, 0 failed, 0 errors, 1 skipped, 4 xfailed**; 43 additional subtests passed; 79 dependency deprecation warnings |
| Full Flutter suite | **99 passed, 0 failed, 0 skipped** |
| Dart analysis | **No issues found** |
| Synthetic rendered Main UI checks | **9 passed**; phone screenshot visually inspected |
| Windows stdlib control/worker tests | Earlier check: 18 passed, 4 skipped (optional ASGI dependencies and symlink permission); complete Linux fixtures passed in the full suite |
| Main and Resident release-mode APKs | Both built and signatures verified; development debug certificate |

Commands: `flutter doctor -v`, `flutter pub get --offline`, `flutter analyze --no-pub`,
`flutter test --no-pub --reporter expanded`, and isolated
`python -m pytest -q -p no:cacheprovider test`. Expected failures/skips are not
counted as passes. No test result represents acoustic recognition accuracy.

| Requirement | Executed software evidence |
| --- | --- |
| A–C gestures | Resident widget tests: single/double/hold, cancellation, compact enlarged-text layout |
| D actual mute acknowledgement | Control-client tests, expiring-display tests, KWS/lease fixtures |
| E release and stale audio | Lease-end tests, queue-boundary and actual fallback-worker fixture tests |
| F lost Wi-Fi | Simulated transport failure; independent worker clock expiry |
| G backgrounding | Flutter lifecycle release/disconnect tests |
| H stale commands | Backend sequence/session/lease rejection fixtures |
| I duplicate IDs | Backend command conflict/idempotency and Main persisted TEST dedup tests |
| J authorization | Actual FastAPI ASGI fixtures reject missing/wrong/scoped/open-mode credentials |
| K both phones' event state | ASGI accept/present/ack path and Main/Resident client/widget fixtures |
| L restarts | Backend and worker restart tests; client reconnect never resumes a hold |
| M thermal while muted | Actual thermal WebSocket handler exercised with mocked hardware during a fixture lease |
| N real emergencies | Genuine alert endpoint persists a critical fixture while muted; existing delivery/runtime regressions and TEST preemption |
| O replay | Existing real-alert replay/dedup suite plus TEST reconnect/restart dedup and output-ownership tests |

Python integration tests used the existing `pi9-test:local` image, no downloads,
`--network none`, a read-only source mount, and a disposable `/tmp` source copy.
Only `.sh` files and the protected-assets manifest were LF-normalized in that
temporary Linux copy; source files stayed unchanged. Tests use synthetic audio,
mocked engines/hardware/outputs, and temporary databases/IPC files. Existing
FastAPI/httpx deprecation warnings and optional/baseline expected failures are not
recognition or device evidence. No restricted audio or genuine inference ran.

## Android builds

Flutter 3.44.0 / Dart 3.12.0, existing Android SDK/build tools 36.1.0 and Java 21.
`flutter doctor -v` completed with warnings for spaces in the SDK path and missing
Windows-desktop C++ components. No Android phone/emulator was attached.
`flutter pub get --offline` succeeded from the local cache; lockfile unchanged.

```powershell
# Existing host workaround: command-local Java socket path, not a global change.
New-Item -ItemType Directory -Force C:\Temp\ProjectPiC158 | Out-Null
$env:JAVA_TOOL_OPTIONS='-Djdk.net.unixdomain.tmpdir=C:\Temp\ProjectPiC158'
flutter build apk --release --no-pub --flavor caregiver -t lib/main.dart
flutter build apk --release --no-pub --flavor resident -t lib/main_resident.dart
```

`caregiver` is the default flavor; `main` is a reserved Android source-set name.
Outputs: `build/app/outputs/flutter-apk/app-caregiver-release.apk` and
`build/app/outputs/flutter-apk/app-resident-release.apk`. The old unflavored
`app-release.apk`, if present locally, is an earlier artifact.

| APK | Bytes | SHA-256 |
| --- | --- | --- |
| Main | 56,464,069 | `43cd965970b106213ffe693f70f3cdc0bc7f45acfbf4b351ce598f4168be0c08` |
| Resident | 51,167,661 | `e4c2b5da39a38bf3cdff91f057c710b3a6936c75fa0eec1aae9fc5a3a2bddcfa` |

Both builds intentionally preserve the existing **Android Debug** signing
configuration. Verified certificate SHA-256:
`7276f472aaef988c4112c54b5ef6d5487e532bdfab9e7f9c66612a053b9b310c`.
These are development release-mode APKs, not production-signed artifacts. Build
warnings about future Kotlin Gradle Plugin compatibility remain unresolved.

## Manual three-device checks — require later explicit authorization

1. Review/integrate the backend patch against the actual uncommitted Pi work;
   back up configuration, credentials, database/outbox, models, and service state.
   Prepare rollback. Do not deploy from this report automatically.
2. Enable a secured Phone 1 hotspot; join the Pi and Phone 2. Record actual DHCP
   addresses. Check authenticated Pi HTTP reachability from **both** phones, not
   just ping. Check mDNS separately; enter the actual Pi address if it fails.
3. If reachability fails, distinguish wrong address/port, firewall, API auth, and
   hotspot client isolation before considering an authenticated relay. Sharing a
   hotspot alone proves none of these routes.
4. Connect Main to that Pi host/8765 with existing Main/API and caregiver pairing.
   Verify thermal/audio streams, durable alert link, and reconnect status.
5. In authorized development TEST mode, pair Resident with its separate ID/secret
   and the same Pi endpoint. Check both recent-contact indicators. Remote mute
   must remain unavailable with its lease configuration absent.
6. Single-tap once; verify exactly one TEST notice and its backend accepted,
   Main presented, then Main user-acknowledged states. Verify no real history row.
7. Authorize TEST outputs locally on Main, double-tap once, and check one TEST
   overlay/notification/audio/vibration. Dismiss it. Verify single-tap did not fire.
8. Only after a lease safety review and separate hardware permission, provision
   private IPC and enable the reviewed configuration. Hold with controlled test
   input: neither phone may show MUTED before KWS confirms gating. Measure the
   actual recognition stop/resume timing and model-reset latency.
9. Release, cancel a touch, navigate to settings, background/kill Resident, and
   disconnect Phone 2 Wi-Fi in separate trials. Confirm recognition resumes on
   release or within the reviewed bound after the last renewal. Reconnect while
   still touching: no automatic new lease or tap TEST may appear.
10. Exercise stale/duplicate/unauthorized commands and backend/KWS restarts in the
    isolated device test setup. Check local disable and expiry; verify older
    buffered audio never becomes a fresh detection after resume.
11. Verify thermal continues during mute, existing authorized real events remain
    deliverable, and a genuine emergency preempts TEST presentation. Such actual
    alarm tests need their own controlled authorization; software fixtures do not
    establish this physical outcome.
12. Repeat both apps' disconnect/reconnect and Main restart tests. Previously
    presented test IDs must not restart outputs. Verify genuine monitoring and
    real alert replay/ACKs afterward and archive observed evidence separately.

## Integration and remaining risks

No Pi checkout, production state, models, recognition thresholds, emergency policy,
thermal logic, services, restricted data, `PLAN.md`, `.cursor/`, or existing PR was
modified. No push, PR creation, merge, install on a phone, or deployment ran.
The branch is for independent review. The task explicitly forbids automatic
pushing, so no PR URL exists; do not create an empty or fictitious PR.

After explicit push authorization, create a Draft PR, preserving Draft PRs #11
and #12 and other work. Reconcile against the latest reviewed main/Pi reliability
changes without overwriting them, rerun these tests, and review backend startup,
single-worker ownership, private IPC permissions and service sandbox access.

Unresolved: real hotspot routing/client isolation, mDNS/DHCP changes, Android
background/doze/notification/audio/vibration behavior, native-engine reset and
capture timing, Pi performance, production signing, and the reviewed lease bound.
The existing local HTTP/WS transport is not encrypted; use only an administrator-
controlled secured test LAN. TLS/relay/transport-hardening work is not claimed.
TEST audit/dedup is intentionally bounded and ephemeral on the backend, not a
substitute for production durable alert delivery. Remote mute remains disabled.

## Exact changed files for this interoperability branch

- `android/.gitignore`
- `android/app/build.gradle.kts`
- `android/app/src/main/AndroidManifest.xml`
- `docs/C1_58_backend_integration_report.md`
- `docs/C1_58_resident_main_app_compatibility.md`
- `lib/main_resident.dart`
- `lib/models/audio_frame.dart`
- `lib/screens/app_shell.dart`
- `lib/screens/monitor_screen.dart`
- `lib/screens/resident_mode_screen.dart`
- `lib/screens/resident_settings_screen.dart`
- `lib/services/alert_runtime_service.dart`
- `lib/services/mute_acknowledgement.dart`
- `lib/services/resident_control_client.dart`
- `lib/services/resident_monitor_service.dart`
- `lib/widgets/alert_overlay.dart`
- `lib/widgets/resident_test_layer.dart`
- `pubspec.yaml`
- `raspberry_pi/backend/main.py`
- `raspberry_pi/kws/audio_preprocessor.py`
- `raspberry_pi/kws/kws_alert_dual.py`
- `raspberry_pi/kws/replay_eval.py`
- `raspberry_pi/resident_control.py`
- `test/alert_runtime_execution_test.dart`
- `test/resident_app_test.dart`
- `test/resident_control_test.dart`
- `test/resident_test_layer_test.dart`
- `test/test_remote_mute_kws.py`
- `test/test_replay_eval.py`
- `test/test_resident_control.py`

## Requested status

MAIN APP UPDATED: YES  
RESIDENT APP UPDATED: YES  
CONNECTION BUG FIXED IN SOURCE: YES — source protocol/package incompatibilities;
physical connection root cause remains unverified.  
FLUTTER TESTS PASSED: YES  
THREE-DEVICE CONNECTION VERIFIED: NO  
REMOTE MUTE VERIFIED ON REAL HARDWARE: NO  
PRODUCTION DEPLOYMENT AUTHORIZED: NO
