$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

function Invoke-Checked {
  param(
    [Parameter(Mandatory = $true)][string]$Command,
    [string[]]$Args = @()
  )
  & $Command @Args
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed ($LASTEXITCODE): $Command $($Args -join ' ')"
  }
}

function Test-Command {
  param([Parameter(Mandatory = $true)][string]$Name)
  $cmd = Get-Command $Name -ErrorAction SilentlyContinue
  return $null -ne $cmd
}

if (-not (Test-Command "docker")) {
  throw "Missing required command: docker"
}
if (-not (Test-Command "ollama")) {
  throw "Missing required command: ollama"
}

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
}

$ModelAlias = if ($env:MODEL_ALIAS) { $env:MODEL_ALIAS } else { "localscript-qwen25coder7b" }
$BaseModel = if ($env:BASE_MODEL) { $env:BASE_MODEL } else { "qwen2.5-coder:7b" }
$BaseImageAlias = if ($env:BASE_IMAGE_ALIAS) { $env:BASE_IMAGE_ALIAS } else { "localscript-python311-slim:local" }
$ApiPort = if ($env:API_PORT) { $env:API_PORT } else { "8080" }
$FallbackApiPort = if ($env:FALLBACK_API_PORT) { $env:FALLBACK_API_PORT } else { "18080" }

Invoke-Checked -Command docker -Args @("info")
$serverOs = (& docker version --format "{{.Server.Os}}")
if ($LASTEXITCODE -ne 0) {
  throw "Cannot detect docker server OS."
}
if ($serverOs.Trim().ToLower() -ne "linux") {
  throw "Docker daemon is '$serverOs'. Switch Docker Desktop to Linux containers mode."
}

$portInUse = $false
try {
  $listen = Get-NetTCPConnection -LocalPort ([int]$ApiPort) -State Listen -ErrorAction SilentlyContinue
  $portInUse = $null -ne $listen
} catch {
  $matches = netstat -ano | Select-String ":$ApiPort\\s+.*LISTENING"
  $portInUse = $matches.Count -gt 0
}

if ($portInUse) {
  Write-Warning "Port $ApiPort is already busy. Falling back to $FallbackApiPort."
  $ApiPort = $FallbackApiPort
}
$env:API_PORT = "$ApiPort"
Set-Content -Path ".api-port" -Value "$ApiPort"

Write-Host "[1/5] Ensuring Ollama model $ModelAlias"
& ollama show $ModelAlias *> $null
if ($LASTEXITCODE -ne 0) {
  Invoke-Checked -Command ollama -Args @("pull", $BaseModel)
  Invoke-Checked -Command ollama -Args @("create", $ModelAlias, "-f", "Modelfiles/qwen25coder7b")
}

Write-Host "[2/5] Ensuring local base image alias $BaseImageAlias"
& docker image inspect $BaseImageAlias *> $null
if ($LASTEXITCODE -ne 0) {
  & docker image inspect python:3.11-slim *> $null
  if ($LASTEXITCODE -ne 0) {
    Invoke-Checked -Command docker -Args @("pull", "python:3.11-slim")
  }
  Invoke-Checked -Command docker -Args @("tag", "python:3.11-slim", $BaseImageAlias)
}

Write-Host "[3/5] Building API image"
$env:COMPOSE_BAKE = "false"
$env:DOCKER_BUILDKIT = "0"
$env:COMPOSE_DOCKER_CLI_BUILD = "0"
$env:BASE_IMAGE = $BaseImageAlias
Invoke-Checked -Command docker -Args @("build", "--build-arg", "BASE_IMAGE=$($env:BASE_IMAGE)", "-f", "docker/Dockerfile.api", "-t", "localscript-agent-api:latest", ".")

Write-Host "[4/5] Starting API container"
Invoke-Checked -Command docker -Args @("compose", "up", "--no-build", "-d", "api")

Write-Host "[5/5] Health check"
$healthOk = $false
for ($i = 0; $i -lt 20; $i++) {
  try {
    Invoke-Checked -Command docker -Args @("compose", "exec", "-T", "api", "/bin/bash", "-lc", "curl -sS http://localhost:8080/health")
    $healthOk = $true
    break
  } catch {
    Start-Sleep -Seconds 1
  }
}

if (-not $healthOk) {
  Write-Warning "Container health endpoint is not ready yet."
}

Write-Host ""
Write-Host "API is running in background."
Write-Host "Stop command: docker compose stop api"
Write-Host "GUI URL: http://localhost:$ApiPort/ui"
