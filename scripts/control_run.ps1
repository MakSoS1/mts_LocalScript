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

py -m pytest -q

py -m app.benchmark.runner --model localscript-qwen25coder7b --dataset $PublicDataset --mode R3
py -m app.benchmark.runner --model localscript-qwen25coder7b --dataset $AugmentedDataset --mode R3
py scripts/compare_reports.py

ollama ps
nvidia-smi --query-gpu=timestamp,name,memory.total,memory.used,utilization.gpu --format=csv,noheader

Write-Host "Control run complete."
