param(
    [switch]$OneFile,
    [string]$VenvDir = ".venv-pack"
)

$ErrorActionPreference = "Stop"

function Get-ProxyUrlFromSystem {
    try {
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
    } catch {
        return $null
    }
}

function Get-BasePythonFromVenv {
    param([string]$CfgPath)

    if (-not (Test-Path $CfgPath)) {
        return $null
    }

    $homeLine = Get-Content $CfgPath | Where-Object { $_ -like 'home = *' } | Select-Object -First 1
    if (-not $homeLine) {
        return $null
    }

    $pythonHome = ($homeLine -split '=', 2)[1].Trim()
    if ([string]::IsNullOrWhiteSpace($pythonHome)) {
        return $null
    }

    $pythonExe = Join-Path $pythonHome 'python.exe'
    if (Test-Path $pythonExe) {
        return $pythonExe
    }

    return $null
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvRoot = Join-Path $projectRoot $VenvDir
$venvSitePackages = Join-Path $venvRoot 'Lib\site-packages'
$pyvenvCfg = Join-Path $venvRoot 'pyvenv.cfg'
$pythonExe = Get-BasePythonFromVenv -CfgPath $pyvenvCfg

if (-not $pythonExe) {
    throw "Python runtime not found for $VenvDir."
}

if (-not (Test-Path $venvSitePackages)) {
    throw "site-packages not found at $venvSitePackages."
}

Set-Location $projectRoot
$env:VIRTUAL_ENV = $venvRoot
$env:PYTHONPATH = if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) { $venvSitePackages } else { "$venvSitePackages;$env:PYTHONPATH" }
$env:PATH = "$(Join-Path $venvRoot 'Scripts');$env:PATH"

$proxyUrl = Get-ProxyUrlFromSystem
if ($proxyUrl) {
    $env:HTTP_PROXY = $proxyUrl
    $env:HTTPS_PROXY = $proxyUrl
    Write-Host "Using proxy for packaging: $proxyUrl" -ForegroundColor Cyan
}

$buildMode = if ($OneFile) { "--onefile" } else { "--onedir" }

$arguments = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--name", "PCBDefectClient",
    $buildMode,
    "--noconsole",
    "--add-data", "templates;templates",
    "--add-data", "static;static",
    "--add-data", "best.pt;.",
    "--add-data", "classes.txt;.",
    "--add-data", "PCB_remake\test\images\01_missing_hole_04.jpg;PCB_remake\test\images",
    "--add-data", "PCB_remake\test\images\01_mouse_bite_12.jpg;PCB_remake\test\images",
    "--add-data", "PCB_remake\test\images\01_open_circuit_04_create_5.jpg;PCB_remake\test\images",
    "--copy-metadata", "ultralytics",
    "--copy-metadata", "timm",
    "--copy-metadata", "pywebview",
    "--exclude-module", "gradio",
    "--exclude-module", "tensorboard",
    "desktop_client.py"
)

Write-Host "Building desktop client EXE..." -ForegroundColor Cyan
& $pythonExe @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Desktop client build failed."
}

Write-Host ""
Write-Host "Desktop client build complete." -ForegroundColor Green
if ($OneFile) {
    Write-Host "Output: $projectRoot\dist\PCBDefectClient.exe"
} else {
    Write-Host "Output: $projectRoot\dist\PCBDefectClient\PCBDefectClient.exe"
}