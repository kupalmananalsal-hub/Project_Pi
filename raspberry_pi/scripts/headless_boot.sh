#!/usr/bin/env bash
# Runs once per boot via project-pi-boot.service (root).
set -euo pipefail

REPO="${PROJECT_PI_REPO:-/home/thesis/Project_Pi}"
SYSTEMD_SRC="${REPO}/raspberry_pi/systemd"
STATE_DIR="/var/lib/project-pi"
LOG_TAG="project-pi-boot"
APT_STAMP="${STATE_DIR}/last-apt-update"
HOTSPOT_CONF="/etc/project-pi/hotspot.env"

log() {
  echo "[${LOG_TAG}] $*"
  logger -t "${LOG_TAG}" "$*"
}

mkdir -p "${STATE_DIR}"

if [[ -f "${HOTSPOT_CONF}" ]]; then
  # shellcheck disable=SC1090
  source "${HOTSPOT_CONF}"
fi
HOTSPOT_SSID="${PROJECT_PI_HOTSPOT_SSID:-Teddy}"
HOTSPOT_PASSWORD="${PROJECT_PI_HOTSPOT_PASSWORD:-}"
HOTSPOT_CONNECTION="${PROJECT_PI_HOTSPOT_CONNECTION:-${HOTSPOT_SSID}}"

wait_for_network() {
  local attempt
  for attempt in $(seq 1 60); do
    if nmcli -t -f STATE general | grep -qE 'connected|connecting'; then
      return 0
    fi
    sleep 2
  done
  log "NetworkManager did not report a connected state within 120s"
  return 1
}

ensure_hotspot_profile() {
  if [[ -z "${HOTSPOT_PASSWORD}" ]]; then
    log "Hotspot password not configured in ${HOTSPOT_CONF}; skipping Wi-Fi setup"
    return 0
  fi

  if ! nmcli connection show "${HOTSPOT_CONNECTION}" >/dev/null 2>&1; then
    log "Creating Wi-Fi profile ${HOTSPOT_CONNECTION} for SSID ${HOTSPOT_SSID}"
    nmcli connection add type wifi con-name "${HOTSPOT_CONNECTION}" ifname wlan0 ssid "${HOTSPOT_SSID}"
    nmcli connection modify "${HOTSPOT_CONNECTION}" wifi-sec.key-mgmt wpa-psk
    nmcli connection modify "${HOTSPOT_CONNECTION}" wifi-sec.psk "${HOTSPOT_PASSWORD}"
  fi

  nmcli connection modify "${HOTSPOT_CONNECTION}" connection.autoconnect yes
  nmcli connection modify "${HOTSPOT_CONNECTION}" connection.autoconnect-priority 10
}

connect_hotspot() {
  ensure_hotspot_profile

  if iwgetid -r 2>/dev/null | grep -Fxq "${HOTSPOT_SSID}"; then
    log "Already associated with ${HOTSPOT_SSID}"
    return 0
  fi

  log "Bringing up hotspot profile ${HOTSPOT_CONNECTION}"
  if nmcli connection up "${HOTSPOT_CONNECTION}"; then
    return 0
  fi

  log "Profile activation failed; attempting direct Wi-Fi connect"
  nmcli dev wifi connect "${HOTSPOT_SSID}" password "${HOTSPOT_PASSWORD}" name "${HOTSPOT_CONNECTION}" \
    connection.autoconnect yes connection.autoconnect-priority 10 || true
}

sync_systemd_units() {
  local units=(
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
  for unit in "${units[@]}"; do
    install -m 0644 "${SYSTEMD_SRC}/${unit}" "/etc/systemd/system/${unit}"
  done
  systemctl daemon-reload
  systemctl enable project-pi-boot.service project-pi.target
  systemctl enable thermal-backend.service kws-alert.service apk-server.service
  systemctl enable project-pi-apt-update.timer project-pi-log-cleanup.timer
  systemctl disable kws-alert-vosk.service 2>/dev/null || true
}

maybe_apt_update() {
  local now last=0
  now="$(date +%s)"
  if [[ -f "${APT_STAMP}" ]]; then
    last="$(cat "${APT_STAMP}")"
  fi
  if (( now - last < 86400 )); then
    log "Skipping apt update (ran within the last 24h)"
    return 0
  fi
  log "Running apt-get update"
  if apt-get update -qq; then
    echo "${now}" > "${APT_STAMP}"
    log "apt-get update completed"
  else
    log "apt-get update failed (continuing boot)"
  fi
}

main() {
  log "Headless boot script started"
  wait_for_network || true
  connect_hotspot || log "Hotspot connect did not succeed; services will still start"
  sync_systemd_units
  maybe_apt_update
  bash "${REPO}/raspberry_pi/scripts/log_cleanup.sh" || log "Log cleanup failed (continuing)"
  log "Headless boot script finished (systemd will start enabled app units)"
}

main "$@"
