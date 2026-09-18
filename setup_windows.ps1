param(
    [ValidateSet("gpu", "cpu")]
    [string]$Mode = "gpu",

    [string]$PythonVersion = "3.10.11",

    [string]$PythonInstallDir = "$env:LOCALAPPDATA\\Programs\\Python\\Python310",

    [string]$VenvDir = ".venv"
)

$ErrorActionPreference = "Stop"

function Get-SystemProxyUrl {
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

function Enable-ProxyForPip {
    $proxyUrl = Get-SystemProxyUrl
    if ($proxyUrl) {
        $env:HTTP_PROXY = $proxyUrl
        $env:HTTPS_PROXY = $proxyUrl
        Write-Step "Using system proxy for downloads: $proxyUrl"
    }
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-Command {
    param([string]$CommandName)
    return [bool](Get-Command $CommandName -ErrorAction SilentlyContinue)
}

function Get-PythonExe {
    $candidates = @(
        (Join-Path $PythonInstallDir "python.exe"),
        "python",
        "py -3.10"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -eq "python" -and -not (Test-Command "python")) {
            continue
        }
        if ($candidate -eq "py -3.10" -and -not (Test-Command "py")) {
            continue
        }
        if ($candidate -like "*.exe" -and -not (Test-Path $candidate)) {
            continue
        }
        return $candidate
    }

    return $null
}

function Install-Python {
    param(
        [string]$Version,
        [string]$TargetDir
    )

    $installerUrl = "https://www.python.org/ftp/python/$Version/python-$Version-amd64.exe"
    $installerPath = Join-Path $env:TEMP "python-$Version-amd64.exe"

    Write-Step "Downloading Python $Version from python.org"
    Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath

    Write-Step "Installing Python $Version to $TargetDir"
    $installArgs = @(
        "/quiet",
        "InstallAllUsers=0",
        "Include_launcher=1",
        "PrependPath=1",
        "Include_test=0",
        "SimpleInstall=1",
        "TargetDir=$TargetDir"
    )
    Start-Process -FilePath $installerPath -ArgumentList $installArgs -Wait

    if (-not (Test-Path (Join-Path $TargetDir "python.exe"))) {
        throw "Python installation did not produce $TargetDir\\python.exe"
    }
}

function Backup-BrokenVenv {
    param([string]$Dir)

    if (-not (Test-Path $Dir)) {
        return
    }

    $venvPython = Join-Path $Dir "Scripts\\python.exe"
    if (Test-Path $venvPython) {
        try {
            & $venvPython --version | Out-Null
            return
        } catch {
        }
    }

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupDir = "$Dir.broken-$stamp"
    Write-Step "Existing virtual environment is broken, renaming to $backupDir"
    Move-Item -Path $Dir -Destination $backupDir
}

function Invoke-Python {
    param(
        [string]$PythonCommand,
        [string[]]$Arguments
    )

    if ($PythonCommand -eq "py -3.10") {
        & py -3.10 @Arguments
    } else {
        & $PythonCommand @Arguments
    }
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

Write-Step "Preparing Windows environment for the YOLO PCB project"
Enable-ProxyForPip

$pythonCommand = Get-PythonExe
if (-not $pythonCommand) {
    Install-Python -Version $PythonVersion -TargetDir $PythonInstallDir
    $pythonCommand = Join-Path $PythonInstallDir "python.exe"
}

Write-Step "Using Python command: $pythonCommand"
Invoke-Python -PythonCommand $pythonCommand -Arguments @("--version")

Backup-BrokenVenv -Dir $VenvDir

Write-Step "Creating virtual environment at $VenvDir"
Invoke-Python -PythonCommand $pythonCommand -Arguments @("-m", "venv", $VenvDir)

$venvPython = Join-Path $projectRoot "$VenvDir\\Scripts\\python.exe"
$venvPip = Join-Path $projectRoot "$VenvDir\\Scripts\\pip.exe"

Write-Step "Upgrading pip tooling"
& $venvPython -m pip install --upgrade pip setuptools wheel

if ($Mode -eq "gpu") {
    Write-Step "Installing PyTorch with CUDA 12.8 wheels"
    & $venvPip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
    $requirementsFile = "requirements-windows-gpu.txt"
} else {
    Write-Step "Installing CPU-only PyTorch"
    & $venvPip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    $requirementsFile = "requirements-windows-cpu.txt"
}

Write-Step "Installing project dependencies from $requirementsFile"
& $venvPip install -r $requirementsFile

Write-Step "Installing the local ultralytics package in editable mode"
& $venvPip install -e . --no-deps

Write-Step "Running environment verification"
& $venvPython -c "import sys; import torch; import gradio; import cv2; import ultralytics; print('python=', sys.version); print('torch=', torch.__version__); print('cuda_available=', torch.cuda.is_available()); print('gradio=', gradio.__version__); print('opencv=', cv2.__version__); print('ultralytics=', ultralytics.__version__)"

Write-Step "Environment setup finished"
Write-Host "Activate with: .\\$VenvDir\\Scripts\\Activate.ps1" -ForegroundColor Green
Write-Host "Run app with: .\\$VenvDir\\Scripts\\python.exe app.py" -ForegroundColor Green
