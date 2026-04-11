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
$env:SYNTAX_REQUIRE_LUAC = "true"

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
  py scripts/judge_check.py --phase preflight --model localscript-qwen25coder7b --strict-luac
  if ($LASTEXITCODE -ne 0) { throw "judge preflight failed with exit code $LASTEXITCODE" }

  py -m pytest -q
  if ($LASTEXITCODE -ne 0) { throw "pytest failed with exit code $LASTEXITCODE" }

  py -m app.benchmark.runner --model localscript-qwen25coder7b --dataset $PublicDataset --mode R3
  if ($LASTEXITCODE -ne 0) { throw "public benchmark failed with exit code $LASTEXITCODE" }
  py -m app.benchmark.runner --model localscript-qwen25coder7b --dataset $AugmentedDataset --mode R3
  if ($LASTEXITCODE -ne 0) { throw "augmented benchmark failed with exit code $LASTEXITCODE" }
  py scripts/compare_reports.py
  if ($LASTEXITCODE -ne 0) { throw "compare reports failed with exit code $LASTEXITCODE" }
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

Write-Host "Control run complete."
