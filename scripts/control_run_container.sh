#!/usr/bin/env bash
set -euo pipefail

PUBLIC_DATASET="${1:-app/benchmark/dataset_public.jsonl}"
AUGMENTED_DATASET="${2:-app/benchmark/dataset_augmented.jsonl}"

cd "$(dirname "$0")/.."

./scripts/clean_submission.sh

export OLLAMA_BASE_URL="http://localhost:11434"
export OLLAMA_BASE_URLS="http://localhost:11434"
export REQUIRED_DEMO_MODEL="localscript-qwen25coder7b"
export DEFAULT_MODEL="localscript-qwen25coder7b"
export OPTIONAL_BENCHMARK_MODELS=""
export STRICT_MODELS=""
export OLLAMA_NUM_BATCH="1"
export OLLAMA_NUM_PARALLEL="1"
export COMPOSE_BAKE="false"
export DOCKER_BUILDKIT="0"
export COMPOSE_DOCKER_CLI_BUILD="0"
export BASE_IMAGE="localscript-python311-slim:local"

if ! docker image inspect "${BASE_IMAGE}" >/dev/null 2>&1; then
  if ! docker image inspect python:3.11-slim >/dev/null 2>&1; then
    echo "Base image python:3.11-slim is not available locally. Pull it from an interactive Docker session first."
    exit 1
  fi
  docker tag python:3.11-slim "${BASE_IMAGE}"
fi

python scripts/judge_check.py --phase preflight --model localscript-qwen25coder7b

docker build --build-arg "BASE_IMAGE=${BASE_IMAGE}" -f docker/Dockerfile.api -t localscript-agent-api:latest .

docker compose up --no-build -d

mkdir -p app/reports
VRAM_LOG="app/reports/vram_samples.csv"
: > "${VRAM_LOG}"
nvidia-smi --query-gpu=timestamp,name,memory.total,memory.used,utilization.gpu --format=csv,noheader -lms 500 > "${VRAM_LOG}" &
VRAM_MON_PID=$!
cleanup() {
  if kill -0 "${VRAM_MON_PID}" >/dev/null 2>&1; then
    kill "${VRAM_MON_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

docker compose exec -T api /bin/bash -lc "\
set -euo pipefail; \
export OLLAMA_BASE_URL=http://host.docker.internal:11434; \
export OLLAMA_BASE_URLS=http://host.docker.internal:11434,http://localhost:11434; \
export REQUIRED_DEMO_MODEL=localscript-qwen25coder7b; \
export DEFAULT_MODEL=localscript-qwen25coder7b; \
export OPTIONAL_BENCHMARK_MODELS=; \
export STRICT_MODELS=; \
export OLLAMA_NUM_BATCH=1; \
export OLLAMA_NUM_PARALLEL=1; \
export SYNTAX_REQUIRE_LUAC=true; \
pytest -q; \
python -m app.benchmark.runner --model localscript-qwen25coder7b --dataset '${PUBLIC_DATASET}' --mode R3; \
python -m app.benchmark.runner --model localscript-qwen25coder7b --dataset '${AUGMENTED_DATASET}' --mode R3; \
python scripts/compare_reports.py \
"

cleanup
python scripts/judge_check.py --phase post --model localscript-qwen25coder7b --vram-log "${VRAM_LOG}" --max-vram-mib 8192

ollama ps
nvidia-smi --query-gpu=timestamp,name,memory.total,memory.used,utilization.gpu --format=csv,noheader

echo "Container control run complete."
