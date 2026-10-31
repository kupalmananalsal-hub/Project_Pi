#!/usr/bin/env bash
# Read-only pre-upgrade gate. Run as thesis from the checkout after preupgrade_backup.sh:
#
#   bash raspberry_pi/scripts/preupgrade_inventory.sh --target=<reviewed SHA> --backup-dir=DIR
#
# Writes nothing. Exit 0 only when: tracked files have no local edits; every protected
# asset (raspberry_pi/config/protected_assets.txt) exists, is not tracked by the target
# commit (a checkout could then overwrite it) and has a verified backup in DIR. Other
# local, ignored or untracked files (datasets, recordings, models) are only reported.
# Never follow a failure with git clean, reset --hard or checkout -f.
set -Eeuo pipefail

TARGET=""
BACKUP_DIR=""
for arg in "$@"; do
  case "${arg}" in
    --target=*) TARGET="${arg#*=}" ;;
    --backup-dir=*) BACKUP_DIR="${arg#*=}" ;;
    *) echo "Unknown option: ${arg}" >&2; exit 2 ;;
  esac
done
if [[ -z "${TARGET}" || -z "${BACKUP_DIR}" ]]; then
  echo "Usage: $0 --target=SHA --backup-dir=DIR" >&2
  exit 2
fi

REPO="$(git rev-parse --show-toplevel)"
MANIFEST="${PROJECT_PI_PROTECTED_ASSETS:-${REPO}/raspberry_pi/config/protected_assets.txt}"
PYTHON="${PYTHON:-python3}"
if ! TARGET_SHA="$(git -C "${REPO}" rev-parse --verify --quiet "${TARGET}^{commit}")"; then
  echo "FAIL     --target=${TARGET} is not a commit here (fetch it first)." >&2
  exit 1
fi
echo "Inventory of ${REPO} at $(git -C "${REPO}" rev-parse HEAD) for target ${TARGET_SHA}"

failures=0
fail() { echo "FAIL     $*"; failures=$((failures + 1)); }

edits="$(git -C "${REPO}" status --porcelain --untracked-files=no)"
if [[ -n "${edits}" ]]; then
  fail "tracked files have local edits:"
  printf '           %s\n' "${edits}"
fi

declare -A PROTECTED=()
sums="${BACKUP_DIR}/SHA256SUMS"
if [[ ! -f "${sums}" ]] || ! (cd "${BACKUP_DIR}" && sha256sum --quiet -c SHA256SUMS >/dev/null 2>&1); then
  fail "${sums} missing, or a backup copy changed since it was made"
fi
while IFS= read -r path; do
  [[ -z "${path}" || "${path}" == \#* ]] && continue
  PROTECTED["${path}"]=1
  live="${REPO}/${path}"
  copy="${BACKUP_DIR}/${path}"
  if [[ ! -f "${live}" ]]; then
    fail "${path}: missing (correct the manifest after checking the Pi)"
    continue
  fi
  if git -C "${REPO}" cat-file -e "${TARGET_SHA}:${path}" 2>/dev/null; then
    fail "${path}: tracked by the target commit; a checkout would overwrite it"
  fi
  # sha256sum lines: 64 hex, a space, then " " or "*" (binary mode), then the path.
  if [[ ! -f "${copy}" ]] || ! cut -c67- "${sums}" 2>/dev/null | grep -qxF -- "${path}"; then
    fail "${path}: no recorded backup in ${BACKUP_DIR}"
    continue
  fi
  if [[ "${path}" == *.db ]]; then
    # A live WAL database keeps changing: check the snapshot, never the live hash.
    check="$("${PYTHON}" -c 'import sqlite3, sys; c = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True); print(c.execute("PRAGMA integrity_check").fetchone()[0])' "${copy}" 2>&1 || true)"
    if [[ "${check}" != ok ]]; then
      fail "${path}: backup snapshot integrity_check returned ${check}"
      continue
    fi
    echo "OK       ${path} (snapshot integrity ok, hash recorded)"
  elif [[ "$(sha256sum <"${live}")" != "$(sha256sum <"${copy}")" ]]; then
    fail "${path}: changed since the backup; back it up again"
  else
    echo "OK       ${path} (backup hash matches)"
  fi
done <"${MANIFEST}"

# Everything else local is reported, never blocking: datasets, recordings, models.
while IFS= read -r line; do
  path="${line:3}"
  [[ -n "${path}" && -z "${PROTECTED[${path}]:-}" ]] || continue
  echo "WARN     untracked, not in the manifest: ${path}"
done < <(git -C "${REPO}" status --porcelain --untracked-files=all)
while IFS= read -r line; do
  path="${line:3}"
  [[ "${line:0:2}" == '!!' && -z "${PROTECTED[${path}]:-}" ]] || continue
  echo "LOCAL    ignored: ${path}"
done < <(git -C "${REPO}" status --porcelain --ignored --untracked-files=normal)

if [[ "${failures}" -ne 0 ]]; then
  echo "BLOCKED: ${failures} check(s) failed; do not upgrade. Nothing was changed."
  exit 1
fi
echo "PASS: protected assets present, not tracked by ${TARGET_SHA}, backups verified."
