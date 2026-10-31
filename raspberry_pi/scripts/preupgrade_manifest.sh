# Sourced by preupgrade_backup.sh and preupgrade_inventory.sh: the one place that
# decides whether a protected-asset manifest is acceptable.
#
# Format: "<role> <path>" per line; "#" comments and blank lines ignored. Every role in
# PREUPGRADE_ROLES must appear exactly once (a model may live at a confirmed alternative
# path, but no asset may be left out). A "? " prefix marks an unconfirmed entry and is
# refused. Paths are relative to the checkout, without "." or ".." parts, and no part of
# them may be a symlink; the file must exist as a regular file.

PREUPGRADE_ROLES=(alerts_db alerts_db_backup thermal_model thermal_labels)

# read_manifest MANIFEST REPO: prints "role path" lines, or every problem on stderr and
# returns 1. Nothing is written.
read_manifest() {
  local manifest="$1" repo="$2" line role path part cur errors=0
  local -A roles=() paths=()
  local -a parts
  if [[ ! -f "${manifest}" ]]; then
    echo "MANIFEST ${manifest} does not exist" >&2
    return 1
  fi
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    [[ -z "${line}" || "${line}" == \#* ]] && continue
    if [[ "${line}" == '? '* ]]; then
      echo "MANIFEST unconfirmed entry (confirm it on the Pi, then remove '? '): ${line}" >&2
      errors=1
      continue
    fi
    role="${line%% *}"
    path="${line#* }"
    if [[ "${line}" != *' '* || -z "${path}" || "${path}" == ' '* ]]; then
      echo "MANIFEST malformed line (expected '<role> <path>'): ${line}" >&2
      errors=1
      continue
    fi
    if [[ " ${PREUPGRADE_ROLES[*]} " != *" ${role} "* ]]; then
      echo "MANIFEST unknown role '${role}' (expected one of: ${PREUPGRADE_ROLES[*]})" >&2
      errors=1
      continue
    fi
    if [[ -n "${roles[${role}]:-}" ]]; then
      echo "MANIFEST duplicate role ${role}" >&2
      errors=1
      continue
    fi
    if [[ -n "${paths[${path}]:-}" ]]; then
      echo "MANIFEST duplicate path ${path}" >&2
      errors=1
      continue
    fi
    roles["${role}"]=1
    paths["${path}"]=1
    if [[ "${path}" == /* || "${path}" == [A-Za-z]:* || "${path}" == */ ||"${path}" == *\\* ]]; then
      echo "MANIFEST ${role}: path must be relative to the checkout: ${path}" >&2
      errors=1
      continue
    fi
    IFS='/' read -r -a parts <<<"${path}"
    cur="${repo}"
    for part in "${parts[@]}"; do
      if [[ -z "${part}" || "${part}" == . || "${part}" == .. ]]; then
        echo "MANIFEST ${role}: '.', '..' or empty path parts are not allowed: ${path}" >&2
        errors=1
        continue 2
      fi
      cur="${cur}/${part}"
      if [[ -L "${cur}" ]]; then
        echo "MANIFEST ${role}: ${cur} is a symlink; protected paths may not pass through one" >&2
        errors=1
        continue 2
      fi
    done
    if [[ ! -f "${repo}/${path}" ]]; then
      echo "MANIFEST ${role}: ${path} is missing (not a regular file)" >&2
      errors=1
      continue
    fi
    printf '%s %s\n' "${role}" "${path}"
  done <"${manifest}"
  for role in "${PREUPGRADE_ROLES[@]}"; do
    if [[ -z "${roles[${role}]:-}" ]]; then
      echo "MANIFEST mandatory asset ${role} is not listed" >&2
      errors=1
    fi
  done
  return "${errors}"
}
