param(
  [string]$Url = "",
  [switch]$OpenBrowser
)

Set-Location (Join-Path $PSScriptRoot "..")

if (-not $Url) {
  $port = ""
  if ($env:API_PORT) {
    $port = $env:API_PORT
  } elseif (Test-Path ".api-port") {
    $port = (Get-Content ".api-port" -Raw).Trim()
  }
  if (-not $port) {
    $port = "8080"
  }
  $Url = "http://localhost:$port/ui"
}

Write-Host "GUI URL: $Url"

if ($OpenBrowser) {
  Start-Process $Url
}
