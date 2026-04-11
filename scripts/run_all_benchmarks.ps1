param(
  [string]$Mode = "R3",
  [string]$Dataset = "app/benchmark/dataset_public.jsonl",
  [string]$Models = "localscript-qwen25coder7b"
)

$ErrorActionPreference = "Stop"
$models = $Models.Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }

foreach ($model in $models) {
  Write-Host "Running benchmark for $model"
  py -m app.benchmark.runner --model $model --dataset $Dataset --mode $Mode
}
