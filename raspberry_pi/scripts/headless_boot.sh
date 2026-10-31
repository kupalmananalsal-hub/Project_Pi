#!/usr/bin/env bash
# Runs once per boot via project-pi-boot.service (root), from the root-owned copy
# /usr/local/sbin/project-pi-boot. It must not execute or install anything from the
# thesis-writable repo; unit files are installed only by install_headless.sh.
set -euo pipefail

STATE_DIR="${PROJECT_PI_STATE_DIR:-/var/lib/project-pi}"
LOG_TAG="project-pi-boot"
HOTSPOT_CONF="${PROJECT_PI_HOTSPOT_CONF:-/etc/project-pi/hotspot.env}"

log() {
  echo "[${LOG_TAG}] $*"
  logger -t "${LOG_TAG}" "$*" || true
}

mkdir -p "${STATE_DIR}"

# Root sources this file: anyone who can write it can run commands as root.
if [[ -f "${HOTSPOT_CONF}" ]]; then
  read -r conf_uid conf_mode < <(stat -c '%u %a' "${HOTSPOT_CONF}")
  if [[ "${conf_uid}" == "0" ]] && (( (8#${conf_mode} & 8#022) == 0 )); then
    # shellcheck disable=SC1090
    source "${HOTSPOT_CONF}"
  else
    log "Ignoring ${HOTSPOT_CONF}: not root-owned or group/world-writable (uid ${conf_uid}, mode ${conf_mode})"
  fi
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

log_network() {
  log "Network unchanged: SSID=$(iwgetid -r 2>/dev/null || echo none)," \
    "IPv4=$(ip -4 -o addr show dev wlan0 2>/dev/null | awk '{print $4}' | paste -sd, -)"
}

# Detection units do not wait for this script, and it never waits for the network unless
# hotspot management is on. Package-index updates run from project-pi-apt-update.timer.
main() {
  log "Headless boot script started"
  # Opt-in only: by default the boot never creates, modifies or activates an NM profile.
  if [[ "${PROJECT_PI_FORCE_HOTSPOT:-0}" == "1" ]]; then
    wait_for_network || true
    connect_hotspot || log "Hotspot connect did not succeed; services will still start"
  else
    log_network
  fi
  /usr/local/sbin/project-pi-log-cleanup || log "Log cleanup failed (continuing)"
  log "Headless boot script finished (systemd will start enabled app units)"
}

main "$@"
