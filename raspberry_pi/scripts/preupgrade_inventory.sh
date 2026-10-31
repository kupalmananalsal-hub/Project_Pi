#!/usr/bin/env bash
# Read-only pre-upgrade gate. Run as thesis after preupgrade_backup.sh:
#
#   bash <tools>/raspberry_pi/scripts/preupgrade_inventory.sh --repo=~/Project_Pi \
#     --target=<reviewed SHA> --backup-dir=DIR
#
# Writes nothing (git runs without optional locks). Exit 0 only when: the backup is
# intact (SHA256SUMS, including the manifest it was made with); that manifest passes
# preupgrade_manifest.sh (all four mandatory assets, each once, contained relative paths,
# no symlinks, no unconfirmed entries); tracked files have no local edits; every
# protected asset exists and has a verified backup inside DIR; and no local untracked or ignored file (protected or
# not: models, datasets, recordings) sits at, or inside, a path the target commit
# tracks, since a normal checkout overwrites or deletes such files. Other local files
# are only reported. install_headless.sh --apply runs this same gate itself.
# Never follow a failure with git clean, reset --hard or checkout -f.
set -Eeuo pipefail
export GIT_OPTIONAL_LOCKS=0
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=preupgrade_manifest.sh
source "${HERE}/preupgrade_manifest.sh"

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
PYTHON="${PYTHON:-python3}"
git_() { git -C "${REPO}" -c core.quotePath=false "$@"; }

failures=0
fail() { echo "FAIL     $*"; failures=$((failures + 1)); }
block() {
  echo "BLOCKED: ${failures} check(s) failed; do not upgrade. Nothing was changed."
  exit 1
}

if ! TARGET_SHA="$(git_ rev-parse --verify --quiet "${TARGET}^{commit}")"; then
  fail "--target=${TARGET} is not a commit in ${REPO} (fetch it first)"
  block
fi
echo "Inventory of ${REPO} at $(git_ rev-parse HEAD) for target ${TARGET_SHA}"

# 1. The backup and the manifest it was made with, unchanged since.
MANIFEST="${BACKUP_DIR}/protected_assets.txt"
if [[ ! -f "${BACKUP_DIR}/SHA256SUMS" || ! -f "${MANIFEST}" ]] \
    || ! (cd "${BACKUP_DIR}" && sha256sum --quiet -c SHA256SUMS >/dev/null 2>&1) \
    || ! cut -c67- "${BACKUP_DIR}/SHA256SUMS" | grep -qxF protected_assets.txt; then
  fail "${BACKUP_DIR}: not a complete backup from preupgrade_backup.sh, or changed since"
  block
fi
if ! problems="$(read_manifest "${MANIFEST}" "${REPO}" 2>&1 >/dev/null)"; then
  while IFS= read -r line; do fail "${line}"; done <<<"${problems}"
  block
fi
entries="$(read_manifest "${MANIFEST}" "${REPO}")"
BACKUP_REAL="$(cd "${BACKUP_DIR}" && pwd -P)"

# 2. Tracked files unedited.
edits="$(git_ status --porcelain --untracked-files=no)"
if [[ -n "${edits}" ]]; then
  fail "tracked files have local edits:"
  printf '           %s\n' "${edits}"
fi

# 3. Protected assets present and backed up.
declare -A PROTECTED=()
while read -r role path; do
  PROTECTED["${path}"]=1
  live="${REPO}/${path}"
  copy="${BACKUP_DIR}/${path}"
  # sha256sum lines: 64 hex, a space, then " " or "*" (binary mode), then the path.
  if [[ ! -f "${copy}" || -L "${copy}" ]] \
      || ! cut -c67- "${BACKUP_DIR}/SHA256SUMS" | grep -qxF -- "${path}"; then
    fail "${path}: no recorded backup in ${BACKUP_DIR}"
    continue
  fi
  if [[ "$(cd "$(dirname "${copy}")" && pwd -P)/" != "${BACKUP_REAL}/"* ]]; then
    fail "${path}: backup copy resolves outside ${BACKUP_DIR}"
    continue
  fi
  if [[ "${role}" == alerts_db ]]; then
    # A live WAL database keeps changing: check the snapshot, never the live hash.
    check="$("${PYTHON}" -c 'import pathlib, sqlite3, sys; c = sqlite3.connect(pathlib.Path(sys.argv[1]).resolve().as_uri() + "?mode=ro", uri=True); print(c.execute("PRAGMA integrity_check").fetchone()[0])' "${copy}" 2>&1 || true)"
    if [[ "${check}" != ok ]]; then
      fail "${path}: backup snapshot integrity_check returned ${check##*$'\n'}"
      continue
    fi
    echo "OK       ${path} (snapshot integrity ok, hash recorded)"
  elif [[ "$(sha256sum <"${live}")" != "$(sha256sum <"${copy}")" ]]; then
    fail "${path}: changed since the backup; back it up again"
  else
    echo "OK       ${path} (backup hash matches)"
  fi
done <<<"${entries}"

# 4. Every local untracked or ignored file against the target's tracked paths: same
# path (overwritten) or inside a path the target tracks as a file (deleted).
collisions="$(awk 'NR == FNR { tracked[$0] = 1; next }
  { path = $0
    while (path != "") {
      if (path in tracked) { print $0; break }
      if (index(path, "/") == 0) break
      sub(/\/[^\/]*$/, "", path)
    } }' <(git_ ls-tree -r --name-only "${TARGET_SHA}") <(git_ ls-files --others))"
if [[ -n "${collisions}" ]]; then
  while IFS= read -r path; do
    fail "${path}: local file at a path ${TARGET_SHA:0:12} tracks; a checkout would overwrite or delete it"
  done <<<"${collisions}"
fi

# 5. Everything else local is reported, never blocking.
while IFS= read -r path; do
  [[ -n "${path}" && -z "${PROTECTED[${path}]:-}" ]] || continue
  echo "WARN     untracked, not in the manifest: ${path}"
done < <(git_ ls-files --others --exclude-standard)
while IFS= read -r line; do
  path="${line:3}"
  [[ "${line:0:2}" == '!!' && -z "${PROTECTED[${path}]:-}" ]] || continue
  echo "LOCAL    ignored: ${path}"
done < <(git_ status --porcelain --ignored --untracked-files=normal)

if [[ "${failures}" -ne 0 ]]; then
  block
fi
echo "PASS: backup ${BACKUP_DIR} verified for ${TARGET_SHA}; no local file collides."
