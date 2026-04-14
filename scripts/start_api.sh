#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

MODEL_ALIAS="${MODEL_ALIAS:-localscript-qwen25coder7b}"
BASE_MODEL="${BASE_MODEL:-qwen2.5-coder:7b}"
BASE_IMAGE_ALIAS="${BASE_IMAGE_ALIAS:-localscript-python311-slim:local}"
API_PORT_VALUE="${API_PORT:-8080}"
FALLBACK_API_PORT="${FALLBACK_API_PORT:-18080}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd docker
require_cmd ollama

port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :${port}" | tail -n +2 | grep -q .
    return $?
  fi
  if command -v netstat >/dev/null 2>&1; then
    netstat -an 2>/dev/null | grep -E "[:.]${port}[[:space:]].*LISTEN" >/dev/null 2>&1
    return $?
  fi
  return 1
}

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

docker info >/dev/null
server_os="$(docker version --format '{{.Server.Os}}')"
if [[ "${server_os}" != "linux" ]]; then
  echo "Docker server OS is '${server_os}'. Switch Docker to Linux containers mode." >&2
  exit 1
fi

if port_in_use "${API_PORT_VALUE}"; then
  echo "Port ${API_PORT_VALUE} is already busy. Falling back to ${FALLBACK_API_PORT}."
  API_PORT_VALUE="${FALLBACK_API_PORT}"
fi
export API_PORT="${API_PORT_VALUE}"
printf '%s\n' "${API_PORT}" > .api-port

echo "[1/5] Ensuring Ollama model ${MODEL_ALIAS}"
if ! ollama show "${MODEL_ALIAS}" >/dev/null 2>&1; then
  ollama pull "${BASE_MODEL}"
  ollama create "${MODEL_ALIAS}" -f Modelfiles/qwen25coder7b
fi

echo "[2/5] Ensuring local base image alias ${BASE_IMAGE_ALIAS}"
if ! docker image inspect "${BASE_IMAGE_ALIAS}" >/dev/null 2>&1; then
  if ! docker image inspect python:3.11-slim >/dev/null 2>&1; then
    docker pull python:3.11-slim
  fi
  docker tag python:3.11-slim "${BASE_IMAGE_ALIAS}"
fi

echo "[3/5] Building API image"
export COMPOSE_BAKE=false
export DOCKER_BUILDKIT=0
export COMPOSE_DOCKER_CLI_BUILD=0
export BASE_IMAGE="${BASE_IMAGE_ALIAS}"
docker build --build-arg "BASE_IMAGE=${BASE_IMAGE}" -f docker/Dockerfile.api -t localscript-agent-api:latest .

echo "[4/5] Starting API container"
docker compose up --no-build -d api

echo "[5/5] Health check"
health_json=""
for ((i=1; i<=20; i++)); do
  if health_json="$(docker compose exec -T api /bin/bash -lc "curl -sS http://localhost:8080/health" 2>/dev/null)"; then
    break
  fi
  sleep 1
done

if [[ -n "${health_json}" ]]; then
  echo "${health_json}"
else
  echo "Warning: container health endpoint is not ready yet."
fi

echo
echo "API is running in background."
echo "Stop command: docker compose stop api"
echo "GUI URL: http://localhost:${API_PORT}/ui"
