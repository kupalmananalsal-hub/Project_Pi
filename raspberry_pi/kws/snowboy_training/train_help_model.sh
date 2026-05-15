#!/usr/bin/env bash
set -euo pipefail

HOTWORD_TEXT="${HOTWORD_TEXT:-help}"
MODEL_NAME="${MODEL_NAME:-help}"
TRAIN_DIR="${SNOWBOY_TRAIN_DIR:-$HOME/snowboy-training/$MODEL_NAME}"
RECORDINGS_DIR="$TRAIN_DIR/recordings"
MODELS_DIR="$TRAIN_DIR/models"
TARGET_MODEL="${TARGET_MODEL:-$HOME/snowboy/examples/Python3/resources/models/$MODEL_NAME.pmdl}"
IMAGE="${SNOWBOY_SEASALT_IMAGE:-rhasspy/snowboy-seasalt}"
CONTAINER_NAME="${SNOWBOY_SEASALT_CONTAINER:-snowboy-seasalt-$MODEL_NAME}"
PORT="${SNOWBOY_SEASALT_PORT:-8000}"
AUDIO_DEVICE="${AUDIO_DEVICE:-plughw:2,0}"
RECORD_SECONDS="${RECORD_SECONDS:-2}"

usage() {
  cat <<USAGE
Usage: $0 [record|serve|train|all|stop]

Environment:
  HOTWORD_TEXT       Phrase to speak while recording. Default: help
  MODEL_NAME         Output model base name. Default: help
  AUDIO_DEVICE       ALSA capture device. Default: plughw:2,0
  RECORD_SECONDS     Seconds per sample. Default: 2
  SNOWBOY_TRAIN_DIR  Work directory. Default: ~/snowboy-training/<MODEL_NAME>
  TARGET_MODEL       Install path. Default: ~/snowboy/examples/Python3/resources/models/<MODEL_NAME>.pmdl
  DOCKER_PLATFORM    Optional Docker platform, for example linux/amd64

Examples:
  $0 all
  HOTWORD_TEXT="please help" MODEL_NAME=please_help $0 all
  $0 serve
USAGE
}

docker_platform_args() {
  if [[ -n "${DOCKER_PLATFORM:-}" ]]; then
    printf '%s\n' --platform "$DOCKER_PLATFORM"
  fi
}

record_examples() {
  mkdir -p "$RECORDINGS_DIR"
  echo "Recording 3 samples for model '$MODEL_NAME'."
  echo "Say this phrase each time: $HOTWORD_TEXT"
  echo

  for index in 1 2 3; do
    local output="$RECORDINGS_DIR/example${index}.wav"
    read -r -p "Press Enter, then say '$HOTWORD_TEXT' for sample $index..."
    arecord -D "$AUDIO_DEVICE" -f S16_LE -r 16000 -c 1 -d "$RECORD_SECONDS" "$output"
    echo "Saved $output"
    aplay "$output" || true
    echo
  done
}

start_server() {
  if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    echo "$CONTAINER_NAME is already running."
    return
  fi

  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker pull "$IMAGE"

  local platform_args=()
  while IFS= read -r arg; do
    platform_args+=("$arg")
  done < <(docker_platform_args)

  docker run \
    --rm \
    -d \
    "${platform_args[@]}" \
    --name "$CONTAINER_NAME" \
    -p "$PORT:8000" \
    "$IMAGE" >/dev/null

  echo "Waiting for Snowboy Seasalt at http://127.0.0.1:$PORT ..."
  for _ in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:$PORT" >/dev/null 2>&1; then
      echo "Snowboy Seasalt is ready."
      return
    fi
    sleep 1
  done

  echo "Snowboy Seasalt did not become ready. Check: docker logs $CONTAINER_NAME" >&2
  exit 1
}

train_model() {
  mkdir -p "$MODELS_DIR"

  for index in 1 2 3; do
    local input="$RECORDINGS_DIR/example${index}.wav"
    if [[ ! -f "$input" ]]; then
      echo "Missing $input. Run: $0 record" >&2
      exit 1
    fi
  done

  start_server

  local output="$MODELS_DIR/$MODEL_NAME.pmdl"
  curl \
    -fsS \
    -X POST \
    -F "modelName=$MODEL_NAME" \
    -F "example1=@$RECORDINGS_DIR/example1.wav" \
    -F "example2=@$RECORDINGS_DIR/example2.wav" \
    -F "example3=@$RECORDINGS_DIR/example3.wav" \
    --output "$output" \
    "http://127.0.0.1:$PORT/generate"

  if [[ ! -s "$output" ]]; then
    echo "Model generation failed or produced an empty file: $output" >&2
    exit 1
  fi

  mkdir -p "$(dirname "$TARGET_MODEL")"
  cp "$output" "$TARGET_MODEL"
  echo "Generated $output"
  echo "Installed $TARGET_MODEL"
}

stop_server() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
}

case "${1:-all}" in
  record)
    record_examples
    ;;
  serve)
    start_server
    echo "Open http://127.0.0.1:$PORT in a browser."
    ;;
  train)
    train_model
    ;;
  all)
    record_examples
    train_model
    ;;
  stop)
    stop_server
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage
    exit 2
    ;;
esac
