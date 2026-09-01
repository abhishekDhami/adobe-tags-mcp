$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "Virtual environment not found. Run scripts\setup.ps1 first."
}

Write-Host "Starting API on http://127.0.0.1:3000 (new window) ..."
Start-Process -FilePath $Python -ArgumentList "-m", "app.main" -WorkingDirectory (Join-Path $Root "api")

Write-Host ""
Write-Host "In a second terminal, start MCP:"
Write-Host "  cd $Root\mcp"
Write-Host "  $Python -m app.server"
Write-Host ""
Write-Host "Validate API: Invoke-RestMethod http://127.0.0.1:3000/health"
