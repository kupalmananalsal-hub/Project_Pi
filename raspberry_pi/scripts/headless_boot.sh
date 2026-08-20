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
HOTSPOT_STATIC_IPV4="${PROJECT_PI_HOTSPOT_STATIC_IPV4:-${PROJECT_PI_STATIC_IPV4:-}}"
HOTSPOT_STATIC_GATEWAY="${PROJECT_PI_HOTSPOT_STATIC_GATEWAY:-${PROJECT_PI_STATIC_GATEWAY:-}}"
HOTSPOT_STATIC_DNS="${PROJECT_PI_HOTSPOT_STATIC_DNS:-${PROJECT_PI_STATIC_DNS:-8.8.8.8 8.8.4.4}}"

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
  configure_static_ipv4
}

normalize_static_ipv4() {
  local address="$1"
  if [[ "${address}" == */* ]]; then
    printf '%s\n' "${address}"
  else
    printf '%s/24\n' "${address}"
  fi
}

detect_gateway() {
  local gateway
  gateway="$(ip -4 route show default dev wlan0 2>/dev/null | awk 'NR == 1 {print $3}')"
  if [[ -n "${gateway}" ]]; then
    printf '%s\n' "${gateway}"
    return 0
  fi

  ip -4 route show default 2>/dev/null | awk 'NR == 1 {print $3}'
}

configure_static_ipv4() {
  if [[ -z "${HOTSPOT_STATIC_IPV4}" ]]; then
    return 0
  fi

  local address gateway target_ip current_ips
  address="$(normalize_static_ipv4 "${HOTSPOT_STATIC_IPV4}")"
  gateway="${HOTSPOT_STATIC_GATEWAY}"
  if [[ -z "${gateway}" ]]; then
    gateway="$(detect_gateway || true)"
  fi

  if [[ -z "${gateway}" ]]; then
    log "Static IPv4 ${address} requested, but no gateway was found; leaving existing IPv4 settings"
    return 1
  fi

  target_ip="${address%%/*}"
  current_ips="$(hostname -I || true)"
  if ! grep -qw "${target_ip}" <<<"${current_ips}"; then
    if ping -c 1 -W 1 "${target_ip}" >/dev/null 2>&1; then
      log "Refusing static IPv4 ${target_ip}; another hotspot device already responds to it"
      return 1
    fi
  fi

  log "Configuring ${HOTSPOT_CONNECTION} with static IPv4 ${address}, gateway ${gateway}"
  nmcli connection modify "${HOTSPOT_CONNECTION}" ipv4.method manual
  nmcli connection modify "${HOTSPOT_CONNECTION}" ipv4.addresses "${address}"
  nmcli connection modify "${HOTSPOT_CONNECTION}" ipv4.gateway "${gateway}"
  nmcli connection modify "${HOTSPOT_CONNECTION}" ipv4.dns "${HOTSPOT_STATIC_DNS}"
}

connect_hotspot() {
  ensure_hotspot_profile

  if iwgetid -r 2>/dev/null | grep -Fxq "${HOTSPOT_SSID}"; then
    log "Already associated with ${HOTSPOT_SSID}"
    if [[ -n "${HOTSPOT_STATIC_IPV4}" ]] && ! ip -4 addr show dev wlan0 | grep -q "inet ${HOTSPOT_STATIC_IPV4%%/*}/"; then
      log "Reapplying ${HOTSPOT_CONNECTION} so static IPv4 settings take effect"
      nmcli connection up "${HOTSPOT_CONNECTION}" || true
    fi
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
