#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-R3}"
DATASET="${2:-app/benchmark/dataset_public.jsonl}"
MODELS_CSV="${3:-localscript-qwen25coder7b}"

IFS=',' read -r -a MODELS <<< "${MODELS_CSV}"

for model in "${MODELS[@]}"; do
  model="$(echo "${model}" | xargs)"
  [[ -z "${model}" ]] && continue
  echo "Running benchmark for ${model}"
  python -m app.benchmark.runner --model "${model}" --dataset "${DATASET}" --mode "${MODE}"
done
