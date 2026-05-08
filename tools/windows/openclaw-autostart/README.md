# OpenClaw Windows headless autostart

This folder keeps the Windows headless startup chain used on the local machine.

Snapshot:

- Captured: 2026-05-08
- OpenClaw: 2026.5.7
- Root: `C:\Users\Administrator\.openclaw`
- Gateway port: `18789`
- OpenViking port: `1933`

## What is installed

Two Windows Scheduled Tasks are used instead of Startup-folder shortcuts.

| Task | Runs as | Visible window | Purpose |
| --- | --- | --- | --- |
| `OpenClaw Gateway` | `SYSTEM` | no user desktop window | Runs `gateway-watchdog.cmd`, which keeps the gateway process alive. |
| `OpenClaw Watchdog` | `SYSTEM` | hidden PowerShell window | Monitors Gateway + OpenViking, starts missing services, and sends one startup notification per boot when configured. |

The key no-frame setting is:

```powershell
powershell.exe -ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File "C:\Users\Administrator\.openclaw\scripts\watchdog.ps1"
```

## Files

- `gateway-watchdog.cmd`: tight loop that starts `openclaw gateway --port 18789` and restarts it after crashes.
- `gateway.cmd`: single gateway launch command with the local proxy and service markers.
- `watchdog.ps1`: lightweight monitor for Gateway and OpenViking.
- `startup-all.ps1`: boot helper that starts OpenViking first, then Gateway.
- `startup-notify.js` + `lib/startup_notify.js`: optional Feishu notification helper. It reads credentials from the local `openclaw.json`; no token is stored in this repo.
- `install-openclaw-autostart.ps1`: recreates the two Scheduled Tasks and can copy the bundled scripts into the active OpenClaw root.

## Restore or update this machine

Run PowerShell as Administrator:

```powershell
cd D:\codex\AI_Tools\tools\windows\openclaw-autostart
.\install-openclaw-autostart.ps1
```

Dry-run first:

```powershell
.\install-openclaw-autostart.ps1 -WhatIf
```

## Verify

```powershell
Get-ScheduledTask -TaskName "OpenClaw Gateway","OpenClaw Watchdog" |
  Select-Object TaskName,State,@{n="Execute";e={$_.Actions.Execute}},@{n="Arguments";e={$_.Actions.Arguments}}

Get-NetTCPConnection -LocalPort 18789 -ErrorAction SilentlyContinue
Get-NetTCPConnection -LocalPort 1933 -ErrorAction SilentlyContinue
```

Expected:

- `OpenClaw Gateway`: `Running`
- `OpenClaw Watchdog`: `Running`
- `127.0.0.1:18789`: listening
- no visible console window required after reboot

