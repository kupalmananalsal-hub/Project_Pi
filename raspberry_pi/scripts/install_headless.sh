#!/usr/bin/env bash
# Installer for headless Project Pi operation. Run on the Pi as root:
#   sudo PROJECT_PI_HOTSPOT_PASSWORD='<hotspot password>' bash raspberry_pi/scripts/install_headless.sh
# Re-run it after pulling changes to systemd units, sudoers or the root helper scripts:
# the boot service no longer copies them from the repo.
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash raspberry_pi/scripts/install_headless.sh"
  exit 1
fi

REPO="${PROJECT_PI_REPO:-/home/thesis/Project_Pi}"
SCRIPTS="${REPO}/raspberry_pi/scripts"
SYSTEMD_SRC="${REPO}/raspberry_pi/systemd"
HOTSPOT_CONF=/etc/project-pi/hotspot.env
BACKEND_CONF=/etc/project-pi/backend.env
LEGACY_TOKEN=project-pi-local-token

echo "Installing Project Pi headless stack from ${REPO}"
install -d -m 0755 /etc/project-pi /var/lib/project-pi

if [[ -n "${PROJECT_PI_HOTSPOT_PASSWORD:-}" ]]; then
  HOTSPOT_SSID="${PROJECT_PI_HOTSPOT_SSID:-Teddy}"
  cat >"${HOTSPOT_CONF}" <<EOF
PROJECT_PI_HOTSPOT_SSID=${HOTSPOT_SSID}
PROJECT_PI_HOTSPOT_PASSWORD=${PROJECT_PI_HOTSPOT_PASSWORD}
PROJECT_PI_HOTSPOT_CONNECTION=${HOTSPOT_SSID}
PROJECT_PI_HOTSPOT_STATIC_IPV4=${PROJECT_PI_HOTSPOT_STATIC_IPV4:-10.129.205.32/24}
PROJECT_PI_HOTSPOT_STATIC_GATEWAY=${PROJECT_PI_HOTSPOT_STATIC_GATEWAY:-}
PROJECT_PI_HOTSPOT_STATIC_DNS="${PROJECT_PI_HOTSPOT_STATIC_DNS:-8.8.8.8 8.8.4.4}"
EOF
  chmod 0600 "${HOTSPOT_CONF}"
elif [[ ! -f "${HOTSPOT_CONF}" ]]; then
  echo "Set PROJECT_PI_HOTSPOT_PASSWORD (no default is shipped) and re-run." >&2
  exit 1
fi

# Created once, never overwritten: it holds the admin's choice of API auth mode.
if [[ ! -f "${BACKEND_CONF}" ]]; then
  cat >"${BACKEND_CONF}" <<'EOF'
# API authentication is OFF (no-token mode): every /api and /ws route, including
# refresh, reboot, shutdown and model deploy, is open to anyone on the network.
# Use no-token mode only on an isolated, trusted network (e.g. the defense hotspot).
#
# To turn authentication ON, uncomment both lines, set a random token, restart
# thermal-backend and kws-alert, and enter the token in each phone's Settings:
#   python3 -c 'import secrets; print(secrets.token_hex(32))'
#PROJECT_PI_API_AUTH=required
#PROJECT_PI_API_TOKEN=
PROJECT_PI_CAREGIVER_CREDENTIALS=/var/lib/project-pi/backend/caregivers.json
PROJECT_PI_CORS_ORIGINS=http://localhost,http://127.0.0.1
EOF
  echo "Created ${BACKEND_CONF} with API authentication OFF (see the comments in it to enable)."
fi
if grep -q "^PROJECT_PI_API_TOKEN=${LEGACY_TOKEN}\$" "${BACKEND_CONF}"; then
  echo "WARNING: ${BACKEND_CONF} sets the public default token; the backend will refuse to start." >&2
fi
chmod 0600 "${BACKEND_CONF}"

# Root runs only these root-owned copies, never the thesis-writable originals.
install -o root -g root -m 0755 "${SCRIPTS}/pi_refresh.sh" /usr/local/sbin/project-pi-refresh
install -o root -g root -m 0755 "${SCRIPTS}/headless_boot.sh" /usr/local/sbin/project-pi-boot
install -o root -g root -m 0755 "${SCRIPTS}/log_cleanup.sh" /usr/local/sbin/project-pi-log-cleanup

# Validate before installing: a broken sudoers file locks everyone out of sudo.
visudo -cf "${REPO}/raspberry_pi/sudoers/project-pi-thesis"
install -o root -g root -m 0440 "${REPO}/raspberry_pi/sudoers/project-pi-thesis" /etc/sudoers.d/project-pi-thesis

units=(
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
  install -o root -g root -m 0644 "${SYSTEMD_SRC}/${unit}" "/etc/systemd/system/${unit}"
done
systemctl daemon-reload
systemctl enable project-pi-boot.service project-pi.target
systemctl enable thermal-backend.service kws-alert.service apk-server.service
systemctl enable project-pi-apt-update.timer project-pi-log-cleanup.timer
# The legacy unit also opens the ReSpeaker: stop it (not just disable) so kws-alert is the
# only microphone owner. A failed stop aborts the install (set -e) instead of being hidden.
if systemctl cat kws-alert-vosk.service >/dev/null 2>&1; then
  systemctl disable --now kws-alert-vosk.service
fi
if systemctl is-active --quiet kws-alert-vosk.service; then
  echo "ERROR: kws-alert-vosk.service is still active; refusing to start a second microphone owner." >&2
  exit 1
fi

if [[ -x /home/thesis/kws-env/bin/python ]]; then
  bash "${SCRIPTS}/install_kws_openwakeword_deps.sh"
else
  echo "Skipping openWakeWord dependency install; /home/thesis/kws-env is not ready."
fi

/usr/local/sbin/project-pi-boot
systemctl start project-pi-apt-update.timer project-pi-log-cleanup.timer
systemctl restart thermal-backend.service kws-alert.service

echo ""
echo "Headless install complete."
systemctl list-unit-files 'project-pi*' 'thermal-backend*' 'kws-alert*' 'apk-server*' --no-pager
echo ""
echo "Pair a caregiver phone (run as thesis so the backend can read the file):"
echo "  sudo -u thesis python3 ${SCRIPTS}/provision_caregiver.py --installation <ID from app> --file /var/lib/project-pi/backend/caregivers.json"
echo "Test refresh:"
echo "  sudo bash -c 'source ${BACKEND_CONF}; curl -X POST http://127.0.0.1:8765/api/refresh -H \"Authorization: Bearer \$PROJECT_PI_API_TOKEN\" -H \"Content-Type: application/json\" -d {}'"
