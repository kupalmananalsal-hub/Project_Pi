# Final Resident controls and existing openWakeWord integration

Baseline: `7155269f13ee034d4100584509b26d65676874e3`.
Development branch: `codex/c158-final-resident-controls`.

## Implemented

- Main renders the Resident TEST strip only for an active TEST presentation. Resident disconnection, inactive session events and acknowledged events clear presentation without deleting history. Real alerts retain their independent provider and priority.
- Resident uses pointer-up handling rather than Flutter's delayed double-tap recognizer. First completed tap starts the local repeating keyword beep and queues the authorized keyword TEST immediately. A second completed tap within 300 ms replaces audio with the local siren and shows the Full Alert TEST overlay.
- Both commands carry a gesture ID. The updated backend upgrades the same session-owned event ID from keyword to full, rather than creating a second event. Kind-aware Main deduplication permits that one upgrade. Revision-aware acknowledgements prevent a delayed keyword presentation ACK from consuming the full upgrade. Legacy requests without gesture IDs retain their existing behavior.
- Foreground Resident TEST audio reuses existing locally synthesized WAV sounds. It never initializes notifications, requests notification/full-screen-intent permission, or downloads audio. A serialized replacement stops the previous sound before starting its replacement. App backgrounding and disposal stop foreground TEST output. Backend delivery failure is reported independently of local simulation output.
- A 500 ms hold sends no tap. It starts a mute lease only when the authenticated backend advertises availability and a finite positive bound. Release, pointer cancellation, movement outside the gesture, backgrounding and disposal release the lease. An in-flight acquisition is released when it completes after finger release. UI uses the existing bounded KWS acknowledgement, not local press state, to report listening paused/resumed.
- Existing secure pairing, endpoint settings, real emergency history/replay/ACKs, thermal processing and recognition thresholds remain unchanged.

## Pi-side source update required before using the new protocol

Files: `raspberry_pi/backend/main.py`, `raspberry_pi/resident_control.py`.
Review the supplied Pi-only patch in an isolated development checkout against the baseline. Do not import directly into production or overwrite intervening Pi reliability changes. No Pi transfer, service restart, deployment or configuration change was performed.

Paired Resident mute is still unavailable by default. It requires **all** existing local lease gates (TEST mode, single backend worker, explicit remote-mute enable, private IPC directory, fresh KWS acknowledgement and an explicit finite positive lease bound), plus a local paired-device allowlist:

```
PROJECT_PI_RESIDENT_TEST_MODE=1
PROJECT_PI_REMOTE_MUTE_ENABLED=1
PROJECT_PI_REMOTE_MUTE_MAX_SECONDS=[REQUIRES SAFETY APPROVAL]
PROJECT_PI_REMOTE_MUTE_DIR=[EXISTING PRIVATE SHARED IPC DIRECTORY]
PROJECT_PI_REMOTE_MUTE_DEVICE_IDS=[LOCALLY APPROVED PAIRED RESIDENT DEVICE ID]
```

These are configuration requirements, not settings to apply now. The bracketed lease placeholder is deliberately invalid and fails closed. No production duration is supplied or approved. Backend and the existing KWS capture owner must share the reviewed bound/IPC configuration. Credentials still authenticate every request; allowlisting alone cannot authenticate a device. Devices absent from the local allowlist cannot issue paired mute commands. Existing legacy scoped credentials retain their existing gates. Main's existing disable-mute action remains available during an active TEST presentation.

Lease expiration, missed release, disconnected Resident sessions, backend/KWS restart and invalid/stale worker acknowledgement use the existing fail-open KWS gate. Thermal monitoring and authorized alert outboxes are outside that gate. This safety-sensitive path was not exercised in this task.

## Actual model artifacts

The requested source directory contained these 17 ONNX classifier names, each with its external-data companion:

`agai`, `ang_sakit`, `aray`, `emergency`, `help`, `help_me`, `kailangan_ko_ng_tulong`, `ouch`, `over_here`, `please_help`, `rescue`, `saklolo`, `save_me`, `sunog`, `tulong`, `tulungan_mo_ako`, `tulungan_niyo_ako`.

All inspected input metadata is float `[1,16,96]`; output metadata is `[1,1]`. These are embedding-classifier candidates for the existing openWakeWord wrapper, not raw waveform models. The packaging utility reads ONNX metadata without importing a recognition runtime, preserves external-data references, and copies only classifier candidates and their actual required companions. Its inventory includes exact names, shapes, sizes and hashes. Packaging is not inference or model validation.

Reuse `raspberry_pi/kws/audio_preprocessor.py` and the existing `kws-alert.service`: the service already sets `OPENWAKEWORD_MODEL_DIR` to the canonical `dataset/audio/openwakeword_models` directory. After a separately reviewed deployment, place each approved `.onnx` and `.onnx.data` pair together in that directory. Preserve existing artifacts instead of blindly overwriting them. If `OPENWAKEWORD_MODELS` is explicitly set, it overrides discovery; the operator must review that existing override. Keep frontend embedding/VAD assets required by the installed openWakeWord runtime; this package does not download or replace them.

No second microphone service was created. Existing ReSpeaker capture, VAD, score thresholds, cooldown/fusion, real event IDs, backend decisions and audio-status reporting remain the integration path. Actual runtime initialization determines which models load; missing dependencies/unsupported ONNX operators must remain reported failures, never detections. No runtime compatibility, model accuracy or physical detection success is claimed.

## Build-only delivery

Both existing Android release flavors are built with the original package IDs/signing configuration. No Python tests, Flutter tests, Flutter analysis, acoustic inference or hardware validation were run, as explicitly requested. Gradle's normal compilation/package dependency tasks may run automatically; native JNI merge/strip/package tasks are forced to avoid the previously observed stale APK packaging defect.

These are untested development changes. Foreground sound can still be affected by Android audio focus, alarm volume, output routing or OS interruption. Notifications/background alarm behavior was not expanded. Local TEST presentation does not prove backend acceptance or Main presentation. Full integration requires the Pi-side source update and later separately authorized testing. Do not enable production remote mute before safety approval of the lease and independent verification.

Exact APK paths, build results, source patch paths and changed-file list accompany the local handoff. No push, merge, PR update or deployment is authorized by this task.
