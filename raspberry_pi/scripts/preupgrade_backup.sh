#!/usr/bin/env bash
# Authorized pre-upgrade step: copy every protected asset into a NEW backup directory.
# Run as thesis, with the checkout that is still deployed, from a freshly extracted and
# verified copy of the reviewed tools (docs/m1_m2_upgrade_and_rollback.md, step 0c):
#
#   bash "$V/raspberry_pi/scripts/preupgrade_backup.sh" --repo="$PI_REPO" \
#     --manifest="$T/protected_assets.confirmed.txt" --backup-dir="$B"
#
# The manifest is validated first (preupgrade_manifest.sh: all four mandatory assets,
# each once, contained relative paths, no symlinks, no unconfirmed entries); on any
# problem nothing is created. It writes only inside --backup-dir (which must not exist
# yet) and never touches the checkout. The live SQLite database (WAL) is opened
# read-only (URI mode=ro) and copied with SQLite's online backup API, which gives a
# consistent snapshot, then checked with PRAGMA integrity_check; other files are copied
# with cp -a. The manifest used is copied into the backup, and SHA256SUMS records the
# hashes of every copy. Backups stay on the Pi or offline media, never in git.
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=preupgrade_manifest.sh
source "${HERE}/preupgrade_manifest.sh"
REPO=""
MANIFEST="${HERE}/../config/protected_assets.txt"
BACKUP_DIR=""
for arg in "$@"; do
  case "${arg}" in
    --repo=*) REPO="${arg#*=}" ;;
    --manifest=*) MANIFEST="${arg#*=}" ;;
    --backup-dir=*) BACKUP_DIR="${arg#*=}" ;;
    *) echo "Unknown option: ${arg}" >&2; exit 2 ;;
  esac
done
if [[ -z "${REPO}" || -z "${BACKUP_DIR}" ]]; then
  echo "Usage: $0 --repo=CHECKOUT --backup-dir=NEW_DIR [--manifest=FILE]" >&2
  exit 2
fi
if [[ -e "${BACKUP_DIR}" || -L "${BACKUP_DIR}" ]]; then
  echo "Refusing: ${BACKUP_DIR} already exists; use a new directory." >&2
  exit 2
fi
if ! entries="$(read_manifest "${MANIFEST}" "${REPO}")"; then
  echo "Refusing: ${MANIFEST} is not a complete, confirmed manifest (see above). Nothing" \
    "was written." >&2
  exit 2
fi
PYTHON="${PYTHON:-python3}"

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"
BACKUP_REAL="$(cd "${BACKUP_DIR}" && pwd -P)"
git -C "${REPO}" rev-parse HEAD >"${BACKUP_DIR}/ROLLBACK_COMMIT"
cp "${MANIFEST}" "${BACKUP_DIR}/protected_assets.txt"
(cd "${BACKUP_DIR}" && sha256sum -- ROLLBACK_COMMIT protected_assets.txt >SHA256SUMS)
failed=0
while read -r role path; do
  src="${REPO}/${path}"
  dest="${BACKUP_DIR}/${path}"
  mkdir -p "$(dirname "${dest}")"
  # Validated paths cannot escape; this checks the directory that was actually created.
  if [[ "$(cd "$(dirname "${dest}")" && pwd -P)/" != "${BACKUP_REAL}/"* ]]; then
    echo "FAIL     ${path}: destination resolves outside ${BACKUP_DIR}" >&2
    failed=1
    continue
  fi
  if [[ "${role}" == alerts_db ]]; then
    companions_before="$(ls "${src}"-wal "${src}"-shm 2>/dev/null || true)"
    if ! result="$("${PYTHON}" - "${src}" "${dest}" 2>&1 <<'PY'
import pathlib, sqlite3, sys
# Read-only (mode=ro): never creates a missing database and never writes the database
# file or an existing WAL.
source = sqlite3.connect(pathlib.Path(sys.argv[1]).resolve().as_uri() + "?mode=ro", uri=True)
target = sqlite3.connect(sys.argv[2])
source.backup(target)
source.close()
target.execute("PRAGMA journal_mode=DELETE")  # a self-contained single-file snapshot
print(target.execute("PRAGMA integrity_check").fetchone()[0])
target.close()
PY
)"; then
      result="error: ${result##*$'\n'}"
    fi
    if [[ "${result}" != ok ]]; then
      echo "FAIL     ${path}: snapshot failed or integrity_check returned ${result}" >&2
      failed=1
      continue
    fi
    echo "SNAPSHOT ${path} (read-only SQLite backup API, integrity_check ok)"
    if [[ "$(ls "${src}"-wal "${src}"-shm 2>/dev/null || true)" != "${companions_before}" ]]; then
      # Only when the database was closed: a read-only WAL reader must create these
      # (empty) and cannot remove them. The database file itself is never written.
      echo "NOTE     SQLite created empty ${path}-wal/-shm next to the closed database;" \
        "left in place (deleting files beside a database is never safe); harmless."
    fi
  else
    cp -a "${src}" "${dest}"
    echo "COPY     ${path}"
  fi
  (cd "${BACKUP_DIR}" && sha256sum -- "${path}" >>SHA256SUMS)
done <<<"${entries}"

if [[ "${failed}" -ne 0 ]]; then
  echo "Backup INCOMPLETE in ${BACKUP_DIR}: do not upgrade." >&2
  exit 1
fi
echo "Backup written to ${BACKUP_DIR}; verify it with preupgrade_inventory.sh."
