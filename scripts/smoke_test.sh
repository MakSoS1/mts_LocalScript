#!/usr/bin/env bash
set -euo pipefail

curl -s http://localhost:8080/health | jq .

curl -s -X POST http://localhost:8080/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Верни последний email из wf.vars.users"}' | jq .
