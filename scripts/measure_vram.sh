#!/usr/bin/env bash
set -euo pipefail

INTERVAL="${1:-1}"
COUNT="${2:-60}"

for ((i=1; i<=COUNT; i++)); do
  nvidia-smi --query-gpu=timestamp,name,memory.used,memory.total --format=csv,noheader
  sleep "${INTERVAL}"
done
