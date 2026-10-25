# One double-click: build zend on the local model-switch branch, start it, smoke-test passthrough,
# then stop it. Transcript: agent-bench\logs\zend-bringup.log
Start-Transcript -Path (Join-Path $PSScriptRoot 'logs\zend-bringup.log') -Force | Out-Null
& (Join-Path $PSScriptRoot 'build-zend.ps1')
if ($?) { & (Join-Path $PSScriptRoot 'start-zend.ps1') -StopAfter }
Stop-Transcript | Out-Null
