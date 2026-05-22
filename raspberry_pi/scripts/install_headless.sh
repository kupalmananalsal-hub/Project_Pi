#!/usr/bin/env bash
# One-time installer for headless Project Pi operation (run on the Pi as thesis).
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash raspberry_pi/scripts/install_headless.sh"
  exit 1
fi

REPO="${PROJECT_PI_REPO:-/home/thesis/Project_Pi}"
HOTSPOT_SSID="${PROJECT_PI_HOTSPOT_SSID:-Teddy}"
HOTSPOT_PASSWORD="${PROJECT_PI_HOTSPOT_PASSWORD:-bayadkamuna}"

echo "Installing Project Pi headless stack from ${REPO}"

install -d -m 0755 /etc/project-pi /var/lib/project-pi
cat >/etc/project-pi/hotspot.env <<EOF
PROJECT_PI_HOTSPOT_SSID=${HOTSPOT_SSID}
PROJECT_PI_HOTSPOT_PASSWORD=${HOTSPOT_PASSWORD}
PROJECT_PI_HOTSPOT_CONNECTION=${HOTSPOT_SSID}
EOF
chmod 0600 /etc/project-pi/hotspot.env

chmod +x "${REPO}/raspberry_pi/scripts/"*.sh
install -m 0440 "${REPO}/raspberry_pi/sudoers/project-pi-thesis" /etc/sudoers.d/project-pi-thesis
visudo -cf /etc/sudoers.d/project-pi-thesis

bash "${REPO}/raspberry_pi/scripts/headless_boot.sh"

systemctl enable project-pi.target
systemctl enable project-pi-apt-update.timer project-pi-log-cleanup.timer
systemctl start project-pi-apt-update.timer project-pi-log-cleanup.timer

echo ""
echo "Headless install complete."
echo "Enabled units:"
systemctl list-unit-files 'project-pi*' 'thermal-backend' 'kws-alert' 'apk-server' --no-pager
echo ""
echo "Test refresh: curl -X POST http://127.0.0.1:8765/api/refresh -H 'Content-Type: application/json' -d '{}'"
