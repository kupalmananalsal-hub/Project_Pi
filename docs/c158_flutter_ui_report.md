# C1.58-UI — Windows Flutter development report

Date: 2026-11-02 (Asia/Manila).

## Checkout and scope

- Starting worktree: clean `codex/c110-replay-hardening` at
  `75e969aa11a7277a9fbef064366034472e94601f`.
- Dedicated UI branch: `codex/c158-flutter-ui`, created from the existing cached
  `origin/main` at `b6a2a20ded8df62cefb7ef6616710cbfdca140cf`.
- Local `main` was `801629e7101845b496c50d0190f1c6530c68069a`, 28 commits behind
  cached `origin/main`. No fetch, pull, merge or reset was performed.
- Other checkouts and local changes were not overwritten. The replay-hardening
  branch and its commits remain intact. No Pi, restricted audio or holdout access.
- The supplied 351-test backend reliability result was not independently rerun;
  unmerged Pi fixes are not assumed to be present in this cached UI baseline.

## Implemented UI

All four requested removals are complete in the caregiver UI:

1. Removed the PART / None thermal fact tile.
2. Removed the Simulate distress call control and its screen-local POST handler.
3. Removed Training from navigation and the shell's instantiated screens.
4. Removed Refresh KWS Service and its screen-local confirmation/action control.

Navigation is **Monitor | History | Controls**: bottom navigation on compact widths,
a labeled rail at 840 logical pixels and above. Existing Training source/provider
and backend API methods remain available for compatibility but have no shell route.

The UI retains dark Material 3 styling with clearer charcoal surfaces, spacing,
typography, full-size controls and responsive wrapping. Monitor switches to columns
at 720 usable content pixels. It reuses `ThermalDisplay`, honors the selected thermal
color map and preserves pixel selection. Sensor failures, missing streams and
retained thermal imagery have explicit states; unavailable microphone levels are
not presented as measured silence. Pattern selection follows provider state, and
palette options have named/selected semantics and 48-by-48 targets.

The emergency overlay and its dismissal callback remain above all destinations.
Alert delivery, classification, siren/vibration execution, acknowledgement, replay,
history persistence, reconnection and backend APIs were not modified. Settings
connection controls, history clearing confirmation and existing power controls remain.

## Verification actually performed

| Check | Result |
|---|---|
| `flutter doctor -v` | Completed; Android SDK path-with-spaces warning and missing Windows desktop C++ components |
| Flutter / Dart | Installed Flutter 3.44.0 stable / Dart 3.12.0 |
| Android / Java | SDK 36.1.0, build tools 36.1.0; existing NDKs available; JDK 21.0.12 |
| `flutter pub get` | Passed, existing lockfile retained; no dependency upgrade |
| Original Flutter test baseline | 77 passed |
| Final `flutter analyze --no-pub` | No issues found |
| Final `flutter test --no-pub --reporter expanded` | **86 passed, 0 failed, 0 skipped** |
| C158 widget tests | **9 passed** |
| `git diff --check` | Passed |
| Protected code comparison | No changes to providers, services, Android configuration, dependencies or Raspberry Pi source |

New widget checks cover requested removals, three-tab/rail navigation, 320/900-wide
layouts at 1.6x text scale, connecting/unavailable/live/error sensor states, configured
thermal color map and pixel selection, critical overlay dismissal from Controls,
retained alert history, externally changed light patterns and accessible palette size.
Device polling and emergency outputs are mocked in the new fixtures.

Ten local PNG captures use synthetic widget data and installed SDK Roboto/icon fonts:
phone/tablet Monitor, History and Controls, live Monitor, sensor failures, critical
overlay and populated History. A separate-agent source/render review identified
three material issues (failed sensors appearing live, stale compact pattern selection,
small unnamed palette targets); all three were fixed and scored resolved on recapture.
These renders are **not Android emulator or physical-device screenshots**. No emulator
or Android device was available/configured; no installation or physical validation occurred.

## APK and signing

- Build: **succeeded**, `flutter build apk --release --no-pub`.
- Output relative to this worktree: `build/app/outputs/flutter-apk/app-release.apk`.
- Size: 56,316,573 bytes (Flutter reports 53.7 MB).
- APK SHA-256: `4df5e7c52f94add7f45c0349d2e11ddf0e778ace76231562efad49d4831961a8`.
- Verified package ID: `com.projectpi.thermalalert`, unchanged.
- Version: `1.0.0`, versionCode `1`, unchanged.
- APK signature verification passed. Certificate SHA-256:
  `7276f472aaef988c4112c54b5ef6d5487e532bdfab9e7f9c66612a053b9b310c`.
  It matches the existing debug keystore and prior local release APK.
- Existing release configuration uses the debug signing key. This is a compatible
  **development release artifact**, not production signing certification. No key,
  password, application ID or signing configuration was changed or added to Git.

The initial build failed before compilation with Java's
`Unable to establish loopback connection` / UnixDomainSockets `Invalid argument`.
An isolated `Selector.open()` probe succeeded with a short socket directory. The
successful build used only this process-local override:

```powershell
New-Item -ItemType Directory -Force -Path 'C:\Temp\ProjectPiC158' | Out-Null
$env:JAVA_TOOL_OPTIONS = '-Djdk.net.unixdomain.tmpdir=C:\Temp\ProjectPiC158'
flutter build apk --release --no-pub
```

No global Java/SDK configuration was modified. The property is documented in
[Oracle's Java 21 networking properties](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/doc-files/net-properties.html).
Build output retains existing Kotlin-plugin migration and SDK XML-version warnings;
those dependencies/tooling were not upgraded as part of this UI task.

## Exact source/document change list

- `.impeccable/design.json` — native design metadata.
- `DESIGN.md` — source-derived visual tokens and conventions.
- `docs/c158_flutter_ui_report.md` — this report.
- `lib/main.dart` — Material theme refinements.
- `lib/screens/app_shell.dart` — three destinations and adaptive navigation.
- `lib/screens/controls_screen.dart` — removed service refresh, responsive actions.
- `lib/screens/history_screen.dart` — wrapping header and empty state.
- `lib/screens/monitor_screen.dart` — compact responsive monitoring and removals.
- `lib/widgets/app_page.dart` — shared scrolling/content width.
- `lib/widgets/connection_indicator.dart` — clear connection/loading indicator.
- `lib/widgets/led_control.dart` — responsive controlled pattern selection and targets.
- `lib/widgets/radar_compass.dart` — compact size support.
- `lib/widgets/thermal_display.dart` — theme typography for the waiting state.
- `test/c158_ui_test.dart` — nine synthetic UI regression/render checks.
- `test/monitor_voice_keyword_test.dart` — accurate offline/live UI expectations.
- `test/widget_test.dart` — updated removed-control and waiting-state assertions.

## Integration and GitHub readiness

The focused UI changes are ready for source review. No automatic push, Draft PR,
merge or deployment was performed, as requested. APKs and local rendered evidence
remain outside tracked source. The existing PRs and backend development branches
were not changed.

Before release, test installation/update with the intended Android device and signing
identity, real notification/audio/vibration execution, acknowledgement, populated
history, background reconnection/replay, safe-area/Back/TalkBack behavior, font scaling
and real thermal/microphone error recovery. Compare against the separately reviewed
backend fixes before integrated testing. Passing mocks and widget renders do not
certify the Pi, sensors or rescue-detection accuracy.
