$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

function Invoke-Checked {
  param(
    [Parameter(Mandatory = $true)][string]$Command,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Args
  )
  & $Command @Args
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed ($LASTEXITCODE): $Command $($Args -join ' ')"
  }
}

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
}

Write-Host "[1/3] Pulling base model qwen2.5-coder:7b"
Invoke-Checked ollama pull qwen2.5-coder:7b

Write-Host "[2/3] Creating runtime alias localscript-qwen25coder7b"
Invoke-Checked ollama create localscript-qwen25coder7b -f Modelfiles/qwen25coder7b

Write-Host "[3/3] Starting API via docker compose"
Invoke-Checked docker info
${serverOs} = (& docker version --format "{{.Server.Os}}")
if ($LASTEXITCODE -ne 0) {
  throw "Cannot detect docker server OS."
}
if ($serverOs.Trim().ToLower() -ne "linux") {
  throw "Docker daemon is '$serverOs'. Switch Docker Desktop to Linux containers mode."
}
Invoke-Checked docker compose up --build -d

Write-Host "Bootstrap complete. Health: http://localhost:8080/health"
