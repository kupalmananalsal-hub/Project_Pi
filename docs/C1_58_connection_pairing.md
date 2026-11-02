# C1.58 — IP/port-only connection and locally approved device pairing

Development base: integrated `74acc81cc69627546bf157a0db273630a2444ddd`.
Branch: `codex/c158-connection-pairing` in the existing isolated Windows build checkout.
No source was restarted from scratch. Earlier APKs/bundles and other checkouts remain preserved.

## User workflow

Both apps request only the editable Pi IP/hostname and port (default 8765).
No hotspot IP is compiled in. Enter the current address, tap Connect, compare
its displayed six-digit code and role with the Pi operator, then wait for local
approval. The apps retry while waiting and save approved device credentials in
Android secure storage. Subsequent connections authenticate automatically.

When DHCP changes the Pi address, edit the address and reconnect. Credentials
are indexed by an opaque stable Pi ID, not IP. A nonce/HMAC server-identity proof
is checked before sending a saved credential to the edited endpoint. The HTTP/WS
credential headers are scoped to the verified host and port. This proof does not
encrypt the underlying local HTTP transport or defend against a forwarding MITM;
a trusted, administrator-controlled LAN is still required.

The Pi registry directory is persistent. Do not delete/reinitialize it during an
upgrade: its identity and credentials must survive backend restarts. Revoked
credentials require a new local approval, retaining installation/inbox identity.
An unapproved or expired request never grants monitoring/control permissions.

Main keeps Monitor | History | Controls, actual alerts, replay and ACKs. Existing
caregiver installation IDs are reused. An existing legacy inbox directory is
retained during migration, and its alias is saved with the stable Pi identity so
an IP edit does not create a fresh inbox or restart presented alarms. Enrolling
an existing identity makes the registry authoritative: its older caregiver secret
cannot bypass revocation. Other legacy installations and the KWS service/admin
API token remain compatible until deliberately migrated by the operator.

Resident keeps single-tap Keyword Spotted TEST and double-tap Full Alert TEST,
unique command IDs and backend/Main acknowledgements. A long press consumes the
gesture without sending a tap or mute command. Remote hold-to-mute is unavailable
in this app release, and the backend rejects mute commands from new paired
Resident credentials, regardless of advertised legacy capability.

## Backend changes and authorization

Required backend source changes are limited to:

- `raspberry_pi/device_pairing.py`: new standard-library SQLite registry and local CLI.
- `raspberry_pi/backend/main.py`: minimal discovery/enrollment and scoped middleware.
- `raspberry_pi/alert_delivery.py`: authenticate enrolled durable identities and
  recheck authorization on heartbeat; replay, persistence, ACK and recovery logic
  are otherwise unchanged.

No KWS worker, recognition model/threshold, emergency decision policy, thermal
logic, outbox schema, deployed service, Android application ID or signing config
was changed. The integrated Pi reliability implementation remains the base.

| Route | Public information / authorization |
| --- | --- |
| GET `/api/discovery` | Protocol/service tag, opaque Pi ID, setup/window availability only |
| POST `/api/pairing/request` | Bounded enrollment request; only while a LOCAL operator-opened window is active |
| POST `/api/pairing/claim` | Pending/approved result only with its random claim proof; no public list or remote approval |
| POST `/api/pairing/prove` | Nonce-bound HMAC proof, no credential disclosure |
| Existing Main REST/WebSocket routes | Automatic caregiver device bearer and device ID; normal API auth remains required |
| Existing `/api/resident/control` | Separate Resident role credential; TEST commands only; paired remote mute rejected |

Caregiver permissions include status, thermal/audio streams, history, durable
alerts, LED/noise controls, existing confirmed reboot/shutdown and manual emergency
controls, and Main TEST acknowledgement. They do not grant training/deployment,
raw keyword injection or `/api/refresh`. Resident credentials cannot read Main
status/history, invoke real alarms or act as caregiver. The existing local admin
API token retains its current service permissions and is not shown on either app.

Pairing is unavailable without an explicitly configured private directory and an
initialized registry, or when existing API authentication is open/locked.
The directory must be canonical, same service UID, mode 0700 on Linux. Registry
and approval/claim state are private; no secret is printed by the local CLI.
Opening the window does NOT approve a device. Approve the exact request and code.

Limits: local window 1–300 seconds (operator selects it), request lifetime 180
seconds, 32 concurrent requests, 128 device records, 8 invalid claim attempts,
4096-byte HTTP messages, and a bounded registry file. The claim proof is saved
before the request so a lost HTTP response can retry idempotently. Expired
requests are rejected/removed; approved credentials persist until local revocation.
These pairing lifetimes are not acoustic-mute lease defaults. No mute bound was
introduced or approved.

## Focused verification actually executed

- **48 Python checks passed, 0 failures/errors/skips**, using temporary state,
  mocked hardware, actual FastAPI ASGI clients and the existing network-disabled
  Docker image. Registry, new routes, existing delivery integration and Resident
  control regressions only; the full Python/512-test suite was NOT rerun.
- **31 focused Flutter checks passed, 0 failures/skips** across pairing, the
  Main/Resident settings, retry, durable delivery, existing pairing migration,
  Resident gestures and test control. The full Flutter suite was NOT rerun.
- `flutter analyze --no-pub`: **No issues found**.
- `flutter pub get --offline`: passed with installed packages. `crypto` 3.0.7 was
  already installed transitively; it is now a direct dependency for HMAC proofs.
- Tests additionally reproduced and fixed legacy-secret revocation bypass,
  lost enrollment response recovery, wrong-role grants, IP/server-proof mismatch,
  concurrent installation creation and preservation of legacy inbox identity.

No physical hotspot/phone/Pi pairing, recognition inference, production database,
restricted recordings, real alarms, app installation or backend deployment ran.
Software fixtures do not certify physical connectivity or emergency performance.

## Build and artifacts

Build existing flavors with the same Android signing key:

```powershell
flutter pub get --offline
$env:JAVA_TOOL_OPTIONS='-Djdk.net.unixdomain.tmpdir=C:\Temp\ProjectPiC158'
flutter build apk --release --no-pub --flavor caregiver -t lib/main.dart
flutter build apk --release --no-pub --flavor resident -t lib/main_resident.dart
```

Application IDs remain `com.projectpi.thermalalert` and
`com.projectpi.thermalalert.resident`. Both retain the existing Android Debug
release-mode signing configuration, version 1.0.0+1. Expected certificate SHA-256:
`7276f472aaef988c4112c54b5ef6d5487e532bdfab9e7f9c66612a053b9b310c`.
They are development APKs, not production-signed/certified releases. The existing
future Kotlin Gradle Plugin compatibility warning remains.

The external handoff manifest records final commit, exact APK filenames, sizes,
SHA-256 hashes, signer verification, source bundle hash and build logs. Previous
74acc81 APKs are preserved. No GitHub push, PR, merge or deployment is automatic.

## Pi integration and deployment procedure — NOT executed

These commands are a handoff for a later explicitly authorized operator session.
Do not run them from the parent `/home/thesis` Git repository. Production is
`/home/thesis/Project_Pi`; the existing offline worktree is
`/var/tmp/Project_Pi_C1_43_alarm_fix`. Neither is an import/overwrite target.

1. Transfer the new source bundle/manifest to the incoming backup area using the
   Pi's currently verified address. Check its recorded SHA-256. Clone it into a
   NEW isolated directory, retaining all current offline files/stashes:

```bash
# Set these from the external handoff manifest, not a guessed branch/IP.
bundle=/home/thesis/offline-work-backups/incoming/Project_Pi-C158-connection-pairing.bundle
reviewed=REPLACE_WITH_FULL_REVIEWED_COMMIT
stage=$(mktemp -d /var/tmp/Project_Pi_C158_pairing.XXXXXX)
git clone --no-checkout "$bundle" "$stage/source"
git -C "$stage/source" checkout --detach "$reviewed"
test "$(git -C "$stage/source" rev-parse HEAD)" = "$reviewed"
git -C "$stage/source" diff 74acc81cc69627546bf157a0db273630a2444ddd "$reviewed" -- raspberry_pi
```

2. Review against any additional uncommitted Pi reliability work. Snapshot those
   changes privately before integration. Do not copy Windows files over a dirty
   Pi checkout. Focused tests are supplied, not authorization to acquire hardware.
   Obtain independent source review and deployment/rollback approval.

3. After that approval, use the existing `docs/m1_m2_upgrade_and_rollback.md`
   backup/inventory/switch process for the exact reviewed commit. Preserve models,
   datasets, SQLite history, outboxes, `/etc/project-pi/backend.env`, credentials
   and device-specific overrides. Do not use reset/clean, an unreviewed install
   script, or a blanket file copy. This task did not execute a production switch.

4. Configure the private pairing registry for the backend's existing `thesis`
   service identity, not as an owner-writable public directory:

```bash
# AFTER explicit device/configuration approval; use the reviewed source checkout.
sudo install -d -m 0700 -o thesis -g audio /var/lib/project-pi/pairing
# Run as thesis, with Python from the existing backend environment:
/home/thesis/thermal-env-sys/bin/python "$stage/source/raspberry_pi/device_pairing.py" \
  --directory /var/lib/project-pi/pairing init
sudoedit /etc/project-pi/backend.env
```

Keep the existing private API token/auth/caregiver settings. Add exactly:

```text
PROJECT_PI_PAIRING_DIR=/var/lib/project-pi/pairing
PROJECT_PI_RESIDENT_TEST_MODE=1
PROJECT_PI_REMOTE_MUTE_ENABLED=0
```

`PROJECT_PI_RESIDENT_TEST_MODE=1` is for authorized development TEST controls only.
Keep `PROJECT_PI_API_AUTH=required`; do not use open mode as a setup shortcut.
Do not set a mute lease or enable mute. The existing service already reads this
protected environment file. Review effective permissions and the selected code
path. A backend restart is needed to pick up the new source/environment, but
**must not happen until the reviewed switch/rollback and service-control action
are separately authorized**. No KWS/model/service config edit is needed for pairing.

5. Once the approved backend is running, authorize each app locally:

```bash
pair_cli="$stage/source/raspberry_pi/device_pairing.py"
py=/home/thesis/thermal-env-sys/bin/python
pair_dir=/var/lib/project-pi/pairing
"$py" "$pair_cli" --directory "$pair_dir" open --seconds 120
# App user: enter current Pi address/8765, then tap Connect.
"$py" "$pair_cli" --directory "$pair_dir" list
# Compare role, installation/request ID and six-digit code with THAT phone.
"$py" "$pair_cli" --directory "$pair_dir" approve \
  --request EXACT_REQUEST_ID_FROM_LIST --code EXACT_SIX_DIGIT_PHONE_CODE
```

Repeat for the other role/phone. Neither app types a token or device ID. `list`
shows pending requests, never credentials. Wrong code, expired window/request or
capacity exhaustion fails closed. Do not approve an unexpected role/request.

Local revocation, when authorized:

```bash
"$py" "$pair_cli" --directory "$pair_dir" revoke --device EXACT_DEVICE_ID
```

New REST requests are rejected immediately; an existing durable alert session
rechecks on its next heartbeat. Reapproval uses a new local window and code,
preserving device/inbox identity. Back up the private registry together with
existing alert data for rollback; never transfer it to Git or a public artifact.

6. Install the supplied matching APKs only after backend readiness and separate
   installation authorization. Compare package IDs/signers before an update.
   Verify both roles, notification permissions, real alert delivery/replay/ACK,
   TEST accept/present/user-acknowledged status, disconnect/reconnect, and changing
   the Pi address without re-pairing. Hold-to-mute must remain disabled.

## Remaining limitations / integration blockers

The updated Pi backend must be reviewed, integrated and configured before these
APKs can pair with it; the old backend cannot issue the new credentials. No
physical three-device reachability, DHCP/mDNS, Android lifecycle, radio recovery,
siren or vibration claim is made. Lost-registry recovery needs a restored registry
or an explicit new operator-approved enrollment; never silently regenerate identity.
Use a controlled trusted LAN: local HTTP/WS remains unencrypted. The proof limits
credential exposure to an arbitrary edited address but is not TLS/PKI. Operator
approval must include comparing the phone's code and role to the local request.

No production deployment, merge, push or PR was performed. A Draft PR remains
pending explicit push authorization under this task's no-automatic-push rule.
