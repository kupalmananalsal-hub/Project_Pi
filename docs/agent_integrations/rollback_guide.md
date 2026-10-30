# Rollback guide

This change is repository-local. To abandon it before merging, delete its branch
or worktree through your normal reviewed Git workflow; do not force-push a shared
branch. If merged, use a normal revert commit that removes the listed toolkit
files. Neither path changes any Pi, dataset, model, service, driver, user-level
plugin, or global agent setting because this PR creates none.

If a future optional integration is installed manually, record its exact version,
files changed, credentials/endpoint ownership, and vendor uninstall instructions
before enabling it. Disable its runtime configuration first, then remove it using
the vendor-supported uninstaller. Do not delete unknown global directories or
credentials as a rollback shortcut.

For a remote diagnostic trial, set `enabled` back to `false`, revoke the dedicated
key on the Pi if appropriate, and retain the local audit summary privately. Host
keys and private keys must never enter Git history.
