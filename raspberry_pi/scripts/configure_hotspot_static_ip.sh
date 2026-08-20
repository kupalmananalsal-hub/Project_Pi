#!/usr/bin/env bash
# Configure the Pi Wi-Fi profile with a stable IPv4 address for the phone hotspot.
set -euo pipefail

HOTSPOT_CONF="${PROJECT_PI_HOTSPOT_CONF:-/etc/project-pi/hotspot.env}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash raspberry_pi/scripts/configure_hotspot_static_ip.sh"
  exit 1
fi

if [[ -f "${HOTSPOT_CONF}" ]]; then
  # shellcheck disable=SC1090
  source "${HOTSPOT_CONF}"
fi

PROFILE="${1:-${PROJECT_PI_HOTSPOT_CONNECTION:-}}"
STATIC_IPV4="${PROJECT_PI_HOTSPOT_STATIC_IPV4:-${PROJECT_PI_STATIC_IPV4:-10.129.205.32/24}}"
STATIC_GATEWAY="${PROJECT_PI_HOTSPOT_STATIC_GATEWAY:-${PROJECT_PI_STATIC_GATEWAY:-}}"
STATIC_DNS="${PROJECT_PI_HOTSPOT_STATIC_DNS:-${PROJECT_PI_STATIC_DNS:-8.8.8.8 8.8.4.4}}"

active_wifi_profile() {
  nmcli -t -f NAME,TYPE,DEVICE connection show --active |
    awk -F: '$2 == "wifi" && $3 != "" && $3 != "--" {print $1; exit}'
}

detect_gateway() {
  ip -4 route show default dev wlan0 2>/dev/null | awk 'NR == 1 {print $3; found=1} END {exit !found}' ||
    ip -4 route show default 2>/dev/null | awk 'NR == 1 {print $3; found=1} END {exit !found}'
}

normalize_static_ipv4() {
  local address="$1"
  if [[ "${address}" == */* ]]; then
    printf '%s\n' "${address}"
  else
    printf '%s/24\n' "${address}"
  fi
}

target_host() {
  printf '%s\n' "${STATIC_IPV4%%/*}"
}

if [[ -z "${PROFILE}" ]]; then
  PROFILE="$(active_wifi_profile)"
fi

if [[ -z "${PROFILE}" ]]; then
  echo "Could not identify an active Wi-Fi NetworkManager profile."
  echo "Run: nmcli -f NAME,TYPE,DEVICE connection"
  echo "Then retry with: sudo bash raspberry_pi/scripts/configure_hotspot_static_ip.sh \"<HOTSPOT_PROFILE>\""
  exit 1
fi

if ! nmcli connection show "${PROFILE}" >/dev/null 2>&1; then
  echo "NetworkManager profile not found: ${PROFILE}"
  exit 1
fi

STATIC_IPV4="$(normalize_static_ipv4 "${STATIC_IPV4}")"
if [[ -z "${STATIC_GATEWAY}" ]]; then
  STATIC_GATEWAY="$(detect_gateway || true)"
fi

if [[ -z "${STATIC_GATEWAY}" ]]; then
  echo "Could not detect a default IPv4 gateway. Set PROJECT_PI_HOTSPOT_STATIC_GATEWAY and retry."
  exit 1
fi

TARGET_IP="$(target_host)"
CURRENT_IPS="$(hostname -I || true)"

if ! grep -qw "${TARGET_IP}" <<<"${CURRENT_IPS}"; then
  if ping -c 1 -W 1 "${TARGET_IP}" >/dev/null 2>&1; then
    echo "Refusing to assign ${TARGET_IP}: another device on the hotspot already responds to it."
    echo "Choose a free Pi IP, then set PROJECT_PI_HOTSPOT_STATIC_IPV4 in ${HOTSPOT_CONF}."
    exit 1
  fi
fi

echo "Configuring ${PROFILE}:"
echo "  IPv4:   ${STATIC_IPV4}"
echo "  Gateway:${STATIC_GATEWAY}"
echo "  DNS:    ${STATIC_DNS}"

nmcli connection modify "${PROFILE}" ipv4.method manual
nmcli connection modify "${PROFILE}" ipv4.addresses "${STATIC_IPV4}"
nmcli connection modify "${PROFILE}" ipv4.gateway "${STATIC_GATEWAY}"
nmcli connection modify "${PROFILE}" ipv4.dns "${STATIC_DNS}"
nmcli connection modify "${PROFILE}" connection.autoconnect yes
nmcli connection modify "${PROFILE}" connection.autoconnect-priority 100

nmcli connection down "${PROFILE}" || true
nmcli connection up "${PROFILE}"

echo "Current Pi addresses:"
hostname -I
