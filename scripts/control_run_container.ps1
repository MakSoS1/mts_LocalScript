param(
  [string]$PublicDataset = "app/benchmark/dataset_public.jsonl",
  [string]$AugmentedDataset = "app/benchmark/dataset_augmented.jsonl"
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

powershell -ExecutionPolicy Bypass -File .\scripts\clean_submission.ps1

$env:OLLAMA_BASE_URL = "http://localhost:11434"
$env:OLLAMA_BASE_URLS = "http://localhost:11434"
$env:REQUIRED_DEMO_MODEL = "localscript-qwen25coder7b"
$env:DEFAULT_MODEL = "localscript-qwen25coder7b"
$env:OPTIONAL_BENCHMARK_MODELS = ""
$env:STRICT_MODELS = ""
$env:OLLAMA_NUM_BATCH = "1"
$env:OLLAMA_NUM_PARALLEL = "1"
$env:COMPOSE_BAKE = "false"
$env:DOCKER_BUILDKIT = "0"
$env:COMPOSE_DOCKER_CLI_BUILD = "0"
$env:BASE_IMAGE = "localscript-python311-slim:local"

docker image inspect $env:BASE_IMAGE *> $null
if ($LASTEXITCODE -ne 0) {
  docker image inspect python:3.11-slim *> $null
  if ($LASTEXITCODE -ne 0) {
    throw "Base image python:3.11-slim is not available locally. Pull it from an interactive Docker session first."
  }
  docker tag python:3.11-slim $env:BASE_IMAGE
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to tag python:3.11-slim as $($env:BASE_IMAGE)."
  }
}

py scripts/judge_check.py --phase preflight --model localscript-qwen25coder7b
if ($LASTEXITCODE -ne 0) { throw "judge preflight failed with exit code $LASTEXITCODE" }

docker build --build-arg "BASE_IMAGE=$($env:BASE_IMAGE)" -f docker/Dockerfile.api -t localscript-agent-api:latest .
if ($LASTEXITCODE -ne 0) { throw "docker build failed with exit code $LASTEXITCODE" }

docker compose up --no-build -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed with exit code $LASTEXITCODE" }

if (-not (Test-Path "app\\reports")) {
  New-Item -ItemType Directory -Path "app\\reports" | Out-Null
}
$vramLog = "app\\reports\\vram_samples.csv"
Set-Content -Path $vramLog -Value ""

$vramJob = Start-Job -ScriptBlock {
  param($LogPath)
  while ($true) {
    try {
      & nvidia-smi --query-gpu=timestamp,name,memory.total,memory.used,utilization.gpu --format=csv,noheader |
        Out-File -FilePath $LogPath -Append -Encoding utf8
    } catch {
    }
    Start-Sleep -Milliseconds 500
  }
} -ArgumentList (Resolve-Path $vramLog)

try {
  docker compose exec -T api /bin/bash -lc "export OLLAMA_BASE_URL=http://host.docker.internal:11434; export OLLAMA_BASE_URLS=http://host.docker.internal:11434,http://localhost:11434; export REQUIRED_DEMO_MODEL=localscript-qwen25coder7b; export DEFAULT_MODEL=localscript-qwen25coder7b; export OPTIONAL_BENCHMARK_MODELS=; export STRICT_MODELS=; export OLLAMA_NUM_BATCH=1; export OLLAMA_NUM_PARALLEL=1; export SYNTAX_REQUIRE_LUAC=true; pytest -q"
  if ($LASTEXITCODE -ne 0) { throw "container pytest failed with exit code $LASTEXITCODE" }
  docker compose exec -T api /bin/bash -lc "export OLLAMA_BASE_URL=http://host.docker.internal:11434; export OLLAMA_BASE_URLS=http://host.docker.internal:11434,http://localhost:11434; export REQUIRED_DEMO_MODEL=localscript-qwen25coder7b; export DEFAULT_MODEL=localscript-qwen25coder7b; export OPTIONAL_BENCHMARK_MODELS=; export STRICT_MODELS=; export OLLAMA_NUM_BATCH=1; export OLLAMA_NUM_PARALLEL=1; export SYNTAX_REQUIRE_LUAC=true; python -m app.benchmark.runner --model localscript-qwen25coder7b --dataset '$PublicDataset' --mode R3"
  if ($LASTEXITCODE -ne 0) { throw "container public benchmark failed with exit code $LASTEXITCODE" }
  docker compose exec -T api /bin/bash -lc "export OLLAMA_BASE_URL=http://host.docker.internal:11434; export OLLAMA_BASE_URLS=http://host.docker.internal:11434,http://localhost:11434; export REQUIRED_DEMO_MODEL=localscript-qwen25coder7b; export DEFAULT_MODEL=localscript-qwen25coder7b; export OPTIONAL_BENCHMARK_MODELS=; export STRICT_MODELS=; export OLLAMA_NUM_BATCH=1; export OLLAMA_NUM_PARALLEL=1; export SYNTAX_REQUIRE_LUAC=true; python -m app.benchmark.runner --model localscript-qwen25coder7b --dataset '$AugmentedDataset' --mode R3"
  if ($LASTEXITCODE -ne 0) { throw "container augmented benchmark failed with exit code $LASTEXITCODE" }
  docker compose exec -T api /bin/bash -lc "python scripts/compare_reports.py"
  if ($LASTEXITCODE -ne 0) { throw "container compare reports failed with exit code $LASTEXITCODE" }
} finally {
  if ($vramJob) {
    Stop-Job -Job $vramJob -ErrorAction SilentlyContinue
    Receive-Job -Job $vramJob -ErrorAction SilentlyContinue | Out-Null
    Remove-Job -Job $vramJob -Force -ErrorAction SilentlyContinue
  }
}

py scripts/judge_check.py --phase post --model localscript-qwen25coder7b --vram-log $vramLog --max-vram-mib 8192
if ($LASTEXITCODE -ne 0) { throw "judge post-check failed with exit code $LASTEXITCODE" }

ollama ps
nvidia-smi --query-gpu=timestamp,name,memory.total,memory.used,utilization.gpu --format=csv,noheader

Write-Host "Container control run complete."
