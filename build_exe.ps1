param(
    [switch]$OneFile,
    [switch]$Windowed,
    [string]$VenvDir = ".venv-pack"
)

$ErrorActionPreference = "Stop"

function Get-ProxyUrlFromSystem {
    $internetSettings = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    if ($internetSettings.ProxyEnable -ne 1 -or [string]::IsNullOrWhiteSpace($internetSettings.ProxyServer)) {
        return $null
    }

    $proxyServer = $internetSettings.ProxyServer.Trim()
    if ($proxyServer -match "=") {
        $pairs = @{}
        foreach ($entry in $proxyServer.Split(";")) {
            if ($entry -match "=") {
                $parts = $entry.Split("=", 2)
                $pairs[$parts[0].ToLower()] = $parts[1]
            }
        }
        if ($pairs.ContainsKey("http")) {
            $proxyServer = $pairs["http"]
        } elseif ($pairs.ContainsKey("https")) {
            $proxyServer = $pairs["https"]
        } else {
            $proxyServer = $pairs.Values | Select-Object -First 1
        }
    }

    if ($proxyServer -notmatch "^[a-zA-Z]+://") {
        $proxyServer = "http://$proxyServer"
    }
    return $proxyServer
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $projectRoot "$VenvDir\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Virtual environment not found at $VenvDir. Create it first before packaging."
}

Set-Location $projectRoot

$proxyUrl = Get-ProxyUrlFromSystem
if ($proxyUrl) {
    $env:HTTP_PROXY = $proxyUrl
    $env:HTTPS_PROXY = $proxyUrl
    Write-Host "Using proxy for pip: $proxyUrl" -ForegroundColor Cyan
}

$pyinstallerCheck = Join-Path $projectRoot "$VenvDir\Lib\site-packages\PyInstaller"
if (-not (Test-Path $pyinstallerCheck)) {
    Write-Host "PyInstaller not found in .venv. Installing..." -ForegroundColor Yellow
    & $pythonExe -m pip install pyinstaller --index-url https://pypi.org/simple --trusted-host pypi.org --trusted-host files.pythonhosted.org
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller installation failed."
    }
}

$buildMode = if ($OneFile) { "--onefile" } else { "--onedir" }
$consoleMode = if ($Windowed) { "--noconsole" } else { "--console" }

$arguments = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--name", "PCBDefectStudio",
    $buildMode,
    $consoleMode,
    "--add-data", "templates;templates",
    "--add-data", "static;static",
    "--add-data", "best.pt;.",
    "--add-data", "classes.txt;.",
    "--add-data", "PCB_remake\test\images\01_missing_hole_04.jpg;PCB_remake\test\images",
    "--add-data", "PCB_remake\test\images\01_mouse_bite_12.jpg;PCB_remake\test\images",
    "--add-data", "PCB_remake\test\images\01_open_circuit_04_create_5.jpg;PCB_remake\test\images",
    "--copy-metadata", "ultralytics",
    "--copy-metadata", "timm",
    "--exclude-module", "gradio",
    "--exclude-module", "tensorboard",
    "launcher.py"
)

Write-Host "Building EXE package..." -ForegroundColor Cyan
& $pythonExe @arguments
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

Write-Host ""
Write-Host "Build complete." -ForegroundColor Green
if ($OneFile) {
    Write-Host "Output: $projectRoot\dist\PCBDefectStudio.exe"
} else {
    Write-Host "Output: $projectRoot\dist\PCBDefectStudio\PCBDefectStudio.exe"
}
