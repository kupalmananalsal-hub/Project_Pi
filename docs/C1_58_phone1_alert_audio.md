# C1.58 Phone 1 alert presentation

Based on integrated source 78006b562f2da7c68bea4fd94d883cfea806c38f.

Resident sends authenticated commands only. It no longer starts local audio or
opens a local emergency overlay. Single/double tap timing and authorized renewable
mute leases are unchanged. Remote mute remains disabled unless explicitly enabled
with the existing approval, device allowlist, lease bound, and worker acknowledgement.

Main plays a single pulse for a manual keyword event and one complete synthesized
siren clip for a manual emergency event. Manual emergency notifications use a new
silent channel so Android does not add a second sound. Audio completion never
dismisses the full-screen alert. Only Main's local dismissal acknowledges/closes it.
Real detection sound policy is unchanged.

Main hides manual-origin labels in Monitor, History, emergency presentation and
notifications. Actual thermal status remains visible. Origin metadata stays in the
backend; manual events are not changed into ML detections. No dispatch is added.

Backend source requires no changes beyond the existing 78006b5 durable-history
implementation. History remains in SQLite until the operator explicitly clears it;
existing recent-history display/retrieval limits remain. Double taps retain the
existing linked keyword/emergency event trail when the first tap was persisted.

No tests, pytest, Flutter tests or Flutter analysis were run for this change, per
the user's restrictions. Android release compilation is reported separately.
Physical playback, volume, timing, delivery and lifecycle behavior still require
verification on the paired phones. Both phones need the new APKs; replacing only
Main leaves the old Resident's local looping sound in place.

Package IDs and the existing local signing configuration are unchanged. The local
build uses version code 4. No push, merge, installation or Pi deployment is included.
