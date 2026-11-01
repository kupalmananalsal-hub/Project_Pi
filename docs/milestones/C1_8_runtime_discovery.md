# C1.8 recognition runtime discovery

## Result

Discovery found a working ONNX Runtime environment and stored keyword classifier
models, but no complete waveform-to-keyword recognition stack. Acoustic inference,
ASR and system-alert evaluation were **NOT RUN**. This is a runtime-discovery
milestone, not an accuracy or false-positive result.

This report contains code/runtime findings only. Restricted audio, record IDs,
paths, checksums, transcripts, annotations, per-record status CSVs and detailed
machine inventories remain outside Git.

## Source examined

Architecture and active-service configuration were inspected from
`milestone/m1-m2-reliability-hardening` at
`9dde20bcf944f0c498ebbb851e85b478a2fd5ae6`.
This PR targets main separately and does not import or modify that branch.
The observed source configuration is not proof of the running Pi configuration.

| Stage | Source and behavior |
| --- | --- |
| Capture/preprocessing | `raspberry_pi/kws/kws_alert_dual.py`: 16 kHz capture; active service requests two channels and 1280-frame chunks. Raw mono goes to `AudioPreprocessor` for openWakeWord/VAD; cleaned mono from `NoiseSuppressor` feeds fallback engines when speech is active. |
| openWakeWord | `raspberry_pi/kws/audio_preprocessor.py`: loads ONNX keyword files and external-data companions through the openWakeWord package. Keyword classifiers require embedding features, not PCM waveform samples. |
| Vosk | `create_vosk_recognizer`, `read_vosk_text`, `vosk_worker`: acoustic model plus `KaldiRecognizer`, final/partial text, then keyword matching. |
| Keyword matching | `detect_tagalog_keyword`: approved aliases, selected prefix rules and `SequenceMatcher` ratio >= 0.72. `masakit` remains mapped to `ang sakit`. A text match is not itself an acoustic result. |
| Snowboy | `create_snowboy_detector`, `snowboy_worker`: native runtime, resources and model files; mono PCM through `RunDetection`. |
| Fusion/transport | `DetectionDispatcher` and `AlertPoster`: confirmation/cooldown, event creation, outbox persistence and HTTP POST. |
| Backend decision | `raspberry_pi/backend/main.py` `/api/alerts` and `raspberry_pi/alert_decision.py`: classify with thermal evidence, persist and publish. These are separate from recognition outputs. |

The live entrypoint is not a safe file-replay adapter: it can open a microphone,
write status/outbox state and POST alerts. It was not started or imported.
The optional wav2vec2 verifier is disabled in the inspected active unit. Its
`from_pretrained` path may fetch assets, so it was not initialized.

## Existing resources actually checked

- The registered Windows Python is 3.14.5. Its default environment lacks Vosk,
  openWakeWord, ONNX Runtime and the associated numeric/runtime dependencies.
- An existing project test environment has Python 3.14.5, ONNX Runtime 1.31.1,
  NumPy 2.5.4 and SciPy. Several existing uv-cached Python 3.13 environments also
  expose ONNX Runtime/NumPy. They do not expose Vosk/openWakeWord/Snowboy.
- All **17 existing keyword ONNX files and companion data loaded successfully**
  on CPU for signature inspection. No classifier `session.run` was called.
  Inputs are float tensors `[1,T,96]`, with observed T values
  **16, 20, 21, 22, 23, 27 and 41**. They cannot consume raw WAV data directly.
  Model hashes and individual signatures are pinned in the local inventory.
  No semantic training-release version is established by these model files.
- No compatible installed openWakeWord package or matching mel/embedding/VAD
  frontend assets were found in the inspected locations. No Vosk acoustic model
  or Snowboy native/resource/model combination was found.
- Existing Docker image `pi9-test:local`, ID
  `sha256:598cf860e36fdcd149e1161e5e63c74d154c74fc173fbcfdc1da445c21cd5334`,
  was checked in a disposable container: Python 3.11.18, no recognition packages.
  It ran with network disabled, read-only root, no repository/audio mounts, dropped
  capabilities and no new privileges. No package/image was installed or pulled.
- WSL listed only Docker Desktop's internal distribution; no independent user
  distribution was found. No WSL services or persistent containers were started.

Discovery covered project copies, Downloads, Documents, OneDrive, StudioProjects,
user caches/local tools, Python/uv directories, and system Python/tools locations.
Filesystem traversal was time-bounded: an initial 90-second broad scan was followed
by separate eight-second-per-root checks and targeted cached-environment probes.
Some broad cache traversal was incomplete. These are negative findings within
the inspected locations, not proof of whole-disk absence.

## Configuration to freeze before an experiment

In the inspected **active** `kws-alert.service`:

| Setting | Configured value |
| --- | --- |
| openWakeWord VAD | 0.40 |
| Global wake threshold | 0.20 |
| Tagalog / English per-keyword wake thresholds | 0.20 / 0.30 |
| Vosk configured candidate confidence | 0.75 |
| Snowboy configured candidate confidence | 0.75 |
| Snowboy base sensitivity; quiet/moderate/noisy | 0.28; 0.38/0.28/0.28 |
| Help confirmation / cooldown | 1.2 s / 2.0 s |
| Policy advisory / critical | 0.30 / 0.85 |
| Repeat escalation to critical | Disabled |
| Thermal freshness | 1.25 s |

Configured fallback confidence is not a measured acoustic probability. Code defaults
and the legacy service differ from the active unit. Runtime environment overrides,
running device revision and actual model/frontend versions still need verification.

The configured Vosk model is `vosk-model-tl-ph-generic-0.6` under the Pi's
`/home/thesis/vosk-models/`; this is an intended path/version, not a locally
verified model installation. Snowboy paths also point at the Pi.

## Blocker and shortest next step

For the Windows path, ONNX Runtime is already usable, but matching openWakeWord
frontend assets and the package are missing. The Vosk path independently needs
both its package and a genuine acoustic model. A fabricated embedding tensor,
corpus-transcript matcher run or heuristic replacement would not test the actual
waveform pipeline and was not substituted.

The likely shortest route to an existing complete setup is a **separately authorized**
inspection of the Pi environment and an isolated offline runner there, if its
configured assets actually exist. Alternatively, separately authorize provisioning
the missing local package/model/frontend resources into a compatible environment.
Neither action has been taken.

Before running: pin exact code, model/frontend hashes, engine versions, preprocessing,
thresholds, chunk/tail handling, reset/cooldown/fusion rules and any thermal scenario.
Use an adapter with local output collectors and no microphone, HTTP posting,
production databases/outboxes or notification sinks. Preserve mono corpus limitations;
these inputs cannot validate ReSpeaker direction or physical hardware behavior.
If conversion is needed, use documented anti-aliased in-memory processing and retain
source identity. Flush short tails and process long utterances in full.

## Verification and sharing

Local checks confirmed model load/signature inspection and a manifest-linked
NOT_RUN status for each candidate, with recognized text, scores, keyword decisions
and alert decisions blank. The original evaluation manifest hash was unchanged.
No source WAV was opened during this blocked inference phase; no conversion,
recognition output, system alert, final ground truth or performance metric is claimed.

Only this redacted report is proposed for Git. There are no production-code,
model, threshold or data changes. Validation for this documentation-only change:
diff/whitespace review, evidence consistency and restricted-content exclusion.
Application regression suites were not rerun because no application code changed.
