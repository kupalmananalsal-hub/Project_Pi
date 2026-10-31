#!/usr/bin/env bash
# Root helper behind /api/refresh. install_headless.sh installs it root-owned as
# /usr/local/sbin/project-pi-refresh; sudoers allows only that copy.
# It must never run anything from the thesis-writable repo: the backend does
# `git pull` itself as thesis, and unit files change only via install_headless.sh.
set -euo pipefail

RESTART_BACKEND=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --restart-backend) RESTART_BACKEND=1 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

log() {
  echo "$*"
  logger -t project-pi-refresh "$*"
}

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
