# C1.58 Main / Resident pairing connection-loop repair

Base: `c44d849619a769a87743f2e02492007fd77dcf31`.
Branch: `codex/c158-pairing-loop-fix`. Development-only Android release builds.

## Findings and corrections

### Verified APK packaging defect

The previously saved APKs named `Project_Pi-C158-Main-pairing-c44d849-release.apk` and `Project_Pi-C158-Resident-pairing-c44d849-release.apk` contain older pre-enrollment arm64 code: neither includes `/api/discovery` or `/api/pairing/request`; Resident still contains the old manual pairing-secret field. Their arm64 library SHA-256 values are respectively `f43811c643174bf876d156cc92db83303438751efba73a3fb8c3561da909b907` and `dacdd47e0a2fac58336c5092020b3c0a6a6b221b7f1b18c2fe251d3c45ca32ec`.

A normal rebuild reproduced the problem: current Flutter JNI outputs contained the new pairing code, but Gradle's merged/stripped JNI outputs and final APKs retained the older libraries. Build success alone was insufficient. Re-run the flavor-specific mergeJniLibFolders, mergeNativeLibs, stripDebugSymbols, and package tasks using their supported `--rerun` task option, then verify final APK contents. Originals were preserved. This directly explains absent enrollment for these local artifacts; matching the installed Phone 1 artifact still requires device verification.

### Additional source defects

Reproduced in focused synthetic tests:

- Main Settings overwrote an edited IP with the saved host after focus moved to Port and an old connection retry rebuilt the widget. Connect could consequently target the old address. Keep user edits until explicitly submitted.
- A protected status 401/403 could be replaced by a later fallback-host network error. Preserve authentication rejection, stop automatic protected retries and require explicit recovery.
- Watching all settings rebuilt the connection notifier, disposing pending enrollment/retry state. Use the existing settings listener; retain explicit pending status when copying unrelated fields.
- Shared pairing failures lacked stage-specific diagnostics. Show Connecting, Pairing required, Waiting for operator approval, Paired and connected, Network unavailable, and Authentication rejected distinctly. Stop automatic retries for authorization, incompatible routes/protocol, or secure-storage failures. Keep public discovery/claim retries for transient network failures and pending approval.
- Resident uses the same pairing service. Cancel stale connection retries when its editable endpoint changes and stop terminal authentication retries.

The c44 source fetcher already called discovery/pairing before protected status; the older packaged binaries did not contain that enrollment implementation. A new test exercises that real fetcher: repeated pending attempts submit one idempotent enrollment request, make no status calls, then issue authenticated status only after simulated operator approval. There is no evidence that c44 source systematically requested status before first pairing.

The user-supplied live discovery object matches the existing contract and reports `pairing_available: true`, `enrollment_open: false`. A closed window cannot accept a new request. This is separate from the reproducible app defects. The Windows laptop could not reach the hotspot endpoint, and no Android device was attached; the exact installed APK/version and on-device failure chain remain unverified.

## Scope and security review

No backend patch is required for the reported discovery contract. No backend, Android native configuration, recognition, thermal, emergency policy, models, replay/ACK implementation, or dependency changes. No Pi access, service restart, deployment, audio access, or installation.

Pairing remains local-operator approved. Credentials remain in secure storage, keyed by Pi identity and role, with existing proof checks before use at a changed IP. Transient failure clears only active in-memory credentials, not saved secure-storage credentials. No manual API token field is added. Remote hold-to-mute stays disabled. Terminal failures require explicit Connect after the operator corrects the cause; credentials are not silently deleted.

The built manifests retain INTERNET permission and cleartext LAN HTTP support. Caregiver builds `lib/main.dart`; Resident builds `lib/main_resident.dart`. Both flavors use the corrected shared pairing service.

## Verification

- 38 focused Flutter tests passed (0 failed / skipped): pairing_connection_loop_test, device_pairing_test, connection_retry_test, connection_setup_test, alert_pairing_test, alert_delivery_test, resident_app_test, resident_control_test. Seven new regression cases cover the defects and public enrollment flow.
- 5 backend device-pairing route tests passed in an isolated, network-disabled, read-only container using existing dependencies; no backend source changes.
- Both Android release builds succeeded with build number 2 and version name 1.0.0; final packaging was forced to refresh the JNI merge/strip/package outputs. All three packaged ABIs must contain discovery/enrollment and the corrected approval/storage diagnostics before handoff. A later test-only lint correction does not affect built application source.
- Signing verification succeeded for both APKs. Existing Android Debug signer is preserved: SHA-256 `7276f472aaef988c4112c54b5ef6d5487e532bdfab9e7f9c66612a053b9b310c`. These remain development artifacts, not production signing certification.
- Main ID: `com.projectpi.thermalalert`; Resident ID: `com.projectpi.thermalalert.resident`.
- No full Flutter or Python regression suite was repeated. Software checks do not establish physical-device success.

Flutter analyze --no-pub completed with no issues. Final APK/source hashes are supplied in the local transfer manifest and final report.

## Local device verification after separate installation authorization

1. Update the existing apps with the matching APKs; preserve app data and credentials. Do not uninstall or clear storage to troubleshoot. Verify version code 2 and the intended flavor. This work did not install either APK.
2. Enter the current Pi address and port 8765. The IP remains editable; no hotspot address is hardcoded. On the same phone, public `/api/discovery` must return the Project Pi object.
3. Have the local operator open the existing enrollment window (`pair open --seconds 120`). Immediately refresh discovery: `enrollment_open` must now be true. If it remains false, verify the operator CLI and running backend use the same private `PROJECT_PI_PAIRING_DIR`; do not publish credentials or environment dumps. Do not restart services as part of this check.
4. Tap Connect. A new device should display Waiting for operator approval with a request and comparison code; `pair list` should show that request. Compare codes before local approval. The repository CLI equivalent is `python -m raspberry_pi.device_pairing --directory <EXISTING_PRIVATE_PAIRING_DIRECTORY> approve --request <DISPLAYED_REQUEST_ID> --code <DISPLAYED_CODE>`; use the established operator wrapper where available.
5. After approval, verify Paired and connected. Repeat for Resident using its separate role. Existing approved devices should authenticate automatically; a changed IP must not itself require credential re-entry.
6. If unsuccessful, record only the displayed phase, HTTP path/status or secure-storage error code and whether discovery's enrollment window is open. Do not share tokens, claim proofs, secure-storage contents, or private registry files.
7. Verify real alert delivery, durable replay/ACKs, history, and Resident single/double-tap TEST behavior on authorized devices before release. Remote mute remains disabled.

No push, merge, PR creation or production deployment was performed. Existing drafts and other checkouts remain untouched.
