# PR #6 pre-merge corrections

These corrections address the review of `a60ef164fb68ab0481561bb2e352264ce0d9aeb8`
on the existing Phase 4 branch. PR #6 remains open; this is not merge approval.

## Positive language integrity

`KEYWORD_LANGUAGES` is now shared by the API, Pi recorder and strict validators.
The API rejects explicit positive language mismatches. Unknown legacy language
(`und`) remains accepted for compatibility, but its sidecar requires review and
strict preparation excludes it. The Training screen synchronizes and locks the
positive language selector to the selected keyword; negative language remains
explicitly selectable. Strict validation also rejects mismatches already on disk.

Mobile uploads explicitly send `recording_device=mobile_microphone` and an
anonymous session ID stable for the API-service instance. These are client-reported
capture metadata, not a verified hardware model or a ReSpeaker claim. Older API
clients retain unknown capture fields; unknown information is not manufactured.

## Pi capture and provenance

The Pi recorder resolves its input device before capture, records through that
same input and preserves the capture-library device description. A supplied
hardware description alone is insufficient for verified provenance. New WAVs have
language, positive label, stable speaker/session IDs, capture details, measured
format/duration, original and processed file hashes, PCM hash, source group,
consent reference and review status. No conversion occurs after recording, so
original and processed file hashes are equal. This is mono recognition capture;
it does not replace a multichannel direction-of-arrival recording workflow.

Example (use your actual device identifier, anonymous IDs and authorized records):

```powershell
python raspberry_pi/kws/record_keyword_dataset.py --keyword tulong --samples 1 --speaker-id speaker_01 --session-id session_01 --age-group adult --gender other --distance-m 1 --noise-condition quiet --device 2 --recording-device-description "Actual verified microphone model" --consent-reference consent_record_01 --reviewer-id reviewer_01
```

Supplying a consent reference asserts authorization for this collection. After
capture, open and listen to the printed WAV path and compare its content and
hardware setup against the capture record. Type `VERIFIED` only after those
checks. Unknown session/device/reviewer or an unconfirmed review keeps the sample
`REVIEW_REQUIRED`. A generic USB input name does not establish ReSpeaker identity;
verify the physical setup and retain the collection record. No physical recording
was made during this correction task.

## Safe legacy migration/review

The new `recording_provenance.py` command defaults to preview. Original WAVs and
CSV rows are never changed. No-review migration measures file properties and
checksums, copies the existing anonymous speaker and label, and explicitly keeps
language, session, hardware, consent and original-capture history unknown. Such
samples remain excluded from strict preparation. Missing WAVs, wrong paths,
changed review checksums and unapproved speaker substitutions are rejected.

```powershell
python raspberry_pi/kws/recording_provenance.py --dataset-dir dataset/audio/keyword_dataset
python raspberry_pi/kws/recording_provenance.py --dataset-dir dataset/audio/keyword_dataset --reviews dataset/audio/keyword_dataset/reports/local-recording-reviews.jsonl
```

Only after inspecting the preview, append `--apply` to create missing sidecars or
explicitly review pending sidecars. Approved sidecars cannot be overwritten.
Pending updates require the current file checksum and preserve previous evidence;
a Pi capture-device record cannot be replaced by a different review assertion.
The migration validates all selected metadata before beginning sidecar writes.
If historic speaker metadata is absent or wrong, recover it from real collection
records first; this command does not guess or silently rewrite speaker identity.

Each private JSONL review contains a relative `path`, `expected_sha256` (hash of
the current WAV), `language`, `session_id`, `recording_device`, `capture_device`
(actual capture record or its anonymous collection reference), `device_verified`,
`consent_reference`, `consent_confirmed`, `audio_reviewed`, and `reviewer_id`.
Verification booleans must be true only where supported by actual records and
listening. Legacy original-audio hashes remain unknown even after review; the
current WAV hash cannot reconstruct an unknown original capture. Keep reviews
under the ignored local reports directory; never commit consent forms or audio.

## Regression and corpus evidence

Tests cover Tagalog/English API mismatches, old unknown-language uploads, mobile
capture metadata, widget language synchronization, explicit negative language,
strict on-disk language validation, recorder-to-manifest integration, capture input
binding, and migration review/immutability. Capture is mocked in software tests;
these results do not certify physical microphones or recognition performance.

The existing local negative corpus was revalidated without reimporting archives:
563 WAVs passed strict checks (468 speech, 95 noise), zero strict issues. No public
source audio, private metadata, source licenses or existing split was changed.
Positive training readiness remains blocked by the previously reported data gaps.
No neural training/deployment, alert-policy change or automatic merge occurred.

## Exact verification results

| Command | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| `python -m unittest test.test_keyword_dataset_pipeline test.test_multilingual_dataset test.test_training_api` | 66 | 0 | 0 | 0 |
| `python -m unittest discover -s test -p "test_*.py"` | 235 | 0 | 0 | 3 |
| `flutter test` | 72 | 0 | 0 | 0 |

`flutter analyze` completed with no issues. Three Linux filesystem permission
tests were skipped on Windows. Python ran in the existing isolated test venv.
These are local results, not a claim of GitHub Actions or device certification.
Logs remain in ignored build/pr6-corrections-{focused,python,flutter,analyze,corpus}.log.

## Exact correction file list

- `docs/phase4_pr6_corrections.md`
- `lib/screens/training_screen.dart`
- `lib/services/pi_api_service.dart`
- `raspberry_pi/backend/main.py`
- `raspberry_pi/kws/dataset_integrity.py`
- `raspberry_pi/kws/dataset_readiness.py`
- `raspberry_pi/kws/keyword_dataset_common.py`
- `raspberry_pi/kws/record_keyword_dataset.py`
- `raspberry_pi/kws/recording_provenance.py`
- `test/test_multilingual_dataset.py`
- `test/test_training_api.py`
- `test/training_negative_screen_test.dart`
