# C1.58-INT — Raspberry Pi Backend Integration Preflight

Project: IoT-Based Thermal-Acoustic Human Detection System  
Inspection and offline validation: 2026-11-02 (UTC; Asia/Manila local date is the same).

**Preflight completed. Windows/Pi integration is BLOCKED pending source transfer.**
The current Pi regression selection passes, including all 351 C1.58 tests. This is
not a combined Windows/Pi pass, a deployment approval, or acoustic/hardware evidence.
No application source was changed during this preflight. The only addition to the
offline worktree is this report; new review tests, logs and recovery files are outside it.

## 1. Existing Pi source status and preservation

| Checkout | HEAD at preflight | Branch | Initial state |
|---|---|---|---|
| Offline `/var/tmp/Project_Pi_C1_43_alarm_fix` | `8a44f109fae8adb4b7daa833c15548b56ccd2452` | `development/c1-43-c1-47-recognition-safety` | 4 modified tracked files, 32 untracked development files; no staged changes |
| Production `/home/thesis/Project_Pi` | `1a5c3095a27421cb4c667ee6caed14169729e774` | `main` | Tracked files clean; four pre-existing untracked entries retained |
| Evaluation `/var/tmp/Project_Pi_M3_eval` | `8a44f109fae8adb4b7daa833c15548b56ccd2452` | `main` | Clean |

Offline and evaluation share `/var/tmp/Project_Pi_M3_eval/.git`; its history is
shallow. No new worktree, ref, commit, index entry or Git object was created there.
Production is a separate repository. Only Git metadata/status was inspected there;
no production alert database, backup database, model or credential contents were read.

All **10 existing SHA256SUMS manifests (156 entries)** verified. The 32 original
pre-C1.58 recovery files match both their inventory and their tar archive members.
All **9 files** recorded in C1.58's completion verification match the current offline
bytes, including backend, KWS, reliability/cancellation tests and the C1.58 report.

A new current checkpoint was needed: the previous raw-source archive preceded the
final C1.58 edits. It is retained at:

`/home/thesis/offline-work-backups/C1_58_INT_20261102T103822Z/`

The checkpoint contains all **36 current development artifacts**, verified twice
against raw copies and archive members, plus Git HEAD, branch/status snapshots,
tracked/staged/unstaged binary patches, four tracked HEAD preimages, inventory,
hashes and individual-file recovery instructions. `preserve.py`,
`backup-verification.json`, `inventory.json`, `RESTORE.md` and `SHA256SUMS` record
the procedure and evidence. Earlier backups were not changed or replaced.

## 2. Current unmerged fixes and implemented components

The four tracked modifications are:

| File | Existing unmerged content preserved |
|---|---|
| `raspberry_pi/backend/main.py` | `api_alerts` shields duplicate waiters; catches owner `CancelledError`; `AlertIdempotencyRegistry.fail` releases the claim and cancels its shared future on owner cancellation |
| `raspberry_pi/kws/kws_alert_dual.py` | Earlier exact whole-token Vosk alias matching; C1.58 per-source accepted `tulong` timestamps; rejected submissions/text hints cannot cancel independent help |
| `test/test_kws_live_paths.py` | Actual worker/dispatcher independent-engine acceptance expectations |
| `test/test_kws_recognition_regression.py` | Exact-alias and independent-engine regression expectations |

The other 32 files include the C1.43–58 reports, untracked regression/reference
helpers, disconnected experimental modules, and
`test/test_alert_reliability_hardening.py` / `test/test_alert_request_cancellation.py`.
Their full paths/hashes are in the new inventory. No untracked artifact was removed,
staged or replaced. The experiments remain disconnected from runtime authority.

Actual source inspection, rather than report titles alone, establishes:

| Component | Current offline implementation and evidence |
|---|---|
| Backend authentication | `backend/main.py:171` onwards: fail-closed configuration validation; constant-time bearer comparison; middleware protects `/api/` and `/ws/`. Explicit acknowledged `open` mode remains an unauthenticated exception. |
| Caregiver authentication | `raspberry_pi/alert_delivery.py:13`: per-installation SHA-256 verifier with constant-time comparison; protocol-v2 authenticates before replay/ACK handling. Locked backend blocks even this protocol. |
| Durable events | `main.py:320` `AlertStore`: SQLite WAL, additive migration, unique non-null event IDs, immutable JSON envelopes, request fingerprints, sequence/instance boundaries and per-caregiver ACK records. |
| Replay/disconnect recovery | `alert_delivery.py` `DeliverySessions.serve`: bounded SQLite replay pages, durable live polling, independent confirmation, heartbeat/session cleanup and stale-session replacement. Polling covers commit-before-hub-publication interruption. |
| Request cancellation/idempotency | `main.py:582` registry and `main.py:2731` API: durable lookup before in-memory claim, same-ID conflict rejection, cancellation-safe duplicate waits and owner cleanup. This is HTTP-task cancellation, not a remote cancel-siren command. |
| Independent KWS evidence | `kws_alert_dual.py:725` `DetectionDispatcher`: `last_tulong_by_source`, cooldown-before-state mutation and no-op `note_vosk_text`; independent Snowboy/openWakeWord help survives Vosk hints/revisions/rejection. Same-engine correlation and per-keyword cooldown remain. |
| Resident real/manual alert | `main.py:2800` `/api/alerts/manual` delegates to the same durable API; `lib/services/resident_alert_service.dart` retains one ID across retries and sends bearer headers. |
| Resident test-event commands | **Absent** from current backend route/schema definitions. No dedicated Resident test command or command acknowledgement contract exists here. |
| Test/real classification | **Absent as an explicit event contract.** `AlertIn`/`ManualAlertIn` declare no test flag, and the classifier has no test branch. `source='manual_button'` explicitly classifies as a real critical emergency. |
| Remote mute gate/control | **Absent**, including a disabled-by-default runtime gate, lease schema, command ledger, owner/session revision or mute endpoint. Unsupported is not an implemented gate set to false. |
| KWS recognition mute integration | **Absent** from dispatcher/workers/main loop. No remote command currently changes recognition state. Noise suppression settings are not recognition mute. |
| Restart recovery | Durable event/envelope/ACK and KWS outbox code exists and is covered by synthetic restart tests. No remote-mute recovery implementation exists to certify. |

The registry docstring still describes persistence as deferred. That comment is
stale: the actual API performs `AlertStore.lookup` before consulting the registry,
and the store enforces event-ID uniqueness across restarts. No source was edited
just to correct this comment during the reconciliation preflight.

## 3. Windows commit availability

Requested branch: `codex/c158-resident-interoperability`  
Requested commit: `9b4f02305f4040aa27cb7ca666442c644036a38d`

`git cat-file -t` could not resolve that object in the offline/evaluation shared
repository, the production repository, or the workspace repository at `/home/thesis`.
Offline refs only identify the Pi base; no requested Windows branch is present.
A bounded filename search of Downloads, cache, backup and temporary locations found
no supplied Windows bundle/patch. The existing `C1_58-only.patch` is the Pi's prior
reliability patch, not a Windows transfer.

**Windows source is unavailable locally.** No Windows file contents, changed-file
list, ancestry, API names, mute duration or test outcomes are inferred. No fetch,
pull, push, merge or integration checkout was attempted. The user-specified absent
commit path therefore applies; source transfer is the next external prerequisite.

## 4. Overlapping files and conflicts

Actual Windows/Pi overlap and merge conflicts are **not assessable until the
Windows diff/tree arrives**. They are not reported as zero conflicts.

These are Pi-side review boundaries, not claims about what Windows changed:

| Boundary | Preserve when reviewing incoming changes |
|---|---|
| `raspberry_pi/backend/main.py` | Middleware coverage; `AlertIn`/`ManualAlertIn`; stable fingerprint fields; durable lookup before claim; shielded duplicate future; owner-cancellation cleanup; atomic event-row/envelope insertion; no replay regression |
| `raspberry_pi/kws/kws_alert_dual.py` | Exact aliases; all three engine paths; per-source accepted timestamps; no text-only veto; rejected-submission no-op; outbox UUID/auth/retry behavior; existing cooldowns/timers |
| `raspberry_pi/alert_delivery.py`, `raspberry_pi/alert_decision.py` | Per-phone authentication, bound ACK identity/sequence, immutable classifications, 300-second existing critical replay eligibility and independent confirmation |
| `lib/services/resident_alert_service.dart`, `lib/models/alert_event.dart` | Existing manual request and retry IDs; explicit future test-event parsing must agree with persistence, delivery and app presentation |
| `lib/providers/alerts_provider.dart`, `lib/services/alert_delivery_service.dart`, runtime output code | Generation guards, durable inbox/ACKs, active-event identity, superseded-event handling, genuine-emergency presentation |
| Existing and incoming tests/configuration | Retain all Pi tests and Windows compatibility tests; review new same-path files; do not silently overwrite untracked helpers or enable a feature through config defaults |

After transfer, compare Windows versus its declared base and versus Pi HEAD; then
compare each changed path against the preserved dirty Pi bytes. Review both sides'
semantics in a separate temporary checkout/repository. Resolve overlapping hunks
there explicitly and rerun the combined suite before proposing an integration
commit. Do not apply either side over the current dirty tree or choose an entire
file merely to make a textual conflict disappear.

## 5. API contract compatibility

The existing Pi contract is established; compatibility with Windows is **unverified**.

| Existing interface | Current behavior / requirement for Windows review |
|---|---|
| `POST /api/alerts/manual` | Optional `event_id`; defaults `keyword='manual'`, `confidence=1.0`, `source='manual_button'`, `direction='center'`; normal classification/persistence, not a test path |
| `POST /api/alerts` | Server classifies/enriches event. Replies `{ok, duplicate_event, event}`. Same ID/payload returns retained immutable result; conflicting payload returns HTTP 409. |
| Identity | Nonempty stripped string, maximum 128 characters, no control characters; absent ID generates a fresh UUID for each request. Windows must reuse the same ID and stable payload for retries of one command. |
| Fingerprint | Stable JSON of the submitted payload excluding `event_id`, `type`, `server_generated_event_id`; changes to future test/command metadata must participate in conflict detection as appropriate. |
| HTTP authorization | `Authorization: Bearer ...` in required mode. No Resident-specific identity/role or restricted command permission exists; the current shared API token also protects broader control routes. |
| `/ws/alerts?protocol=2` | Authenticate control frame with protocol version 2, installation ID and per-phone token. Then replay requests carry cursor and instance; ACKs carry event ID and sequence and must not spoof another caregiver. |
| Alert replay | Full retained envelope, sequence and persisted time; per-caregiver dispositions survive restart. Existing emergency replay must remain available after a test event or optional control session ends. |
| Remote cancel/test/mute APIs | No such dedicated interfaces in this tree. Their Windows paths, payloads, status codes, feature negotiation and authorization scopes cannot yet be reviewed. |

The new manual-route contract check uses actual extracted API/store/registry and
model class bodies with the existing fake BaseModel fixture. It verifies route
logic and durable effects, **not real Pydantic input validation or real HTTP**.
Real ASGI tests require the unavailable optional dependencies.

## 6. Mute and safety contract findings

| Required safety property | Finding |
|---|---|
| Resident commands require authorization | **Conditional for existing manual commands:** verified in `required`/locked modes. Acknowledged open mode bypasses auth. New Resident command authorization/roles are absent and cannot be certified. Integration acceptance must include unauthenticated, wrong-token and wrong-role rejection for every new command. |
| Test events distinguishable from real alerts | **Not implemented.** Never use the current manual HELP endpoint for a live test: its default source is a real critical emergency and can be durably replayed. An incoming explicit test marker must survive request validation, fingerprint, stored envelope, replay and both apps' display/output policies. |
| Duplicate commands cannot duplicate sirens | **Backend same-ID guarantee verified within tested boundaries:** one immutable row and one hub publication for same manual ID/payload, including conflict and cancellation cases. Missing/new IDs represent separate events. No universal command or physical-siren exactly-once guarantee is claimed. |
| Remote mute disabled by default | No remote mute implementation or gate is present, so this source has no remote mute path to enable. A future implementation must be explicitly gated off by default and fail safely for missing/malformed config. No production setting was read or changed. |
| No invented production mute duration | **Satisfied:** no lease duration, TTL or renewal period was selected. Existing 300-second replay eligibility and Resident retry windows are unrelated and must not be reused as a mute lease. |
| Disconnect cannot leave recognition muted | There is no remote recognition-mute state in this source. Future session ownership, expiry, disconnect, process death and restart behavior remain **unverified**; a client-only unmute message is insufficient. Require backend/KWS enforced recovery to recognition enabled without choosing a duration here. |
| Genuine thermal/alert delivery functional | Existing thermal/classification, publication, outbox and replay regressions pass with synthetic evidence. No new control code can gate/drop genuine alerts until its intended scope and tests are reviewed. Hardware/live delivery is not certified. |
| Existing emergency replay preserved | Current SQLite recovery, replay age/confirmation rules and independent caregiver ACKs are unchanged and pass selected tests. Test commands or mute must not clear real history, mark real events confirmed, reset cursors or block replay. |

Required future mute tests include disabled-gate rejection, authorized acquisition,
duplicate acquisition, stale/reordered renew/release, wrong owner/session,
independent sessions, recognition worker handoff, disconnect, lease expiry,
backend/KWS restart, and recognition resumption. Require an authoritative command
identity/revision and explicit state acknowledgements consistent with reviewed
Windows code; no wire format or ordering policy is invented here.

The existing C1.58 limitations remain: publication after a committed row can be
interrupted; protocol-v2 SQLite polling/replay recovers it, but legacy transient
hub delivery is not an exactly-once guarantee. Threaded insertion can continue
after cancellation. Classification/history/publication are not one transaction.
Independent cross-engine evidence can create separate `tulong`/`help` events from
one sound; source preservation is not acoustic episode deduplication.

The earlier Flutter replay candidate remains visible: the provider's reliable
delivery `isActive` callback checks the current active ID but not retained
`_supersededAlertIds`. Recreate-delivery/replay A+B while B is active still needs
the targeted Flutter reproduction and correction described in C1.58. Nothing in
the current Python run certifies that app lifecycle.

## 7. Actual regression results and limits

All completed results below are from this preflight, using the current offline Pi
source. Logs, JSON counts and exact selections are in the checkpoint directory.

| Completed invocation | Passed | Failed | Errors | Skipped | Expected failures | Unexpected successes |
|---|---:|---:|---:|---:|---:|---:|
| `run_preflight.py baseline` — retained selected Pi baseline | 333 | 0 | 0 | 0 | 0 | 0 |
| `run_preflight.py pi-plus-contract` — all prior 351 + 12 new contract cases in one run | **363** | **0** | **0** | **0** | **0** | **0** |
| `run_preflight.py optional-asgi` — existing real HTTP/WebSocket suite | 0 | 0 | 0 | **16** | 0 | 0 |
| Combined Windows/Pi regression | **Not run: Windows source unavailable** | — | — | — | — | — |

Baseline and expanded rows overlap; do not add them as distinct test coverage.
The 363 run includes the exact previous 351-test selection, unchanged, plus five
auth/middleware checks and seven direct API/protocol contract checks. The earlier
351 software fixes and their tests are preserved, not replaced by a smaller suite.

Coverage includes independent Snowboy/openWakeWord/Vosk arrival order and hint
revision, accepted-source correlation windows, rejected cooldown submissions,
HTTP owner/waiter cancellation, continued threaded insertion, same-ID conflicts,
SQLite migration/envelopes/restart, 205-row bounded replay, caregiver-independent
ACKs, replay eligibility, real manual alert ID retries, auth rejection and stale
session/replay/ACK handling. The twelve new cases use actual extracted Pi code,
synthetic credential verifiers, synthetic SQLite and in-memory WebSockets.

Execution evidence:

- `baseline.log` / `baseline.json`: 333 tests, 13.839 seconds, success.
- `pi-plus-contract.log` / `pi-plus-contract.json`: 363 tests, 21.636 seconds, success.
- `optional-asgi.log` / `.json`: 16 tests skipped because FastAPI/HTTPX/Starlette and
  related optional HTTP dependencies are absent from the selected interpreter.
- `test_c158_int_contract.py`, `run_preflight.py`, `run_validation.sh`: exact new
  review tests and commands. These are retained review artifacts outside the worktree.

Initial sandboxed attempts stalled in asynchronous thread completion. Two were
interrupted (exit 130); two diagnostic attempts timed out (exit 124). They did not
produce completed test totals and are **not passes, expected failures or skipped
tests**. The timed attempt logs and `sandbox-attempts.json` retain this distinction.
The same guarded test commands completed outside the sandbox through explicit
tool escalation. No application fix was made to bypass a failing assertion.

The harness redirects temporary fixture directories to an isolated `/tmp` tree,
turns off bytecode, and rejects network connections/address resolution,
subprocess/system calls, production/evaluation file opens, native model/audio
reads, hardware device paths and SQLite outside the synthetic fixture tree.
Original test and application source is read directly from the offline worktree.
No startup/lifespan, live backend, native inference or physical output is run.

The ASGI dependencies were not downloaded. Flutter/Dart are unavailable on PATH
and the checked usual SDK paths; no Flutter suite was run and no Flutter skip
count is invented. The backup-CLI subprocess test and broader unrelated repository
suites remain outside the selected regression scope. New test-event delivery,
recognition-mute transitions and stale/reordered mute commands cannot be exercised
as implemented features because their source is absent. Passing existing tests
does not close those gaps.

## 8. Required Windows source transfer and verification

These are **handoff instructions for later execution**, not commands performed in
this preflight. Transfer source only, never credentials, live databases, private
audio or model datasets. No automatic remote Git operation is requested.

### Minimum acceptable transfer

Preferred: a self-contained Git bundle of the exact Windows branch frozen at the
requested commit, plus its SHA-256, reviewed change list and API/config/test notes.
This retains commit/tree identity and ancestors even when Pi history is shallow.

Alternative: a reviewed **cumulative binary/full-index patch from the exact Pi base
`8a44f109fae8adb4b7daa833c15548b56ccd2452` to the target commit**, including all
prerequisite commits and tests. A single `git show 9b4f023` or a list of copied
Flutter files is insufficient unless review establishes there are no prerequisites.
Supply base/target IDs, target tree ID, file-change list, diff statistics, patch
SHA-256, review notes and test logs. A patch reproduces source differences; by
itself it cannot cryptographically establish the originating commit object.
If Windows does not contain the exact Pi base, use the self-contained bundle and
state that fact; do not invent a common base or substitute the production HEAD.

### Windows export (PowerShell, no fetch/pull/push/merge)

Run in the Windows repository. Select a new empty export directory first:

```powershell
$target = '9b4f02305f4040aa27cb7ca666442c644036a38d'
$branch = 'codex/c158-resident-interoperability'
$piBase = '8a44f109fae8adb4b7daa833c15548b56ccd2452'
$out = 'C:\C1_58_INT_transfer'  # new empty local directory
New-Item -ItemType Directory -Path $out -ErrorAction Stop
git status --short
$tip = git rev-parse --verify $branch
if ($LASTEXITCODE -ne 0 -or $tip.Trim() -ne $target) { throw 'Unexpected branch tip; stop and review' }
git cat-file -e "${target}^{commit}"
if ($LASTEXITCODE -ne 0) { throw 'Target commit unavailable' }
git show --no-patch --format=fuller $target | Set-Content -Encoding utf8 "$out\commit.txt"
git rev-parse "${target}^{tree}" | Set-Content -Encoding ascii "$out\target-tree.txt"
git bundle create "$out\windows-9b4f023.bundle" $branch
if ($LASTEXITCODE -ne 0) { throw 'Bundle export failed; do not transfer' }
git bundle verify "$out\windows-9b4f023.bundle"
if ($LASTEXITCODE -ne 0) { throw 'Bundle verification failed' }
Get-FileHash -Algorithm SHA256 "$out\windows-9b4f023.bundle"
```

The commit export excludes uncommitted Windows files. Review any dirty status and
identify omissions explicitly. Do not stash/reset/clean them. Reviewers must receive
the full relevant committed changes and their tests. If this is a shallow Windows
repository and the bundle needs missing prerequisites, supply the reviewed cumulative
patch against the exact available Pi base or a complete bundle from an already
complete local repository; do not fetch automatically to make the export succeed.

If the exact Pi base exists on Windows, also produce the reviewable patch and list:

```powershell
git cat-file -e "${piBase}^{commit}"
if ($LASTEXITCODE -ne 0) { throw 'Pi base unavailable: provide bundle instead' }
git diff --binary --full-index --no-ext-diff --no-renames --output="$out\windows-from-pi-base.patch" $piBase $target
if ($LASTEXITCODE -ne 0) { throw 'Patch export failed' }
git diff --name-status --no-renames $piBase $target | Set-Content -Encoding utf8 "$out\changed-files.txt"
git diff --stat $piBase $target | Set-Content -Encoding utf8 "$out\diff-stat.txt"
Get-FileHash -Algorithm SHA256 "$out\windows-from-pi-base.patch"
```

Use Git's `--output` for patch bytes; avoid PowerShell text redirection/encoding
conversion of the patch. Record the hashes with the review/handoff. Transfer the
export directory using the approved file-transfer channel or removable media into
a **new** directory under `/home/thesis/offline-work-backups/C1_58_INT_incoming/`.
Compare hashes with the sender's separately communicated values before any use.
Do not place transferred files in production or evaluation.

### Pi-side verification and isolated review after receipt

Examples below assume the transferred files exist; the quoted directory is a
future handoff location, not evidence of a transfer already received:

```bash
sha256sum /home/thesis/offline-work-backups/C1_58_INT_incoming/windows-9b4f023.bundle
git -C /var/tmp/Project_Pi_C1_43_alarm_fix bundle verify /home/thesis/offline-work-backups/C1_58_INT_incoming/windows-9b4f023.bundle
git bundle list-heads /home/thesis/offline-work-backups/C1_58_INT_incoming/windows-9b4f023.bundle
```

The bundle's named branch must resolve to the exact target SHA. A prerequisite
failure must be reported, not repaired through a fetch. For later source review,
create a fresh isolated repository from that **local bundle** with `git clone
--no-checkout <bundle> <new-temporary-directory>`; do not import it into the
shared offline/evaluation Git directory. Verify `rev-parse <target>`, its tree ID,
`show --no-patch`, `fsck --full`, and the complete declared-base-to-target diff
there before checking out reviewed source. This local-bundle clone is a future
review step, not a remote fetch or an operation executed in this task.

For patch-only transfer, first verify the hash and exact base availability; inspect
`git apply --stat` and `git apply --summary`, paths, binary additions and deletions.
Use `git apply --check` only in a separate temporary checkout at the declared base.
Review the Windows patch there alongside the Pi checkpoint's `tracked-changes.patch`
and all raw untracked files. A clean apply at the base does **not** prove it applies
over the dirty Pi source or is API/safety compatible. Only after explicit source
review should the combined temporary candidate be assembled and tested. No blanket
file-copy overwrite, automatic merge or deployment is part of this preflight.

## 9. Integration blockers

1. Exact Windows commit/tree/diff, prerequisite history and its tests have not been
   transferred; API compatibility and actual overlapping hunks remain unknown.
2. The available Pi source lacks Resident test-event classification/commands and
   remote-mute gate, lease, command ordering and KWS recognition-state integration.
   Whether Windows implements these cannot be inferred from its branch name.
3. Authorized command scope must be specified and tested, including acknowledged
   open mode and separation between caregiver delivery credentials and Resident
   command permissions. Current bearer possession is not a distinct Resident role.
4. No reviewed production mute lease policy exists in the available material. No
   duration is proposed; remote mute must remain disabled through integration.
5. Real ASGI optional dependencies and Flutter/Dart tooling are unavailable;
   deterministic Python protocol tests do not replace those full-stack checks.
6. Existing Flutter superseded-ID replay risk and C1.58's documented policy/acoustic
   limitations remain. No physical notification, acoustic accuracy or live hardware
   acceptance has been established by this preflight.

## 10. Deployment prerequisites and final boundary

Before any deployment proposal: receive and verify reviewed Windows source;
reconcile both sides in an isolated candidate; preserve API/auth/fingerprint and
emergency replay contracts; implement/review explicit test classification and the
disabled-by-default mute capability if included; settle the lease/ordering/owner
policy separately; and run an **actual combined Windows/Pi** Python, real ASGI and
Flutter regression with exact passed/failed/error/skipped/expected-failure totals.
Resolve the app replay candidate or document its disposition with deterministic
evidence. Record the final source IDs/diffs, feature defaults and rollback plan.

Production is a different HEAD from the offline base. A later authorized deployment
review must reconcile against its actual deployed source/configuration and arrange
authorized database backup/rollback and hardware acceptance separately. This task
does not read production data or authorize that later work. Keep remote mute off;
do not assume a test label or caregiver pairing alone makes a live test safe.

Final preservation is recorded in `completion-verification.json` in the checkpoint:
all 36 original development files remain byte-identical; tracked changes/staging
remain identical; the report is the sole new offline file; production/evaluation
HEAD, branch and Git status match the initial snapshots. No service restart,
production database access, live microphone/model inference, swap/boot change,
reset, clean, fetch, pull, push, merge or deployment was performed.
