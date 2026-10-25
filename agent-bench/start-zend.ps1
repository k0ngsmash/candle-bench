# Starts zend standalone on 127.0.0.1:8090 (no cluster, no gateway), waits until it is ready, and
# runs a passthrough smoke test: one plain turn and one turn offering a client tool.
# Leaves zend running unless -StopAfter. Logs to D:\candle-work\logs\zend-*.log.
param([switch]$StopAfter)
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'zend-common.ps1')
$exe = "$Repo\target\release\zend.exe"
if (Get-ZendStatus) { Write-Host 'zend already answering on 8090' } else {
  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  $zargs = @('--host','127.0.0.1','--port',"$ZendPort",'--agent',"$Ws\agent.yaml",
            '--working-dir',$Ws,'--disable-layer','repo_map','--disable-layer','code_reading')
  Write-Host "Starting: zend.exe $($zargs -join ' ')"
  $p = Start-Process -FilePath $exe -ArgumentList $zargs -WorkingDirectory $Repo -PassThru -WindowStyle Minimized `
        -RedirectStandardOutput "$Logs\zend-$stamp.out.log" -RedirectStandardError "$Logs\zend-$stamp.err.log"
  $p.Id | Set-Content "$Logs\zend.pid"
  $t0 = Get-Date
  while ($true) {
    Start-Sleep 10
    if ($p.HasExited) { Write-Host "zend exited with $($p.ExitCode) - see $Logs\zend-$stamp.*.log" -ForegroundColor Red; Get-Content "$Logs\zend-$stamp.err.log" -Tail 40; exit 1 }
    $s = Get-ZendStatus
    $el = [math]::Round(((Get-Date) - $t0).TotalSeconds)
    if ($s) { Write-Host ("[{0,4}s] state: {1}" -f $el, ($s | ConvertTo-Json -Compress -Depth 3).Substring(0, [math]::Min(160, ($s | ConvertTo-Json -Compress -Depth 3).Length))) }
    else { Write-Host ("[{0,4}s] not answering yet" -f $el) }
    if ($s -and ($s | ConvertTo-Json -Depth 5) -match '"state":\s*"ready"') { break }
    if ($el -gt 2400) { Write-Host 'Not ready after 40 minutes' -ForegroundColor Red; exit 1 }
  }
}
Write-Host '== Smoke: plain passthrough turn' -ForegroundColor Cyan
$body1 = @{ model = 'passthrough'; stream = $false; max_tokens = 64
  messages = @(@{ role = 'system'; content = 'You are a terse assistant.' }, @{ role = 'user'; content = 'Reply with exactly: ready' }) } | ConvertTo-Json -Depth 6
$t = Measure-Command { $r1 = Invoke-RestMethod "$ZendBase/v1/chat/completions" -Method Post -ContentType 'application/json' -Body $body1 -TimeoutSec 600 }
Write-Host ("{0:N1}s  {1}" -f $t.TotalSeconds, ($r1 | ConvertTo-Json -Depth 8 -Compress))
Write-Host '== Smoke: passthrough turn offering a client tool' -ForegroundColor Cyan
$tool = @{ type = 'function'; function = @{ name = 'bash'; description = 'Run a bash command and return its output.'
  parameters = @{ type = 'object'; properties = @{ command = @{ type = 'string' } }; required = @('command') } } }
$body2 = @{ model = 'passthrough'; stream = $false; max_tokens = 256; tools = @($tool)
  messages = @(@{ role = 'system'; content = 'You are a software engineer working in a Linux shell. Use the bash tool.' },
               @{ role = 'user'; content = 'List the files in the current directory.' }) } | ConvertTo-Json -Depth 10
$t = Measure-Command { $r2 = Invoke-RestMethod "$ZendBase/v1/chat/completions" -Method Post -ContentType 'application/json' -Body $body2 -TimeoutSec 600 }
Write-Host ("{0:N1}s  {1}" -f $t.TotalSeconds, ($r2 | ConvertTo-Json -Depth 10 -Compress))
nvidia-smi --query-gpu=memory.used,memory.total --format=csv
if ($StopAfter) { Stop-Process -Id (Get-Content "$Logs\zend.pid") -Force; Write-Host 'zend stopped' }
