$jsonPath = "$env:USERPROFILE\.docker\config.json"
$json = Get-Content $jsonPath | ConvertFrom-Json
$json | Add-Member -NotePropertyName 'credsStore' -NotePropertyValue 'wincred' -Force
$json | ConvertTo-Json -Depth 10 | Set-Content $jsonPath
Write-Host "Updated config:"
Get-Content $jsonPath
