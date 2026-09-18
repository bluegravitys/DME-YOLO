param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PipArgs
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

$proxyUrl = Get-ProxyUrlFromSystem
if ($proxyUrl) {
    $env:HTTP_PROXY = $proxyUrl
    $env:HTTPS_PROXY = $proxyUrl
    Write-Host "Using Clash proxy: $proxyUrl" -ForegroundColor Cyan
} else {
    Write-Host "System proxy is not enabled. Running pip directly." -ForegroundColor Yellow
}

if (-not $PipArgs -or $PipArgs.Count -eq 0) {
    $PipArgs = @("list")
}

& python -m pip @PipArgs
exit $LASTEXITCODE
