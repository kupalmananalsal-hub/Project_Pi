# C1.58 delivery recovery

Base: 4d04117a340fc99739910b64e60761585ed8c87d.

The c44d849 backend accepts /api/resident/control commands into its transient
Resident test state but does not insert/publish their events into AlertStore.
Current Main uses authenticated /ws/alerts protocol 2 and the durable history API,
so an old backend can accept a tap without delivering it to Main. Actual Pi
revision was not remotely inspected; the reported failed deployments make this
source incompatibility the primary deployment blocker.

The full updated backend includes the 78006b5 persistence-before-publication path:
Resident bearer credential + X-Resident-Id -> sequenced command/gesture ID ->
immutable manual event UUID -> SQLite -> alert publication and protocol-2 live
delivery -> Main notice/emergency and one-shot audio. Linked first-tap and
double-tap events retain an accurate history trail. Existing delivery UUIDs,
durable inbox, acknowledgements and replay controls suppress duplicate handling.

Backend control responses now advertise manual_alert_history_version=1. Resident
checks this before enabling gesture delivery and shows a backend-update message
for old servers, preserving pairing. Disconnected taps do not replace that message.
Reconnect Resident after backend activation. No legacy downgrade or auth bypass.

The keyword notice now reads KEYWORD SPOTTED! directly above RadarCompass in both
responsive layouts. Main receives events continuously; refreshing is unnecessary.
Manual keyword audio remains a single pulse. Manual emergency audio remains one
complete siren clip, with a silent notification channel preventing an added sound.
Audio completion and Resident lifecycle do not close Main's emergency overlay.
Main's own dismiss control closes it and acknowledges; History remains in SQLite.
Resident starts no beep, siren, notification or local emergency overlay.

Installer v3 is prepared separately under Downloads/Project_Pi_C158_PI_DEPLOYMENT/v3.
v2 rejected the second committed model link raspberry_pi/thermal/models. v3 checks
both exact model link names/targets but never creates links from archive content;
it retains existing model paths through the existing inheritance mechanism.
Unknown symlinks, hardlinks, devices, traversal, duplicate/case collisions and
oversized archives remain rejected. Every archive member is checked before payload
files are written. Full source snapshot replaces delta-patch assumptions.

v3 uses new source/state/installer/drop-in paths. It leaves failed v1/v2 staging
and backups intact, selects the effective backend unit/drop-ins, and leaves the
independent KWS service untouched. It preserves the current history DB, pairing
registry, credentials, configuration and models. Remote mute remains disabled.
Rollback removes only its hash-matched backend drop-in; current DBs are never
replaced by older backups. Activation requires manual operator execution.

No suites, pytest, flutter test or flutter analyze were run at user instruction.
Release build and artifact details are in the local handoff. No Pi access,
installation, deployment, push, PR, merge or service restart was performed.
This is source-level repair and build evidence; physical delivery is not certified.
