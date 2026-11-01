#!/usr/bin/env bash
# Replace PROJECT_PI_API_TOKEN in /etc/project-pi/backend.env with a new random token.
# Installed root-owned by install_headless.sh --apply as /usr/local/sbin/project-pi-rotate-token
# (never run it from the thesis-writable checkout as root). On the Pi console:
#   sudo /usr/local/sbin/project-pi-rotate-token
#
# The token exists only in this shell's memory and is written with the printf builtin:
# it never appears in a process's arguments, in output, logs, shell history or git.
# The file is replaced atomically, root-owned 600. Only required mode is rotated.
# Nothing is restarted: restart thermal-backend then kws-alert, then enter the new token
# on every phone (read it on the console: sudo sed -n 's/^PROJECT_PI_API_TOKEN=//p' FILE).
set -Eeuo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo /usr/local/sbin/project-pi-rotate-token" >&2
  exit 1
fi
ROOT="${PROJECT_PI_INSTALL_ROOT:-}"  # tests only
CONF="${ROOT}/etc/project-pi/backend.env"
if [[ ! -f "${CONF}" ]]; then
  echo "${CONF} does not exist; create it with install_headless.sh --api-auth=required." >&2
  exit 1
fi
if ! grep -qx 'PROJECT_PI_API_AUTH=required' "${CONF}"; then
  echo "Refusing: ${CONF} is not in required mode; a token there would not be used." >&2
  exit 1
fi

umask 077
token="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
tmp="$(mktemp "${CONF}.XXXXXX")"
trap 'rm -f "${tmp}"' EXIT
replaced=0
while IFS= read -r line || [[ -n "${line}" ]]; do
  if [[ "${line}" == PROJECT_PI_API_TOKEN=* ]]; then
    printf 'PROJECT_PI_API_TOKEN=%s\n' "${token}"
    replaced=1
  else
    printf '%s\n' "${line}"
  fi
done <"${CONF}" >"${tmp}"
if [[ "${replaced}" -eq 0 ]]; then
  printf 'PROJECT_PI_API_TOKEN=%s\n' "${token}" >>"${tmp}"
fi
unset token
chmod 600 "${tmp}"
if [[ -z "${ROOT}" ]]; then
  chown root:root "${tmp}"
fi
mv -f "${tmp}" "${CONF}"
trap - EXIT
echo "New API token written to ${CONF} (not shown). Restart thermal-backend, then"
echo "kws-alert, then enter it on every phone; the old token stops working at the restart."
