# AIVOA RCA backend supervisor — keeps uvicorn serving 127.0.0.1:8000.
# Launched hidden by Task Scheduler (task "AIVOA-RCA-Backend") so it survives
# editor/terminal sessions and OpenCode restarts. Three resilience layers:
#   1) inner loop:   uvicorn exits  -> respawn after 5 s
#   2) health probe: uvicorn alive but not answering (zombie) -> kill + respawn
#      (catches any failure mode, e.g. a dead event-loop accept task)
#   3) outer heartbeat (the task itself): respawns THIS script within 60 s
#      if it is ever killed (MultipleInstancesPolicy=IgnoreNew).
# Resolve every path from this script's own folder so a fresh clone works
# unchanged, wherever it is checked out and under whichever Windows user.
$backendDir = $PSScriptRoot
Set-Location $backendDir
$logDir = Join-Path $env:TEMP 'aivoa-rca'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'aivoa_uvicorn.log'
$launcher = Join-Path $backendDir 'start_uvicorn_once.cmd'

function Kill-UvicornTree {
    Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match 'python' -and $_.CommandLine -match 'uvicorn app\.main'
    } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

while ($true) {
    Add-Content -Path $log -Value ("=== supervisor start " + (Get-Date -Format s) + " ===")
    $proc = Start-Process -FilePath $launcher -WindowStyle Hidden -PassThru
    $fails = 0
    while ($true) {
        Start-Sleep -Seconds 10
        if ($proc.HasExited) {
            Add-Content -Path $log -Value ("=== launcher exited with code " + $proc.ExitCode + " while supervisor was probing ===")
            break
        }
        $ok = $false
        try {
            $r = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 5
            $ok = ($r.status -eq 'ok' -or $r.status -eq 'degraded')
        } catch { $ok = $false }
        if ($ok) {
            $fails = 0
        } else {
            $fails++
            if ($fails -ge 3) {
                Add-Content -Path $log -Value ("=== health probe failed $fails x - killing zombie (launcher pid " + $proc.Id + ") ===")
                Kill-UvicornTree
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                break
            }
        }
    }
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Kill-UvicornTree
    Add-Content -Path $log -Value ("=== uvicorn stopped - restarting in 5s ===")
    Start-Sleep -Seconds 5
}
