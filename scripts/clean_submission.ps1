$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

if (Test-Path "app\\reports") {
  Get-ChildItem "app\\reports" -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in @(".json", ".md") } |
    Remove-Item -Force
}

if (Test-Path ".pytest_cache") {
  Remove-Item ".pytest_cache" -Recurse -Force
}

Get-ChildItem -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Get-ChildItem -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem -Recurse -File -Filter ".DS_Store" -ErrorAction SilentlyContinue | Remove-Item -Force

Write-Host "Submission workspace cleaned."
