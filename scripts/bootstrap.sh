#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

echo "[1/3] Pulling base model qwen2.5-coder:7b"
ollama pull qwen2.5-coder:7b

echo "[2/3] Creating runtime alias localscript-qwen25coder7b"
ollama create localscript-qwen25coder7b -f Modelfiles/qwen25coder7b

echo "[3/3] Starting API via docker compose"
docker info >/dev/null
server_os="$(docker version --format '{{.Server.Os}}')"
if [[ "${server_os}" != "linux" ]]; then
  echo "Docker server OS is '${server_os}'. Switch Docker to Linux containers mode." >&2
  exit 1
fi
docker compose up --build -d

echo "Bootstrap complete. Health: http://localhost:8080/health"
