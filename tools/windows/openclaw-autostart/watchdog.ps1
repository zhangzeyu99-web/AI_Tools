#Requires -Version 5.1
<#
.SYNOPSIS
    Lightweight watchdog for Gateway + OpenViking.
.DESCRIPTION
    Monitors and restarts only after repeated failures. It does not compete with
    healthy manual starts.
#>

param(
    [int]$IntervalSeconds = 60
)

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$OutputEncoding = $Utf8NoBom

$env:USERPROFILE = "C:\Users\Administrator"
$env:HOMEDRIVE = "C:"
$env:HOMEPATH = "\Users\Administrator"
$env:HOME = "C:\Users\Administrator"
$env:APPDATA = "C:\Users\Administrator\AppData\Roaming"
$env:LOCALAPPDATA = "C:\Users\Administrator\AppData\Local"
$env:TEMP = "C:\Users\Administrator\AppData\Local\Temp"
$env:TMP = "C:\Users\Administrator\AppData\Local\Temp"
$env:TMPDIR = "C:\Users\Administrator\AppData\Local\Temp"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHON_PATH = "C:\Users\Administrator\AppData\Local\Programs\Python\Python314"
$env:NO_PROXY = "localhost,127.0.0.1,::1"
$env:no_proxy = "localhost,127.0.0.1,::1"
$env:Path = "D:\nodejs;$env:PYTHON_PATH\Scripts;$env:PYTHON_PATH;$env:Path"

$LogFile = "$env:USERPROFILE\.openclaw\logs\watchdog.log"
$BootTime = (Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue).LastBootUpTime
$BootId = if ($BootTime) { $BootTime.ToUniversalTime().ToString("o") } else { (Get-Date).ToUniversalTime().ToString("o") }
$BootAgeSeconds = if ($BootTime) { [int]((Get-Date) - $BootTime).TotalSeconds } else { 0 }
$StartupNotifyScript = "$env:USERPROFILE\.openclaw\scripts\startup-notify.js"

function Write-Log {
    param([string]$Msg, [string]$Level = "INFO")
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [$Level] $Msg"
    $logDir = Split-Path $LogFile -Parent
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
    if (Test-Path $LogFile) {
        $size = (Get-Item $LogFile -ErrorAction SilentlyContinue).Length
        if ($size -gt 512KB) {
            $lines = Get-Content $LogFile -Tail 200
            $lines | Set-Content $LogFile -Encoding UTF8
        }
    }
}

function Test-Port {
    param([int]$Port)
    return [bool](Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Start-OpenViking {
    $already = Get-Process -Name "openviking-server" -ErrorAction SilentlyContinue
    if ($already) {
        Write-Log "OV process exists PID=$($already.Id), waiting for port"
        return
    }
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "$env:USERPROFILE\.openviking\start-openviking.bat" -WindowStyle Hidden
    Write-Log "Started OpenViking"
}

function Start-Gateway {
    $existing = Get-Process -Name "node" -ErrorAction SilentlyContinue | Where-Object {
        $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
        $cmd -like "*gateway*"
    }
    if ($existing) {
        Write-Log "Gateway process exists PID=$($existing.Id), waiting for port"
        return
    }
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "$env:USERPROFILE\.openclaw\gateway.cmd" -WindowStyle Hidden
    Write-Log "Started Gateway"
}

Write-Log "Watchdog started (interval=${IntervalSeconds}s)"

$gwDownCount = 0
$ovDownCount = 0
$checks = 0
$bootNotifyChecked = $false

Start-Sleep -Seconds 30

$initialGw = Test-Port 18789
$initialOv = Test-Port 1933
if ($BootAgeSeconds -lt 1800 -and (-not $initialGw -or -not $initialOv)) {
    Write-Log "Boot auto-start check: services missing (GW=$initialGw OV=$initialOv), running startup-all immediately"
    & powershell -ExecutionPolicy Bypass -NoProfile -File "$env:USERPROFILE\.openclaw\scripts\startup-all.ps1" 2>&1 | ForEach-Object { Write-Log "  $_" }
    Start-Sleep -Seconds 20
}

while ($true) {
    $checks++
    $gwOk = Test-Port 18789
    $ovOk = Test-Port 1933

    if ($gwOk) { $gwDownCount = 0 } else { $gwDownCount++ }
    if ($ovOk) { $ovDownCount = 0 } else { $ovDownCount++ }

    if ($checks % 10 -eq 0) {
        Write-Log "Heartbeat: GW=$(if($gwOk){'OK'}else{'DOWN'}) OV=$(if($ovOk){'OK'}else{'DOWN'}) checks=$checks"
    }

    if (-not $bootNotifyChecked -and $gwOk -and (Test-Path $StartupNotifyScript)) {
        try {
            $notify = & node "$StartupNotifyScript" --boot-id "$BootId" --source "watchdog" --gateway-port 18789 2>&1
            foreach ($line in $notify) { Write-Log "startup-notify: $line" }
            $bootNotifyChecked = $true
        } catch {
            Write-Log "startup-notify failed: $_" "WARN"
            $bootNotifyChecked = $true
        }
    }

    if ($ovDownCount -eq 3) {
        Write-Log "OpenViking down 3x, starting..." "WARN"
        Start-OpenViking
    }

    if ($gwDownCount -eq 3) {
        if (Test-Port 1933) {
            Write-Log "Gateway down 3x (OV ready), starting..." "WARN"
            Start-Gateway
        } else {
            Write-Log "Gateway down 3x but OV also down, waiting for OV first" "WARN"
        }
    }

    if ($gwDownCount -eq 5 -and $ovDownCount -eq 5) {
        Write-Log "Both down 5x, running startup-all..." "ERROR"
        & powershell -ExecutionPolicy Bypass -NoProfile -File "$env:USERPROFILE\.openclaw\scripts\startup-all.ps1" 2>&1 | ForEach-Object { Write-Log "  $_" }
        $gwDownCount = 0
        $ovDownCount = 0
        Start-Sleep -Seconds 60
    }

    if ($gwDownCount -gt 10 -or $ovDownCount -gt 10) {
        Write-Log "Persistent failure (gw=$gwDownCount ov=$ovDownCount). Backing off 5 min." "ERROR"
        Start-Sleep -Seconds 300
        $gwDownCount = 0
        $ovDownCount = 0
    }

    Start-Sleep -Seconds $IntervalSeconds
}

