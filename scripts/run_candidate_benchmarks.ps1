param(
  [string]$Mode = "R3",
  [string]$Dataset = "app/benchmark/dataset_public.jsonl"
)

$ErrorActionPreference = "Stop"

$models = @(
  "localscript-qwen25coder7b",
  "localscript-deepseekr1-8b",
  "localscript-qwen3-8b",
  "localscript-gemma3-4b",
  "localscript-qwen25coder3b",
  "localscript-gemma4"
)

$env:OLLAMA_BASE_URL = "http://localhost:11434"
$env:OLLAMA_BASE_URLS = "http://localhost:11434"

foreach ($model in $models) {
  Write-Host "Running benchmark for $model"
  $env:STRICT_MODELS = $model
  py -m app.benchmark.runner --model $model --dataset $Dataset --mode $Mode
}
