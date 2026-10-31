#!/usr/bin/env bash
# Authorized pre-upgrade step: copy every protected asset into a NEW backup directory.
# Run as thesis from the checkout, before preupgrade_inventory.sh:
#
#   bash raspberry_pi/scripts/preupgrade_backup.sh --backup-dir=~/project-pi-backups/pre-<date>
#
# It writes only inside --backup-dir (which must not exist yet) and never touches the
# checkout. A live SQLite database (WAL) is copied with SQLite's online backup API,
# which gives a consistent snapshot, then checked with PRAGMA integrity_check; other
# files are copied with cp -a. SHA256SUMS records the hashes of the copies. Backups
# stay on the Pi or offline media, never in git.
set -Eeuo pipefail

BACKUP_DIR=""
for arg in "$@"; do
  case "${arg}" in
    --backup-dir=*) BACKUP_DIR="${arg#*=}" ;;
    *) echo "Unknown option: ${arg}" >&2; exit 2 ;;
  esac
done
if [[ -z "${BACKUP_DIR}" ]]; then
  echo "Usage: $0 --backup-dir=DIR (a new directory)" >&2
  exit 2
fi
if [[ -e "${BACKUP_DIR}" ]]; then
  echo "Refusing: ${BACKUP_DIR} already exists; use a new directory." >&2
  exit 2
fi

REPO="$(git rev-parse --show-toplevel)"
MANIFEST="${PROJECT_PI_PROTECTED_ASSETS:-${REPO}/raspberry_pi/config/protected_assets.txt}"
PYTHON="${PYTHON:-python3}"

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"
git -C "${REPO}" rev-parse HEAD >"${BACKUP_DIR}/ROLLBACK_COMMIT"
failed=0
while IFS= read -r path; do
  [[ -z "${path}" || "${path}" == \#* ]] && continue
  src="${REPO}/${path}"
  dest="${BACKUP_DIR}/${path}"
  if [[ ! -f "${src}" ]]; then
    echo "FAIL     ${path}: missing (correct the manifest after checking the Pi)" >&2
    failed=1
    continue
  fi
  mkdir -p "$(dirname "${dest}")"
  if [[ "${path}" == *.db ]]; then
    result="$("${PYTHON}" - "${src}" "${dest}" <<'PY'
import sqlite3, sys
source = sqlite3.connect(sys.argv[1])  # the backup API only reads the source
target = sqlite3.connect(sys.argv[2])
source.backup(target)
target.execute("PRAGMA journal_mode=DELETE")  # a self-contained single-file snapshot
print(target.execute("PRAGMA integrity_check").fetchone()[0])
target.close()
source.close()
PY
)"
    if [[ "${result}" != ok ]]; then
      echo "FAIL     ${path}: snapshot integrity_check returned ${result}" >&2
      failed=1
      continue
    fi
    echo "SNAPSHOT ${path} (SQLite backup API, integrity_check ok)"
  else
    cp -a "${src}" "${dest}"
    echo "COPY     ${path}"
  fi
  (cd "${BACKUP_DIR}" && sha256sum -- "${path}" >>SHA256SUMS)
done <"${MANIFEST}"

if [[ "${failed}" -ne 0 ]]; then
  echo "Backup INCOMPLETE in ${BACKUP_DIR}: do not upgrade." >&2
  exit 1
fi
echo "Backup written to ${BACKUP_DIR}; verify it with preupgrade_inventory.sh."
