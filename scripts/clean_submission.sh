#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

find app/reports -maxdepth 1 -type f \( -name "*.json" -o -name "*.md" -o -name "*.csv" \) -delete || true
find tools/eval_pack/reports -maxdepth 1 -type f \( -name "*.json" -o -name "*.md" -o -name "*.csv" \) -delete || true
rm -rf .pytest_cache
find . -type d -name "__pycache__" -prune -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
find . -type f -name ".DS_Store" -delete

echo "Submission workspace cleaned."
