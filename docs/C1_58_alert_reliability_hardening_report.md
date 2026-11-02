# C1.58 Alert Reliability Hardening

Real application changes are implemented in the offline development worktree. No disconnected reference implementation was added. The changes address deterministic fusion-state and request-cancellation defects, without claiming acoustic improvement or deployment readiness.

- **RUNTIME FIXES IMPLEMENTED: YES** — KWS dispatcher and backend API/registry.
- **SOFTWARE REGRESSION VERIFIED: YES** — 351 selected mocked tests passed, zero failures/errors/skips; scope below.
- **ACOUSTIC ACCURACY VERIFIED: NO**.
- **PRODUCTION DEPLOYMENT AUTHORIZED: NO**.

## A. Confirmed problems addressed

The existing C1.45, C1.50 and C1.52 findings supplied the reproduction and safety boundaries; their investigations were not repeated. C1.45's earlier exact-alias changes remain. C1.58 corrects the remaining dispatcher coupling:

1. A Vosk text hint canceled pending Snowboy help without any accepted replacement submission. A later ordinary hypothesis could not restore that evidence.
2. An accepted Vosk `tulong` submission could suppress independent Snowboy/openWakeWord `help` regardless of whether they represented the same acoustic occurrence.
3. A cooldown-rejected `tulong` updated suppression timestamps and canceled pending help before checking acceptance.
4. Independently, API owner cancellation bypassed `except Exception`, leaving its in-flight idempotency claim unresolved. A canceled duplicate request also canceled the result Future shared by other retries.

New deterministic tests reproduced these defects against actual application functions before changes. Recognition/model outputs, time and timers are synthetic; backend methods are extracted from actual source with temporary synthetic stores and injected I/O. No application startup, live model or production store is involved.

## B. Exact runtime files modified

| Runtime file | Functions changed | Purpose |
|---|---|---|
| `raspberry_pi/kws/kws_alert_dual.py` | `DetectionDispatcher.__init__`, `note_vosk_text`, `_publish_tulong`, `_schedule_help`, `_publish_help`, `_publish_help_now` | Keep accepted correlation timestamps per engine; prevent text hints and rejected submissions from vetoing independent help |
| `raspberry_pi/backend/main.py` | `AlertIdempotencyRegistry.fail`, `api_alerts` | Protect shared duplicate Future from waiter cancellation and release/resolve owner claims on cancellation |

No Flutter, model, score threshold, alias list, VAD algorithm, backend classification policy, database schema, service, or runtime entrypoint configuration was changed. The experimental observation modules remain disconnected and are not imported by these changes.

## C. Before and after source behavior

### KWS dispatcher

| Trigger | Before | After |
|---|---|---|
| `note_vosk_text('tulong')` | Refreshed a hint timestamp and canceled pending Snowboy help | Compatibility hook performs no state mutation or publication. Text alone has no acceptance receipt. |
| Rejected `tulong` submission | Refreshed timestamps/canceled help before cooldown rejection | Cooldown is checked under the dispatcher lock before any correlation-state mutation. Rejection leaves timestamps, per-source state and pending help untouched. |
| Accepted `tulong` from source A, help from source B | Shared timestamps could veto B | Correlation checks use only B's accepted `tulong` timestamp. A cannot cancel B's pending help. |
| Accepted `tulong` then help from same source | Existing correlation window applied | Existing same-source window is retained; no new window value or timeout is selected. |
| Repeated same keyword | Existing per-keyword cooldown | Unchanged. Multiple same-keyword engine submissions still share the keyword cooldown. |
| Another source accepted during an earlier same-source window | Initial C1.58 patch used one last-source field | Review found this could overwrite another source's still-active window. Final code uses `last_tulong_by_source`; every help guard reads the matching source under the lock. |

`last_tulong_at` remains the aggregate latest accepted timestamp for compatibility; `last_tulong_hint_at` remains present but is not refreshed. `note_vosk_text` and `submit` signatures remain unchanged. No timer duration, threshold, keyword guess, confidence conversion or new alarm authority is introduced. The existing Snowboy confirmation timer remains.

Acceptance here means acceptance by the existing dispatcher cooldown, not successful HTTP delivery or a new durable observation receipt. `AlertPoster.publish` has no publication receipt interface; this change does not claim transactional coupling of correlation state to durable backend acceptance.

Independent evidence preservation deliberately removes cross-engine vetoes. It can allow distinct `tulong` and `help` publications from one acoustic occurrence. Acoustic correlation and episode deduplication cannot be invented to conceal that consequence. Existing per-keyword cooldown is preserved, but is not a validated episode detector.

### Backend request cancellation

Duplicate requests now await `asyncio.shield(claim['future'])`. Canceling one HTTP handler's wait does not cancel the shared result or the owner processing. Other duplicate waiters receive the existing response and duplicate metadata.

The owner processing block catches `asyncio.CancelledError` as well as ordinary exceptions. Registry cleanup removes its in-flight claim, cancels the shared future for a canceled owner, and propagates cancellation. Waiters terminate rather than hang; a same-ID retry can claim again if nothing persisted, or recover the immutable existing row through the existing durable lookup if it did.

No event ID/fingerprint normalization, conflict check, classification, thermal-read policy, insert transaction, immutable history or replay/ACK policy changed. A running `asyncio.to_thread` operation is not stopped by task cancellation. The real-thread regression releases an original insertion after a same-ID retry has inserted; the existing SQLite uniqueness/deduplication path keeps one row and one publication by that retry. This is not a claim of atomic classification/history/publication.

Cancellation after insertion can still interrupt AlertHub publication. That limitation predates C1.58. Durable replay/polling can recover the row; these tests do not demonstrate every live/legacy subscriber receives a transient hub notification or certify exactly-once physical notification delivery.

## D. Regression tests and expectation changes

New test files:

- `test/test_alert_reliability_hardening.py`: 8 actual-dispatcher tests. Covers hint revision, all six engine/arrival order combinations, rejection without timestamp/pending-state refresh, text-only no-op, synthetic Vosk failure plus a later healthy empty-text invocation retaining pending help, same-engine correlation, repeated help/cooldown, and overlapping source windows.
- `test/test_alert_request_cancellation.py`: 6 actual API/registry tests using synthetic stores. Covers canceled owner before persistence, canceled duplicate with another waiter surviving, cancellation at insert/after commit/publication boundaries, canceled owner waking waiters, a real background insertion finishing after cancellation and retry, and repeated unchanged thermal/same-ID critical replay.

The existing tests below contained assertions that intentionally characterized the old cross-engine suppression. Those assertions and names were changed to require independent help; no tests were deleted, skipped or marked expected-failure:

| Existing file | Updated scope |
|---|---|
| `test/test_runtime_safety_blockers.py` | Arrival-order, hint, rejected timestamp and failure counterexamples become corrected runtime acceptance cases. Unresolved partial authority, sustained scores, repeat escalation, backend/thermal counterexamples remain. |
| `test/test_recognition_defect_remediation.py` | Vosk `tulong` must preserve pending/subsequent independent Snowboy help |
| `test/test_kws_live_paths.py` | Actual worker/dispatcher wiring preserves independent help after Vosk or openWakeWord `tulong` |
| `test/test_kws_recognition_regression.py` | Cross-engine help no longer assumed a misfire; exact aliases and ordinary-word safeguards remain |

The engine-failure regression demonstrates independent evidence survival, not automatic worker supervision/restart in production. Missing/empty Vosk text has no veto side effect. Existing decision tests cover missing optional engine scores. Complete native missing-score/health propagation is not added: existing numeric/VAD fallback conversions and failure supervision remain unchanged. Changing how unknown VAD authorizes detection would require a separately specified interface and decision-policy review; no fabricated zero-score release or new fallback policy is introduced here.

## E. Test results and execution evidence

| Checkpoint | Result |
|---|---|
| Prior selected baseline | 333 passed; 0 failures/errors/skips |
| New dispatcher RED | 7 methods; 9 failing assertions/subtests; no errors (the initial discovery also picked up imported fixture TestCase methods; import corrected before the final focused RED) |
| Dispatcher initial GREEN | 7 passed |
| First full run after runtime change | 333 methods; 14 failures from obsolete cross-engine suppression expectations; all retained and updated as described in D |
| Existing selected suite after expectation updates | 333 passed |
| Backend RED | 3 methods; 5 failing assertions/subtests; no errors |
| First backend GREEN attempt | Owner cleanup passed; one test incorrectly compared duplicate-response marker equality. Corrected test to compare immutable fields and separately assert the expected false/true duplicate markers. |
| Backend strengthened tests | 5 passed, including real-thread continuation |
| Combined before review correction | 345 passed |
| Reviewer timestamp regression RED | 8 dispatcher methods; 1 failure; no errors |
| Per-source timestamp GREEN | 8 passed |
| Combined after review fix | 346 passed |
| Final expanded suite | **351 passed; 0 failures, 0 errors, 0 skips** |

Final suite = the retained 333 selected mocked cases + 8 dispatcher tests + 6 cancellation/idempotency tests + 4 further existing storage/protocol tests (legacy migration, invalid/unoffered ACKs, disconnected/overflow replay of 205 synthetic events, invalid protocol payloads).

The selection includes real KWS publication/outbox UUID tests, backend classification/thermal/idempotency cases, advisory then independently submitted new-ID thermal-positive critical classification, restart/replay, and independent caregiver acknowledgement. No full network application integration test was run. The backup-CLI subprocess case is outside this selection; Flutter tests were not run because no Flutter/Dart executable was available on PATH or the checked common SDK locations. No toolchain download or network dependency resolution was attempted.

Execution used the standard-library runner and logs in:

`/home/thesis/offline-work-backups/C1_58_validation_20261102T074250.787322Z/`

`run_mocked.py` contains the exact selection and can run baseline or `combined`. It forces bytecode off via invocation, places temporary fixtures under the offline worktree, rejects network connection/address resolution and subprocess/system calls, rejects recording/model and production-file opens, and restricts SQLite connections to synthetic paths inside the offline worktree. It redirects test output to retained logs and cleans its temporary fixture tree. No production backend is imported or started. Expected malformed-policy warnings in existing tests are retained in logs.

The final run is `final-expanded.log`. Red/green and earlier full-run logs are retained. `C1_58-only.patch` compares this milestone against raw preflight copies (backend against unchanged HEAD) instead of conflating it with the earlier C1.43–47 patch. All test numbers are software evidence; no acoustic accuracy/recall/latency or physical siren performance was measured.

## F. Remaining policies and unsupported corrections

| Requested behavior | Outcome / blocker |
|---|---|
| Independent Snowboy/openWakeWord help; Vosk revision | Implemented dispatcher correction, including rejected submissions and source-specific accepted correlation |
| Rejected observations changing suppression | Cooldown rejection fixed. Durable poster receipt/atomic suppression transaction remains outside current public interface. |
| Same immutable ID retries creating extra backend notifications | Shared cancellation isolation and claim recovery fixed; durable ID/fingerprint deduplication retained and tested |
| New authorized critical event after advisory | Existing new-ID request classification preserved; tests show negative-thermal advisory then positive-thermal distinct-ID critical. This does not authorize automatic thermal association. |
| Repeated unchanged thermal evidence | Same-ID replay returns one immutable row and does not reclassify/re-read thermal; explicit regression passes. Automatic reevaluation/critical-event generation is unchanged and BLOCKED by association and authority policy. |
| Separate distress episodes | Existing eligibility/cooldown remains. No invented episode end, rearm duration or repeated-score episode rule. Unique event IDs alone do not establish a new real emergency. |
| Provisional Vosk alarm authority | Unchanged and unresolved; removing independent-engine vetoes does not certify partial authority |
| Missing scores and engine supervision | No independent evidence is erased by the corrected hint/submission paths on failure/empty text. Full structured health/unknown-score transport and safe runtime recovery remain unintegrated. |
| Durable atomic classification/history/outbox | Not claimed. Pre-persistence retries can still re-evaluate mutable classification history; interrupted threaded work can continue. Requires a separate transactional design review. |

No experimental `UNRESOLVED` classification is written into the live alert schema or delivery paths. No schema migration is introduced.

### Flutter inspection and blocker

Read-only inspection covered critical activation, duplicate delivery, reconnect/replay, acknowledgement, stop, superseded IDs and restart recovery. Existing runtime generation guards, durable inbox/dispositions, ACK paths and active-alert handling remain unchanged.

Review found a concrete candidate in `lib/providers/alerts_provider.dart`: reliable delivery's `isActive` callback recognizes the current active event ID but not retained `_supersededAlertIds`. Recreating a delivery service while the provider still owns active B can offer superseded A for presentation and then B again. A narrow future fix should treat both as members of the current retained alarm lifecycle, with an identity-specific A→B / service recreation / replay A+B / dismiss regression using existing provider and delivery-service test fixtures. It must also preserve fresh-process unconfirmed replay and genuinely new critical C after an older acknowledgement.

**Flutter correction BLOCKED in C1.58 by unavailable executable Flutter/Dart test tooling**, not by acoustic data. No Flutter source was changed without running the required deterministic reproduction/acceptance tests. This is a remaining known reliability candidate, not a claim that the app lifecycle is fully verified. Physical siren activation remains separately unauthorized.

## G. Independent review findings

A separate read-only delivery review identified the backend cancellation defects and the Flutter lifecycle candidate. A second read-only runtime review inspected the actual C1.58 diff, fixtures and expectation changes, and found the per-source-window overwrite edge case in the initial implementation. The overlap is supported by existing checked-in service configuration (2.0-second cooldown versus 2.2-second correlation), not a new policy value.

The regression failed before the correction; final code retains accepted timestamps per source. Re-review found no remaining blocking finding in the changed KWS/backend code. Reviewer also checked that shielding/cleanup does not change classification/persistence semantics and that the real-thread insertion test covers continued work after cancellation. Review does not certify hardware, network delivery, acoustic performance or unresolved policy. Reviewers made no edits, ran no models or application tests, and accessed no private data.

## H. Preservation and safety verification

Preflight verified all eight existing backup manifests and all **32** cumulative development artifacts (including C1.55–57). A new byte-exact checkpoint was created at:

`/home/thesis/offline-work-backups/C1_58_preflight_20261102T074250.787322Z/`

It contains `all-32-development-artifacts.tar`, all 32 raw `verified-recovery/` files, original HEAD, checkout state, original tracked binary patch, inventory, restoration instructions and SHA256SUMS. All source files restored exactly before implementation. These original bytes are preserved even for intentionally edited files. Backend's pre-C1.58 source is also available at unchanged Git HEAD.

Final checks compare production/evaluation HEAD/branch/status to preflight, the retained preflight bytes/checksums, and the allowed offline source changes. The only application-source differences added by C1.58 are the two files in B; prior keyword/threshold/configuration and policy files are untouched. Five pre-existing development artifacts were intentionally edited (KWS plus the four existing test files in D); the other 27 checkpoint artifacts remain byte-identical. Two new Python test files and this report are added. No original file was deleted. No staging, commit, push, fetch, pull, merge, rebase, reset, clean or deployment occurred.

Production tracked files remain clean; its pre-existing untracked entries are untouched. Evaluation remains clean. No production database, credential, alert queue, recording or model contents were opened; no microphone/inference, service restart, Docker, swap or boot change was performed. SQLite work used only disposable synthetic test stores.

## I. Proposed pull request boundaries

1. **KWS independent evidence:** dispatcher source plus eight new tests and the four explicit expectation-update files. Review cross-engine notification consequences and preserve same-engine timers/cooldown/alias/score configuration. Keep earlier C1.43–47 changes visible as their own review boundary; do not accidentally hide them in this patch.
2. **Backend cancellation/idempotency:** only `main.py` request/registry changes and cancellation tests. Review cancellation before/during/after persistence, shared waiter semantics, immutable response identity and replay recovery. No classifier or schema change.
3. **Flutter lifecycle follow-up:** after offline SDK/test capability is available, reproduce the identified superseded-ID replay issue and implement the narrow membership guard with provider/service tests. Separate from current Python changes.
4. **Episode/thermal authority work:** separate design and authorization; remain BLOCKED rather than coupling speculative policy to these fixes.

No PR, commit or staging action was performed. Each source boundary can be reviewed and reverted independently using the C1.58-only patch and checkpoint. Restore only the intended source files after preserving any subsequent work; do not apply this backup to production automatically.

## J. Controlled deployment requirements

Production deployment remains unauthorized. Before any later release: review the actual source boundaries and tests, approve the independent-engine behavior change, resolve or explicitly scope the remaining Flutter and authority/episode/thermal blockers, run a separately authorized isolated system exercise, verify durable replay and no production routing, preserve code/config/storage with rollback, and obtain explicit deployment/service-control authorization. Existing mocked results cannot establish acoustic efficacy, false-alarm rates, safe audible authorization or physical delivery reliability.

C1.58 completes two narrow offline runtime corrections. It does not authorize production or silently enable the earlier experimental architecture.
