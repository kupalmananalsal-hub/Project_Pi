#!/usr/bin/env bash
# The only supported way to move the Pi checkout to a reviewed commit. Run as thesis,
# from a fresh copy that the runbook extracted with git archive and verified (step 2):
#
#   bash "$V/raspberry_pi/scripts/preupgrade_switch.sh" --repo="$PI_REPO" \
#     --target="$REVIEWED" --backup-dir="$B"
#
# Every check is fatal and runs before git touches the working tree:
#   1. this script, preupgrade_inventory.sh and preupgrade_manifest.sh match the target's
#      blobs (defense in depth; the runbook verifies a fresh copy before running it);
#   1b. the backup DIR was made at the current HEAD (ROLLBACK_COMMIT);
#   2. the target is on origin/main (squash-merge repos: never deploy a PR-branch commit);
#   3. preupgrade_inventory.sh passes for exactly this target (backup verified, no local
#      file the target would overwrite or delete);
#   4. the move is a fast-forward straight to the target tree (no intermediate checkout).
# Then it records the verified target in DIR/PRESWITCH_VERIFIED; install_headless.sh
# --apply refuses unless that names the checked-out HEAD. Nothing is ever reset, cleaned
# or forced.
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO=""
TARGET=""
BACKUP_DIR=""
for arg in "$@"; do
  case "${arg}" in
    --repo=*) REPO="${arg#*=}" ;;
    --target=*) TARGET="${arg#*=}" ;;
    --backup-dir=*) BACKUP_DIR="${arg#*=}" ;;
    *) echo "Unknown option: ${arg}" >&2; exit 2 ;;
  esac
done
if [[ -z "${REPO}" || -z "${TARGET}" || -z "${BACKUP_DIR}" ]]; then
  echo "Usage: $0 --repo=CHECKOUT --target=SHA --backup-dir=DIR" >&2
  exit 2
fi
stop() { echo "STOP: $*; the checkout was not changed." >&2; exit 1; }
git_() { git -C "${REPO}" "$@"; }

TARGET_SHA="$(git_ rev-parse --verify --quiet "${TARGET}^{commit}")" \
  || stop "${TARGET} is not a commit in ${REPO} (git fetch origin first)"
# Defense in depth only: a script cannot vouch for itself once running. The runbook
# extracts and verifies a fresh copy BEFORE invoking it (step 2).
for tool in preupgrade_switch.sh preupgrade_inventory.sh preupgrade_manifest.sh; do
  reviewed="$(git_ rev-parse --verify --quiet "${TARGET_SHA}:raspberry_pi/scripts/${tool}")" \
    || stop "${tool} is not in ${TARGET_SHA}"
  [[ "$(git_ hash-object "${HERE}/${tool}")" == "${reviewed}" ]] \
    || stop "${HERE}/${tool} differs from the reviewed ${tool}"
done
git_ merge-base --is-ancestor "${TARGET_SHA}" origin/main \
  || stop "${TARGET_SHA} is not on origin/main"
# The backup must be of what runs now: an older backup records the wrong rollback commit.
head_now="$(git_ rev-parse HEAD)"
[[ "$(cat "${BACKUP_DIR}/ROLLBACK_COMMIT" 2>/dev/null)" == "${head_now}" ]] \
  || stop "${BACKUP_DIR} was not made at the current HEAD ${head_now}; make a new backup"
bash "${HERE}/preupgrade_inventory.sh" --repo="${REPO}" --target="${TARGET_SHA}" \
  --backup-dir="${BACKUP_DIR}" || stop "the pre-upgrade inventory did not pass"

# Fast-forward to the target in one checkout, onto a main that tracks origin/main.
branch="$(git_ symbolic-ref --quiet --short HEAD || true)"
if [[ "${branch}" == main ]]; then
  git_ merge --ff-only "${TARGET_SHA}" || stop "main cannot fast-forward to ${TARGET_SHA}"
elif git_ show-ref --verify --quiet refs/heads/main; then
  git_ merge-base --is-ancestor main "${TARGET_SHA}" \
    || stop "local main has commits not in ${TARGET_SHA}; back them up and get them reviewed"
  git_ branch -f main "${TARGET_SHA}"  # a fast-forward of an unchecked-out branch
  git_ switch main
else
  git_ switch -c main "${TARGET_SHA}"
fi
git_ branch --set-upstream-to=origin/main main >/dev/null
[[ "$(git_ rev-parse HEAD)" == "${TARGET_SHA}" ]] || stop "HEAD is not ${TARGET_SHA} after the switch"
echo "${TARGET_SHA}" >"${BACKUP_DIR}/PRESWITCH_VERIFIED"
echo "SWITCHED to ${TARGET_SHA} after a passing inventory; recorded in ${BACKUP_DIR}/PRESWITCH_VERIFIED."
