#!/usr/bin/env bash
# WARNING: MANUAL USE ONLY. This script changes the KWS virtual environment: it runs
# apt-get and installs the pinned versions in raspberry_pi/requirements/kws-env.lock.txt,
# which can replace whatever is installed now. A changed onnxruntime/openWakeWord/Vosk
# version changes detection behavior, so run it only as part of a reviewed upgrade.
# install_headless.sh never calls it.
#
#   bash raspberry_pi/scripts/install_kws_openwakeword_deps.sh --i-understand-this-upgrades-packages
set -euo pipefail

if [[ "${1:-}" != "--i-understand-this-upgrades-packages" ]]; then
  sed -n '2,8p' "$0" >&2
  exit 2
fi

KWS_VENV="${KWS_VENV:-/home/thesis/kws-env}"
KWS_PYTHON="${KWS_VENV}/bin/python"
KWS_PIP="${KWS_VENV}/bin/pip"
LOCK_FILE="$(cd "$(dirname "$0")/.." && pwd)/requirements/kws-env.lock.txt"

if [[ ! -x "${KWS_PYTHON}" ]]; then
  echo "KWS Python not found: ${KWS_PYTHON}" >&2
  echo "Create the virtual environment first, then rerun this script." >&2
  exit 1
fi

if [[ "$(id -u)" -eq 0 ]]; then
  SUDO=()
else
  SUDO=(sudo)
fi

echo "Installing system Speex library..."
"${SUDO[@]}" apt-get update
"${SUDO[@]}" apt-get install -y libspeexdsp-dev

PY_TAG="$("${KWS_PYTHON}" -c 'import sys; print(f"cp{sys.version_info.major}{sys.version_info.minor}")')"
ARCH="$("${KWS_PYTHON}" -c 'import platform; print(platform.machine())')"

install_speex_wrapper() {
  if [[ "${ARCH}" == "aarch64" || "${ARCH}" == "arm64" ]]; then
    local wheel_url
    wheel_url="https://github.com/dscripka/openWakeWord/releases/download/v0.1.1/speexdsp_ns-0.1.2-${PY_TAG}-${PY_TAG}-linux_aarch64.whl"
    echo "Trying Speex wheel: ${wheel_url}"
    if "${KWS_PIP}" install "${wheel_url}"; then
      return 0
    fi
  fi

  echo "Falling back to speexdsp-ns from PyPI/source..."
  "${KWS_PIP}" install speexdsp-ns==0.1.2
}

if ! "${KWS_PYTHON}" -c 'import speexdsp_ns' >/dev/null 2>&1; then
  install_speex_wrapper
fi

echo "Installing the pinned KWS environment from ${LOCK_FILE}..."
"${KWS_PIP}" install -r "${LOCK_FILE}"

"${KWS_PYTHON}" -c "import speexdsp_ns; print('Speex OK')"
"${KWS_PYTHON}" -c "import onnxruntime; print('ONNX Runtime OK')"

echo "KWS dependency install complete."
