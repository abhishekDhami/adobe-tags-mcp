$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root ".venv"

Write-Host "Creating virtual environment at $Venv ..."
py -3 -m venv $Venv

$Python = Join-Path $Venv "Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $Root "api\requirements-dev.txt")
& $Python -m pip install -r (Join-Path $Root "mcp\requirements-dev.txt")

$ApiEnv = Join-Path $Root "api\.env"
$McpEnv = Join-Path $Root "mcp\.env"
if (-not (Test-Path $ApiEnv)) {
    Copy-Item (Join-Path $Root "api\.env.example") $ApiEnv
    Write-Host "Created api\.env from api\.env.example — add Adobe credentials"
}
if (-not (Test-Path $McpEnv)) {
    Copy-Item (Join-Path $Root "mcp\.env.example") $McpEnv
    Write-Host "Created mcp\.env from mcp\.env.example — match MCP_API_KEY with api\.env"
}

Write-Host "Setup complete. Activate with: .\.venv\Scripts\Activate.ps1"
