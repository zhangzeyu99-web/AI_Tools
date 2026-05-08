#Requires -Version 5.1
<#
.SYNOPSIS
    OpenClaw full startup: OpenViking first, then Gateway.
.DESCRIPTION
    Safe to call repeatedly. It skips services that are already listening unless
    -Force is passed.
#>

param(
    [switch]$Force
)

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHON_PATH = "C:\Users\Administrator\AppData\Local\Programs\Python\Python314"
$env:NO_PROXY = "localhost,127.0.0.1,::1"
$env:no_proxy = "localhost,127.0.0.1,::1"
$env:Path = "D:\nodejs;$env:PYTHON_PATH\Scripts;$env:PYTHON_PATH;$env:Path"

$ErrorActionPreference = "Continue"
$LogFile = "$env:USERPROFILE\.openclaw\logs\startup.log"

function Write-Log {
    param([string]$Msg, [string]$Level = "INFO")
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [$Level] $Msg"
    Write-Host $line
    $logDir = Split-Path $LogFile -Parent
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Test-Port {
    param([int]$Port)
    return [bool](Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Wait-Port {
    param([int]$Port, [string]$Name, [int]$TimeoutSec = 120)
    $elapsed = 0
    while ($elapsed -lt $TimeoutSec) {
        if (Test-Port $Port) {
            Write-Log "${Name} port ${Port}: READY (${elapsed}s)"
            return $true
        }
        Start-Sleep -Seconds 3
        $elapsed += 3
    }
    Write-Log "${Name} port ${Port}: TIMEOUT after ${TimeoutSec}s" "ERROR"
    return $false
}

Write-Log "===== OpenClaw Startup ====="

$ovRunning = Test-Port 1933
if ($ovRunning -and -not $Force) {
    Write-Log "OpenViking already running on port 1933, skipping"
} else {
    if ($Force) {
        Write-Log "Force mode: killing OpenViking..."
        Stop-Process -Name "openviking-server" -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
    Write-Log "Starting OpenViking..."
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "$env:USERPROFILE\.openviking\start-openviking.bat" -WindowStyle Hidden
    $ovOk = Wait-Port -Port 1933 -Name "OpenViking" -TimeoutSec 90
    if (-not $ovOk) {
        Write-Log "OpenViking failed to start. Gateway will start without vector memory." "WARN"
    }
}

$gwRunning = Test-Port 18789
if ($gwRunning -and -not $Force) {
    Write-Log "Gateway already running on port 18789, skipping"
} else {
    if ($Force) {
        Write-Log "Force mode: killing Gateway..."
        Get-Process -Name "node" -ErrorAction SilentlyContinue | ForEach-Object {
            $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
            if ($cmd -like "*gateway*") { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
        }
        Start-Sleep -Seconds 2
    }
    Write-Log "Starting Gateway..."
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "$env:USERPROFILE\.openclaw\gateway.cmd" -WindowStyle Hidden
    $gwOk = Wait-Port -Port 18789 -Name "Gateway" -TimeoutSec 30
    if (-not $gwOk) {
        Write-Log "Gateway failed to start!" "ERROR"
    }
}

$ovFinal = Test-Port 1933
$gwFinal = Test-Port 18789
Write-Log "Final status: OpenViking=$(if ($ovFinal) {'OK'} else {'DOWN'}) Gateway=$(if ($gwFinal) {'OK'} else {'DOWN'})"

if ($ovFinal -and $gwFinal) {
    Write-Log "All services UP" "OK"
    exit 0
}

Write-Log "Some services failed to start" "ERROR"
exit 1

