#!/usr/bin/env bash
# Installer for headless Project Pi operation. Run on the Pi as root, from the checkout:
#
#   sudo bash raspberry_pi/scripts/install_headless.sh            # dry run (default): writes nothing
#   sudo bash raspberry_pi/scripts/install_headless.sh --apply    # install units, helpers, sudoers
#
# Options:
#   --restart             with --apply: restart thermal-backend and kws-alert afterwards
#                         (without it no service is restarted; changes apply on next restart)
#   --configure-hotspot   with --apply: write /etc/project-pi/hotspot.env from
#                         PROJECT_PI_HOTSPOT_* (password required) and let the boot script
#                         manage the NetworkManager hotspot profile
#   --accept-env-drift    with --apply: proceed although the venvs differ from
#                         raspberry_pi/requirements/*.lock.txt
#   --rollback-commit=SHA required with --apply: the application commit that ran before
#                         this upgrade (ROLLBACK_COMMIT, or HEAD for a reinstall). If
#                         --apply fails it is reported next to the current HEAD; the
#                         installer never changes the git checkout itself.
#
# It never installs or upgrades packages and never runs nmcli. Every replaced file is
# backed up to /var/lib/project-pi/install-backups/<UTC timestamp>/ first, and a failure
# during --apply rolls back every file and unit change it made. It never overwrites
# anything in /etc/systemd/system/*.service.d/ and never touches dataset/, models,
# alerts.db, recordings, caregiver credentials or other /etc/project-pi/*.env.
set -Eeuo pipefail

MODE=dry-run
RESTART=0
CONFIGURE_HOTSPOT=0
ACCEPT_ENV_DRIFT=0
ROLLBACK_COMMIT=""
for arg in "$@"; do
  case "${arg}" in
    --dry-run) MODE=dry-run ;;
    --apply) MODE=apply ;;
    --restart) RESTART=1 ;;
    --configure-hotspot) CONFIGURE_HOTSPOT=1 ;;
    --accept-env-drift) ACCEPT_ENV_DRIFT=1 ;;
    --rollback-commit=*) ROLLBACK_COMMIT="${arg#*=}" ;;
    *) echo "Unknown option: ${arg}" >&2; exit 2 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash raspberry_pi/scripts/install_headless.sh [--apply]" >&2
  exit 1
fi

# Tests only: install into a scratch directory instead of /. Ownership is then left alone.
ROOT="${PROJECT_PI_INSTALL_ROOT:-}"
OWN=(-o root -g root)
if [[ -n "${ROOT}" ]]; then
  OWN=()
fi

REPO="${PROJECT_PI_REPO:-/home/thesis/Project_Pi}"
SCRIPTS="${REPO}/raspberry_pi/scripts"
SYSTEMD_SRC="${REPO}/raspberry_pi/systemd"
REQUIREMENTS="${REPO}/raspberry_pi/requirements"
SUDOERS_SRC="${REPO}/raspberry_pi/sudoers/project-pi-thesis"
UNIT_DIR="${ROOT}/etc/systemd/system"
HOTSPOT_CONF="${ROOT}/etc/project-pi/hotspot.env"
BACKEND_CONF="${ROOT}/etc/project-pi/backend.env"
THERMAL_DROPIN="${UNIT_DIR}/thermal-backend.service.d/10-local.conf"
LEGACY_VOSK_UNIT=kws-alert-vosk.service
LEGACY_TOKEN=project-pi-local-token
BACKUP_ROOT="${ROOT}/var/lib/project-pi/install-backups"
BACKUP_DIR="${BACKUP_ROOT}/$(date -u +%Y%m%dT%H%M%SZ)"
STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT

echo "Project Pi installer (${MODE}) from ${REPO}"

# The application code is the checkout itself; git runs as its owner, never as root.
REPO_OWNER="$(stat -c %U "${REPO}")"
repo_git() {
  if [[ -n "${ROOT}" || "$(id -un)" == "${REPO_OWNER}" ]]; then
    git -C "${REPO}" "$@"
  else
    runuser -u "${REPO_OWNER}" -- git -C "${REPO}" "$@"
  fi
}
CODE_HEAD_BEFORE="$(repo_git rev-parse HEAD)"
ROLLBACK_SHA=""
if [[ -n "${ROLLBACK_COMMIT}" ]]; then
  if ! ROLLBACK_SHA="$(repo_git rev-parse --verify --quiet "${ROLLBACK_COMMIT}^{commit}")"; then
    echo "--rollback-commit=${ROLLBACK_COMMIT} is not a commit in ${REPO}." >&2
    exit 2
  fi
  echo "CODE       HEAD ${CODE_HEAD_BEFORE}; rollback commit ${ROLLBACK_SHA} (reported, never checked out)"
elif [[ "${MODE}" == "apply" ]]; then
  echo "--apply needs --rollback-commit=SHA: the commit that ran before this upgrade (the" \
    "ROLLBACK_COMMIT recorded in step 0, or HEAD for a reinstall), reported if --apply fails." >&2
  exit 2
else
  echo "CODE       HEAD ${CODE_HEAD_BEFORE}; --apply will need --rollback-commit=SHA"
fi

# 1. Package drift: read-only comparison with the recorded Pi baseline.
ENV_DRIFT=0
check_env() {
  local venv="$1" lock="$2"
  if [[ ! -x "${venv}/bin/python" ]]; then
    echo "ENV  ${venv}: MISSING"
    ENV_DRIFT=1
    return 0
  fi
  if diff -u --label "${lock}" --label "${venv} (pip freeze)" <(sort -f "${lock}") \
      <(PIP_DISABLE_PIP_VERSION_CHECK=1 "${venv}/bin/python" -m pip freeze 2>/dev/null | sort -f); then
    echo "ENV  ${venv}: matches $(basename "${lock}")"
  else
    echo "ENV  ${venv}: DRIFT from $(basename "${lock}") (diff above)"
    ENV_DRIFT=1
  fi
}
check_env "${ROOT}/home/thesis/kws-env" "${REQUIREMENTS}/kws-env.lock.txt"
check_env "${ROOT}/home/thesis/thermal-env-sys" "${REQUIREMENTS}/thermal-env-sys.lock.txt"

# 2. Files to install: "source|destination|mode".
TARGETS=(
  "${SCRIPTS}/pi_refresh.sh|${ROOT}/usr/local/sbin/project-pi-refresh|755"
  "${SCRIPTS}/headless_boot.sh|${ROOT}/usr/local/sbin/project-pi-boot|755"
  "${SCRIPTS}/log_cleanup.sh|${ROOT}/usr/local/sbin/project-pi-log-cleanup|755"
  "${SUDOERS_SRC}|${ROOT}/etc/sudoers.d/project-pi-thesis|440"
)
UNITS=(
  project-pi-boot.service
  project-pi-apt-update.service
  project-pi-apt-update.timer
  project-pi-log-cleanup.service
  project-pi-log-cleanup.timer
  project-pi.target
  thermal-backend.service
  kws-alert.service
  apk-server.service
)
for unit in "${UNITS[@]}"; do
  TARGETS+=("${SYSTEMD_SRC}/${unit}|${UNIT_DIR}/${unit}|644")
done

# Created once, never overwritten: it holds the admin's choice of API auth mode.
if [[ ! -e "${BACKEND_CONF}" ]]; then
  cat >"${STAGE}/backend.env" <<'EOF'
# PROJECT_PI_API_AUTH=open: NO authentication. Every /api and /ws route, including
# refresh, reboot, shutdown, model deploy and alerts, is open to anyone on the network;
# the old app's built-in token is not security. Use open only on an isolated hotspot.
#
# To require a token (new app only: old APKs are then refused), set required, set a
# random token of 16+ characters, restart thermal-backend and kws-alert, and enter
# the token in each phone's Settings:
#   python3 -c 'import secrets; print(secrets.token_hex(32))'
PROJECT_PI_API_AUTH=open
#PROJECT_PI_API_TOKEN=
PROJECT_PI_CAREGIVER_CREDENTIALS=/var/lib/project-pi/backend/caregivers.json
PROJECT_PI_CORS_ORIGINS=http://localhost,http://127.0.0.1
EOF
  TARGETS+=("${STAGE}/backend.env|${BACKEND_CONF}|600")
fi

# Device-specific thermal settings survive the generic unit: seeded once from the unit
# that is installed now, never overwritten afterwards.
if [[ ! -e "${THERMAL_DROPIN}" ]]; then
  installed_env="$(systemctl cat thermal-backend.service 2>/dev/null \
    | grep -E '^Environment=.*(LGPIO_CHIP|THERMAL_HUMAN_MODEL_PATH|THERMAL_HUMAN_MODEL_METADATA_PATH|THERMAL_HUMAN_MODEL_THRESHOLD|THERMAL_REFRESH_HZ|MLX90640_VARIANT)=' || true)"
  {
    echo "# Local, device-specific settings for thermal-backend.service."
    echo "# Created by install_headless.sh on $(date -u +%Y-%m-%d) from the unit installed then;"
    echo "# never overwritten by the installer. Edit here, not in the repo unit."
    echo "[Service]"
    if [[ -n "${installed_env}" ]]; then
      printf '%s\n' "${installed_env}"
    fi
    if ! grep -q 'MLX90640_VARIANT=' <<<"${installed_env}"; then
      echo "# Baseline-preserving, variant not verified: set BAA or BAB once the sensor is identified."
      echo "Environment=MLX90640_VARIANT=unverified"
    fi
    if ! grep -q 'THERMAL_REFRESH_HZ=' <<<"${installed_env}"; then
      echo "# Baseline-preserving: the rate this Pi has run at (previously hard-coded), not a"
      echo "# claim that 4 Hz suits every MLX90640 variant."
      echo "Environment=THERMAL_REFRESH_HZ=4"
    fi
  } >"${STAGE}/10-local.conf"
  TARGETS+=("${STAGE}/10-local.conf|${THERMAL_DROPIN}|644")
fi

if [[ "${CONFIGURE_HOTSPOT}" -eq 1 ]]; then
  if [[ -z "${PROJECT_PI_HOTSPOT_PASSWORD:-}" ]]; then
    echo "--configure-hotspot needs PROJECT_PI_HOTSPOT_PASSWORD (no default is shipped)." >&2
    exit 1
  fi
  HOTSPOT_SSID="${PROJECT_PI_HOTSPOT_SSID:-Teddy}"
  cat >"${STAGE}/hotspot.env" <<EOF
PROJECT_PI_FORCE_HOTSPOT=1
PROJECT_PI_HOTSPOT_SSID=${HOTSPOT_SSID}
PROJECT_PI_HOTSPOT_PASSWORD=${PROJECT_PI_HOTSPOT_PASSWORD}
PROJECT_PI_HOTSPOT_CONNECTION=${HOTSPOT_SSID}
PROJECT_PI_HOTSPOT_STATIC_IPV4=${PROJECT_PI_HOTSPOT_STATIC_IPV4:-10.129.205.32/24}
PROJECT_PI_HOTSPOT_STATIC_GATEWAY=${PROJECT_PI_HOTSPOT_STATIC_GATEWAY:-}
PROJECT_PI_HOTSPOT_STATIC_DNS="${PROJECT_PI_HOTSPOT_STATIC_DNS:-8.8.8.8 8.8.4.4}"
EOF
  TARGETS+=("${STAGE}/hotspot.env|${HOTSPOT_CONF}|600")
fi

# 3. Report NEW / IDENTICAL / CHANGED with a unified diff.
CHANGED=()
for target in "${TARGETS[@]}"; do
  IFS='|' read -r src dest mode <<<"${target}"
  if [[ ! -e "${dest}" ]]; then
    echo "NEW        ${dest} (mode ${mode})"
  elif cmp -s "${src}" "${dest}" && [[ "$(stat -c %a "${dest}")" == "${mode}" ]]; then
    echo "IDENTICAL  ${dest}"
    continue
  else
    echo "CHANGED    ${dest} (mode $(stat -c %a "${dest}") -> ${mode})"
  fi
  CHANGED+=("${target}")
  if [[ "${dest}" == "${HOTSPOT_CONF}" ]]; then
    echo "           (contents not shown: contains the hotspot password)"
  elif [[ -e "${dest}" ]]; then
    diff -u --label "${dest}" --label "${dest} (new)" "${dest}" "${src}" || true
  else
    diff -u --label /dev/null --label "${dest} (new)" /dev/null "${src}" || true
  fi
done
if [[ -e "${THERMAL_DROPIN}" ]]; then
  echo "KEEP       ${THERMAL_DROPIN} (local drop-in; never overwritten)"
fi

ENABLE_UNITS=(project-pi-boot.service project-pi.target thermal-backend.service kws-alert.service
  apk-server.service project-pi-apt-update.timer project-pi-log-cleanup.timer)
echo "ENABLE     ${ENABLE_UNITS[*]}"
echo "MASK       ${LEGACY_VOSK_UNIT} (second ReSpeaker owner; stopped first if running)"
echo "REPORT     thesis-camera.service: enabled=$(systemctl is-enabled thesis-camera.service 2>/dev/null || true)" \
  "active=$(systemctl is-active thesis-camera.service 2>/dev/null || true) (not changed)"
if [[ "${RESTART}" -eq 1 ]]; then
  echo "RESTART    thermal-backend.service kws-alert.service"
else
  echo "RESTART    none (pass --restart to restart thermal-backend and kws-alert)"
fi

# Root sources hotspot.env; both files hold secrets. Reported, never changed here.
for conf in "${HOTSPOT_CONF}" "${BACKEND_CONF}"; do
  if [[ -e "${conf}" ]]; then
    read -r conf_owner conf_mode < <(stat -c '%U %a' "${conf}")
    if [[ "${conf_owner}" != root ]] || (( (8#${conf_mode} & 8#077) != 0 )); then
      echo "WARNING: ${conf} is ${conf_owner}:${conf_mode}; expected root-owned 600" \
        "(fix: sudo chown root:root ${conf} && sudo chmod 600 ${conf})." >&2
    fi
  fi
done

visudo -cf "${SUDOERS_SRC}"
if grep -qs "^PROJECT_PI_API_TOKEN=${LEGACY_TOKEN}\$" "${BACKEND_CONF}"; then
  echo "WARNING: ${BACKEND_CONF} sets the public legacy token; it is never accepted as authentication." >&2
fi

if [[ "${MODE}" != "apply" ]]; then
  echo ""
  echo "Dry run: nothing was changed. Re-run with --apply to install."
  exit 0
fi

# 4. Apply.
if [[ "${ENV_DRIFT}" -eq 1 && "${ACCEPT_ENV_DRIFT}" -ne 1 ]]; then
  echo "Refusing --apply: the virtual environments differ from the lock files (see above)." >&2
  echo "Review the drift, then re-run with --accept-env-drift. Nothing was changed." >&2
  exit 1
fi

# Journal of every change, so a failure part-way through can undo them all.
CREATED=()
REPLACED=()
NEWLY_ENABLED=()
VOSK_FILE_REMOVED=0
VOSK_MASKED=0
RESTART_ATTEMPTED=0
# Prior legacy-unit state, read before anything changes (and before the ERR trap).
VOSK_WAS_ACTIVE=0
VOSK_WAS_ENABLED=0
VOSK_WAS_MASKED=0
if vosk_state="$(systemctl is-enabled "${LEGACY_VOSK_UNIT}")"; then :; fi
case "${vosk_state}" in
  enabled) VOSK_WAS_ENABLED=1 ;;
  masked | masked-runtime) VOSK_WAS_MASKED=1 ;;
esac
if systemctl is-active --quiet "${LEGACY_VOSK_UNIT}"; then
  VOSK_WAS_ACTIVE=1
fi

backup() {
  [[ -e "$1" ]] || return 0
  mkdir -p "${BACKUP_DIR}$(dirname "${1#"${ROOT}"}")"
  cp -a "$1" "${BACKUP_DIR}${1#"${ROOT}"}"
}

ROLLBACK_FAILURES=()
# One restoration step: a failure is recorded, never hidden, and the others still run.
step() {
  local description="$1"
  shift
  if ! "$@"; then
    ROLLBACK_FAILURES+=("FAILED: ${description}")
  fi
}
# One check of the end state: recovery counts only if the result is verified.
check() {
  local description="$1"
  shift
  if ! "$@"; then
    ROLLBACK_FAILURES+=("NOT VERIFIED: ${description}")
  fi
}
unit_masked() { [[ "$(systemctl is-enabled "$1")" == masked* ]]; }
unit_not_masked() { ! unit_masked "$1"; }
unit_not_enabled() { ! systemctl is-enabled --quiet "$1"; }

rollback() {
  local status=$?
  trap - ERR
  set +e
  echo "ERROR: --apply failed (exit ${status}); undoing the installer's own changes." >&2
  for unit in "${NEWLY_ENABLED[@]}"; do
    step "disable ${unit}" systemctl disable "${unit}"
  done
  for dest in "${REPLACED[@]}"; do
    step "restore ${dest}" cp -a "${BACKUP_DIR}${dest#"${ROOT}"}" "${dest}"
  done
  for dest in "${CREATED[@]}"; do
    step "remove ${dest}" rm -f "${dest}"
  done
  if [[ "${VOSK_MASKED}" -eq 1 ]]; then
    step "unmask ${LEGACY_VOSK_UNIT}" systemctl unmask "${LEGACY_VOSK_UNIT}"
  fi
  if [[ "${VOSK_FILE_REMOVED}" -eq 1 ]]; then
    step "restore ${UNIT_DIR}/${LEGACY_VOSK_UNIT}" \
      cp -a "${BACKUP_DIR}/etc/systemd/system/${LEGACY_VOSK_UNIT}" "${UNIT_DIR}/${LEGACY_VOSK_UNIT}"
  fi
  step "systemctl daemon-reload" systemctl daemon-reload
  if [[ "${VOSK_WAS_ENABLED}" -eq 1 ]]; then
    step "re-enable ${LEGACY_VOSK_UNIT}" systemctl enable "${LEGACY_VOSK_UNIT}"
  fi
  if [[ "${VOSK_WAS_ACTIVE}" -eq 1 ]]; then
    step "start ${LEGACY_VOSK_UNIT}" systemctl start "${LEGACY_VOSK_UNIT}"
  fi
  if [[ "${RESTART_ATTEMPTED}" -eq 1 ]]; then
    step "restart thermal-backend.service kws-alert.service" \
      systemctl restart thermal-backend.service kws-alert.service
  fi

  for dest in "${REPLACED[@]}"; do
    check "${dest} matches its backup" cmp -s "${BACKUP_DIR}${dest#"${ROOT}"}" "${dest}"
  done
  for dest in "${CREATED[@]}"; do
    check "${dest} removed" test ! -e "${dest}"
  done
  for unit in "${NEWLY_ENABLED[@]}"; do
    check "${unit} not enabled" unit_not_enabled "${unit}"
  done
  if [[ "${VOSK_WAS_MASKED}" -eq 1 ]]; then
    check "${LEGACY_VOSK_UNIT} still masked" unit_masked "${LEGACY_VOSK_UNIT}"
  elif [[ "${VOSK_MASKED}" -eq 1 ]]; then
    check "${LEGACY_VOSK_UNIT} unmasked" unit_not_masked "${LEGACY_VOSK_UNIT}"
  fi
  if [[ "${VOSK_FILE_REMOVED}" -eq 1 ]]; then
    check "${UNIT_DIR}/${LEGACY_VOSK_UNIT} restored" test -f "${UNIT_DIR}/${LEGACY_VOSK_UNIT}"
  fi
  if [[ "${VOSK_WAS_ENABLED}" -eq 1 ]]; then
    check "${LEGACY_VOSK_UNIT} enabled" systemctl is-enabled --quiet "${LEGACY_VOSK_UNIT}"
  fi
  if [[ "${VOSK_WAS_ACTIVE}" -eq 1 ]]; then
    check "${LEGACY_VOSK_UNIT} active" systemctl is-active --quiet "${LEGACY_VOSK_UNIT}"
  fi
  if [[ "${RESTART_ATTEMPTED}" -eq 1 ]]; then
    check "thermal-backend.service active" systemctl is-active --quiet thermal-backend.service
    check "kws-alert.service active" systemctl is-active --quiet kws-alert.service
  fi

  # The installer never changes the checkout: the code is reported, not rolled back.
  local head_now
  head_now="$(repo_git rev-parse HEAD)"
  echo "CODE: the installer did not change ${REPO}; HEAD is ${head_now}," \
    "recorded rollback commit ${ROLLBACK_SHA}." >&2
  if [[ "${head_now}" != "${ROLLBACK_SHA}" ]]; then
    echo "CODE MISMATCH: installer-managed files are back to their pre-install state, but the" \
      "application code is still ${head_now}. Restoring ${ROLLBACK_SHA} is a separate," \
      "authorized step (docs/m1_m2_upgrade_and_rollback.md, Rollback)." >&2
  fi
  if [[ "${#ROLLBACK_FAILURES[@]}" -eq 0 ]]; then
    echo "ROLLBACK VERIFIED: every installer change was undone and its end state checked." \
      "Backup kept in ${BACKUP_DIR}." >&2
    exit 1
  fi
  echo "ROLLBACK INCOMPLETE: the previous system is NOT restored. Operations that failed" \
    "or could not be verified:" >&2
  printf '  - %s\n' "${ROLLBACK_FAILURES[@]}" >&2
  echo "Backup kept in ${BACKUP_DIR}; restore the listed items by hand before restarting." >&2
  exit 3
}
trap rollback ERR

install -d -m 0700 "${OWN[@]}" "${BACKUP_ROOT}" "${BACKUP_DIR}"
install -d -m 0755 "${OWN[@]}" "${ROOT}/etc/project-pi" "${ROOT}/var/lib/project-pi" \
  "$(dirname "${THERMAL_DROPIN}")" "${ROOT}/etc/sudoers.d" "${ROOT}/usr/local/sbin"
for target in "${CHANGED[@]}"; do
  IFS='|' read -r src dest mode <<<"${target}"
  if [[ -e "${dest}" ]]; then
    backup "${dest}"
    REPLACED+=("${dest}")
  else
    CREATED+=("${dest}")
  fi
  install "${OWN[@]}" -m "0${mode}" "${src}" "${dest}"
done
echo "Backups of replaced files: ${BACKUP_DIR}"

# Single microphone owner. A failed stop aborts and rolls back instead of being hidden.
if [[ "${VOSK_WAS_ACTIVE}" -eq 1 ]]; then
  systemctl stop "${LEGACY_VOSK_UNIT}"
fi
legacy_unit_file="${UNIT_DIR}/${LEGACY_VOSK_UNIT}"
if [[ -f "${legacy_unit_file}" && ! -L "${legacy_unit_file}" ]]; then
  # mask cannot replace a real unit file; it is kept in the backup.
  systemctl disable "${LEGACY_VOSK_UNIT}"
  backup "${legacy_unit_file}"
  rm "${legacy_unit_file}"
  VOSK_FILE_REMOVED=1
fi
systemctl daemon-reload
# Already masked (e.g. a re-run): leave it, so a rollback never unmasks it.
if [[ "${VOSK_WAS_MASKED}" -eq 0 ]]; then
  systemctl mask "${LEGACY_VOSK_UNIT}"
  VOSK_MASKED=1
fi
if systemctl is-active --quiet "${LEGACY_VOSK_UNIT}"; then
  echo "ERROR: ${LEGACY_VOSK_UNIT} is still active; refusing to leave a second microphone owner." >&2
  false
fi

for unit in "${ENABLE_UNITS[@]}"; do
  if ! systemctl is-enabled --quiet "${unit}"; then
    NEWLY_ENABLED+=("${unit}")
  fi
done
systemctl enable "${ENABLE_UNITS[@]}"

if [[ "${RESTART}" -eq 1 ]]; then
  RESTART_ATTEMPTED=1
  systemctl restart thermal-backend.service kws-alert.service
else
  echo "No service was restarted. To activate: sudo systemctl restart thermal-backend.service kws-alert.service"
fi
trap - ERR

echo ""
echo "Headless install applied."
echo "Pair a caregiver phone (run as thesis so the backend can read the file):"
echo "  sudo -u thesis python3 ${SCRIPTS}/provision_caregiver.py --installation <ID from app> --file /var/lib/project-pi/backend/caregivers.json"
