#!/usr/bin/env bash
set -euo pipefail

LOG_TAG="project-pi-log-cleanup"
STATE_DIR="/var/lib/project-pi"
REPO="${PROJECT_PI_REPO:-/home/thesis/Project_Pi}"

log() {
  echo "[${LOG_TAG}] $*"
  logger -t "${LOG_TAG}" "$*"
}

mkdir -p "${STATE_DIR}"

disk_use_percent() {
  df -P / | awk 'NR==2 {gsub("%","",$5); print $5}'
}

log "Vacuuming systemd journal (7 days, max 200M)"
journalctl --vacuum-time=7d >/dev/null 2>&1 || true
journalctl --vacuum-size=200M >/dev/null 2>&1 || true

if [[ -d /var/log/journal ]]; then
  find /var/log/journal -type f -name '*.journal~' -delete 2>/dev/null || true
fi

for pattern in '*.log' '*.log.*'; do
  find /tmp -maxdepth 1 -type f -name "${pattern}" -mtime +3 -delete 2>/dev/null || true
done

if [[ -f /tmp/project_pi_alerts.jsonl ]] && [[ "$(wc -c </tmp/project_pi_alerts.jsonl)" -gt 5242880 ]]; then
  log "Truncating large alert queue log"
  : >/tmp/project_pi_alerts.jsonl
fi

usage="$(disk_use_percent)"
if [[ "${usage}" -ge 85 ]]; then
  log "Disk usage ${usage}% — aggressive cleanup"
  apt-get clean -qq || true
  find "${REPO}" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
  journalctl --vacuum-size=100M >/dev/null 2>&1 || true
fi

log "Log cleanup complete (disk ${usage}%)"
