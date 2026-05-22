#!/usr/bin/env bash
# Refresh KWS stack from the mobile app (runs as root via sudo).
set -euo pipefail

REPO="${PROJECT_PI_REPO:-/home/thesis/Project_Pi}"
SYSTEMD_SRC="${REPO}/raspberry_pi/systemd"
GIT_PULL=0
RESTART_BACKEND=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --git-pull) GIT_PULL=1 ;;
    --restart-backend) RESTART_BACKEND=1 ;;
  esac
  shift
done

log() {
  echo "$*"
  logger -t project-pi-refresh "$*"
}

if [[ "${GIT_PULL}" -eq 1 ]]; then
  if [[ -d "${REPO}/.git" ]]; then
    log "Pulling latest code"
    sudo -u thesis git -C "${REPO}" pull --ff-only
  else
    log "Skipping git pull (no git repository at ${REPO})"
  fi
fi

log "Installing kws-alert.service unit"
install -m 0644 "${SYSTEMD_SRC}/kws-alert.service" /etc/systemd/system/kws-alert.service
systemctl daemon-reload
systemctl enable kws-alert.service

log "Restarting kws-alert.service"
systemctl reset-failed kws-alert.service 2>/dev/null || true
systemctl restart --no-block kws-alert.service
sleep 2

if [[ "${RESTART_BACKEND}" -eq 1 ]]; then
  log "Restarting thermal-backend.service"
  systemctl restart thermal-backend.service
fi

if systemctl is-active --quiet kws-alert.service; then
  log "kws-alert.service is active"
  systemctl --no-pager --full status kws-alert.service | head -n 8
  exit 0
fi

log "kws-alert.service failed to stay active"
systemctl --no-pager --full status kws-alert.service | head -n 20 || true
exit 1
