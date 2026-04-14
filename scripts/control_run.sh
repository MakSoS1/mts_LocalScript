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

pytest -q

python -m app.benchmark.runner --model localscript-qwen25coder7b --dataset "${PUBLIC_DATASET}" --mode R3
python -m app.benchmark.runner --model localscript-qwen25coder7b --dataset "${AUGMENTED_DATASET}" --mode R3
python scripts/compare_reports.py

ollama ps
nvidia-smi --query-gpu=timestamp,name,memory.total,memory.used,utilization.gpu --format=csv,noheader

echo "Control run complete."
