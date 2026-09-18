$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $projectRoot ".venv\\Scripts\\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Virtual environment not found. Run .\\setup_windows.ps1 first."
}

Set-Location $projectRoot
& $pythonExe app.py

