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
#
# It never installs or upgrades packages and never runs nmcli. Every replaced file is
# backed up to /var/lib/project-pi/install-backups/<UTC timestamp>/ first. It never
# overwrites anything in /etc/systemd/system/*.service.d/ and never touches dataset/,
# models, alerts.db, recordings, caregiver credentials or other /etc/project-pi/*.env.
set -euo pipefail

MODE=dry-run
RESTART=0
CONFIGURE_HOTSPOT=0
ACCEPT_ENV_DRIFT=0
for arg in "$@"; do
  case "${arg}" in
    --dry-run) MODE=dry-run ;;
    --apply) MODE=apply ;;
    --restart) RESTART=1 ;;
    --configure-hotspot) CONFIGURE_HOTSPOT=1 ;;
    --accept-env-drift) ACCEPT_ENV_DRIFT=1 ;;
    *) echo "Unknown option: ${arg}" >&2; exit 2 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash raspberry_pi/scripts/install_headless.sh [--apply]" >&2
  exit 1
fi

REPO="${PROJECT_PI_REPO:-/home/thesis/Project_Pi}"
SCRIPTS="${REPO}/raspberry_pi/scripts"
SYSTEMD_SRC="${REPO}/raspberry_pi/systemd"
REQUIREMENTS="${REPO}/raspberry_pi/requirements"
SUDOERS_SRC="${REPO}/raspberry_pi/sudoers/project-pi-thesis"
HOTSPOT_CONF=/etc/project-pi/hotspot.env
BACKEND_CONF=/etc/project-pi/backend.env
THERMAL_DROPIN=/etc/systemd/system/thermal-backend.service.d/10-local.conf
LEGACY_VOSK_UNIT=kws-alert-vosk.service
LEGACY_TOKEN=project-pi-local-token
BACKUP_DIR="/var/lib/project-pi/install-backups/$(date -u +%Y%m%dT%H%M%SZ)"
STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT

echo "Project Pi installer (${MODE}) from ${REPO}"

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
check_env /home/thesis/kws-env "${REQUIREMENTS}/kws-env.lock.txt"
check_env /home/thesis/thermal-env-sys "${REQUIREMENTS}/thermal-env-sys.lock.txt"

# 2. Files to install: "source|destination|mode".
TARGETS=(
  "${SCRIPTS}/pi_refresh.sh|/usr/local/sbin/project-pi-refresh|755"
  "${SCRIPTS}/headless_boot.sh|/usr/local/sbin/project-pi-boot|755"
  "${SCRIPTS}/log_cleanup.sh|/usr/local/sbin/project-pi-log-cleanup|755"
  "${SUDOERS_SRC}|/etc/sudoers.d/project-pi-thesis|440"
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
  TARGETS+=("${SYSTEMD_SRC}/${unit}|/etc/systemd/system/${unit}|644")
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

install -d -m 0700 -o root -g root /var/lib/project-pi/install-backups "${BACKUP_DIR}"
backup() {
  [[ -e "$1" ]] || return 0
  mkdir -p "${BACKUP_DIR}$(dirname "$1")"
  cp -a "$1" "${BACKUP_DIR}$1"
}

install -d -m 0755 /etc/project-pi /var/lib/project-pi "$(dirname "${THERMAL_DROPIN}")"
for target in "${CHANGED[@]}"; do
  IFS='|' read -r src dest mode <<<"${target}"
  backup "${dest}"
  install -o root -g root -m "0${mode}" "${src}" "${dest}"
done
echo "Backups of replaced files: ${BACKUP_DIR}"

# Single microphone owner. A failed stop aborts the install (set -e) instead of being hidden.
if systemctl is-active --quiet "${LEGACY_VOSK_UNIT}"; then
  systemctl stop "${LEGACY_VOSK_UNIT}"
fi
legacy_unit_file="/etc/systemd/system/${LEGACY_VOSK_UNIT}"
if [[ -f "${legacy_unit_file}" && ! -L "${legacy_unit_file}" ]]; then
  # mask cannot replace a real unit file; it is kept in the backup.
  systemctl disable "${LEGACY_VOSK_UNIT}"
  backup "${legacy_unit_file}"
  rm "${legacy_unit_file}"
fi
systemctl daemon-reload
systemctl mask "${LEGACY_VOSK_UNIT}"
if systemctl is-active --quiet "${LEGACY_VOSK_UNIT}"; then
  echo "ERROR: ${LEGACY_VOSK_UNIT} is still active; refusing to leave a second microphone owner." >&2
  exit 1
fi

systemctl enable "${ENABLE_UNITS[@]}"

if [[ "${RESTART}" -eq 1 ]]; then
  systemctl restart thermal-backend.service kws-alert.service
else
  echo "No service was restarted. To activate: sudo systemctl restart thermal-backend.service kws-alert.service"
fi

echo ""
echo "Headless install applied."
echo "Pair a caregiver phone (run as thesis so the backend can read the file):"
echo "  sudo -u thesis python3 ${SCRIPTS}/provision_caregiver.py --installation <ID from app> --file /var/lib/project-pi/backend/caregivers.json"
