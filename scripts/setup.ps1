# Creates .env from .env.example with freshly generated secrets (Windows).
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root ".env"
if (Test-Path $envFile) { Write-Host ".env already exists - leaving it alone."; exit 0 }

function New-Hex([int]$bytes) {
  $b = New-Object byte[] $bytes
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
  ($b | ForEach-Object { $_.ToString("x2") }) -join ""
}
function New-Fernet {
  $b = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
  [Convert]::ToBase64String($b).Replace("+", "-").Replace("/", "_")
}

$adminPw = "Strata-" + (New-Hex 6) + "!"
$content = Get-Content (Join-Path $root ".env.example") -Raw
$content = $content -replace "POSTGRES_PASSWORD=.*", "POSTGRES_PASSWORD=$(New-Hex 24)"
$content = $content -replace "REDIS_PASSWORD=.*", "REDIS_PASSWORD=$(New-Hex 24)"
$content = $content -replace "JWT_SECRET=.*", "JWT_SECRET=$(New-Hex 32)"
$content = $content -replace "FILE_ENCRYPTION_KEY=.*", "FILE_ENCRYPTION_KEY=$(New-Fernet)"
$content = $content -replace "BOOTSTRAP_ADMIN_PASSWORD=.*", "BOOTSTRAP_ADMIN_PASSWORD=$adminPw"
[System.IO.File]::WriteAllText($envFile, $content.Replace("`r`n", "`n"))

Write-Host "Created .env"
Write-Host "  First admin:    admin@example.com"
Write-Host "  Admin password: $adminPw   (change it after first sign-in)"
Write-Host "Next: docker compose --profile local-llm up -d --build"
