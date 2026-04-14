#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

DEFAULT_PORT="${API_PORT:-}"
if [[ -z "${DEFAULT_PORT}" && -f .api-port ]]; then
  DEFAULT_PORT="$(tr -d '[:space:]' < .api-port)"
fi
if [[ -z "${DEFAULT_PORT}" ]]; then
  DEFAULT_PORT="8080"
fi
URL="${1:-http://localhost:${DEFAULT_PORT}/ui}"

echo "GUI URL: ${URL}"

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "${URL}" >/dev/null 2>&1 || true
elif command -v open >/dev/null 2>&1; then
  open "${URL}" >/dev/null 2>&1 || true
else
  echo "Open this URL manually in browser: ${URL}"
fi
