#Requires -Version 5.1
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$OpenClawRoot = "$env:USERPROFILE\.openclaw",
    [switch]$SkipCopy
)

$ErrorActionPreference = "Stop"

function Copy-WithBackup {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    $parent = Split-Path -Path $Destination -Parent
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }

    if (Test-Path -LiteralPath $Destination) {
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $backup = "$Destination.bak.$stamp"
        if ($PSCmdlet.ShouldProcess($Destination, "backup to $backup")) {
            Copy-Item -LiteralPath $Destination -Destination $backup -Force
        }
    }

    if ($PSCmdlet.ShouldProcess($Destination, "copy from $Source")) {
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
    }
}

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptsRoot = Join-Path $OpenClawRoot "scripts"
$LibRoot = Join-Path $ScriptsRoot "lib"

if (-not $SkipCopy) {
    Copy-WithBackup -Source (Join-Path $Here "gateway-watchdog.cmd") -Destination (Join-Path $OpenClawRoot "gateway-watchdog.cmd")
    Copy-WithBackup -Source (Join-Path $Here "gateway.cmd") -Destination (Join-Path $OpenClawRoot "gateway.cmd")
    Copy-WithBackup -Source (Join-Path $Here "watchdog.ps1") -Destination (Join-Path $ScriptsRoot "watchdog.ps1")
    Copy-WithBackup -Source (Join-Path $Here "startup-all.ps1") -Destination (Join-Path $ScriptsRoot "startup-all.ps1")
    Copy-WithBackup -Source (Join-Path $Here "startup-notify.js") -Destination (Join-Path $ScriptsRoot "startup-notify.js")
    Copy-WithBackup -Source (Join-Path $Here "lib\startup_notify.js") -Destination (Join-Path $LibRoot "startup_notify.js")
}

$gatewayAction = New-ScheduledTaskAction -Execute (Join-Path $OpenClawRoot "gateway-watchdog.cmd")
$watchdogAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File `"$ScriptsRoot\watchdog.ps1`""
$startupTrigger = New-ScheduledTaskTrigger -AtStartup
$systemPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)
$settings.Hidden = $true

if ($PSCmdlet.ShouldProcess("OpenClaw Gateway", "register startup task")) {
    Register-ScheduledTask `
        -TaskName "OpenClaw Gateway" `
        -Action $gatewayAction `
        -Trigger $startupTrigger `
        -Principal $systemPrincipal `
        -Settings $settings `
        -Force | Out-Null
}

if ($PSCmdlet.ShouldProcess("OpenClaw Watchdog", "register hidden startup watchdog task")) {
    Register-ScheduledTask `
        -TaskName "OpenClaw Watchdog" `
        -Action $watchdogAction `
        -Trigger $startupTrigger `
        -Principal $systemPrincipal `
        -Settings $settings `
        -Force | Out-Null
}

Get-ScheduledTask -TaskName "OpenClaw Gateway", "OpenClaw Watchdog" |
    Select-Object TaskName, State, @{n = "Execute"; e = { $_.Actions.Execute } }, @{n = "Arguments"; e = { $_.Actions.Arguments } }

