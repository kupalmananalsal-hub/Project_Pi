#!/usr/bin/env bash
# Install Project Pi openWakeWord runtime dependencies on the Raspberry Pi.
set -euo pipefail

KWS_VENV="${KWS_VENV:-/home/thesis/kws-env}"
KWS_PYTHON="${KWS_VENV}/bin/python"
KWS_PIP="${KWS_VENV}/bin/pip"

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

echo "Installing Python openWakeWord ONNX dependencies into ${KWS_VENV}..."
"${KWS_PIP}" install --upgrade pip wheel setuptools
"${KWS_PIP}" install --upgrade openwakeword onnxruntime soundfile

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
  "${KWS_PIP}" install speexdsp-ns
}

if ! "${KWS_PYTHON}" -c 'import speexdsp_ns' >/dev/null 2>&1; then
  install_speex_wrapper
fi

"${KWS_PYTHON}" -c "import speexdsp_ns; print('Speex OK')"
"${KWS_PYTHON}" -c "import onnxruntime; print('ONNX Runtime OK')"

echo "openWakeWord dependency install complete."
