# Installs WSL2 (no distribution yet) and writes %USERPROFILE%\.wslconfig. Needs admin and a restart.
# After the restart, run install-ubuntu.cmd to put Ubuntu on D:.
$log = Join-Path $PSScriptRoot 'install-wsl.log'
Start-Transcript -Path $log -Force | Out-Null
Write-Host '== Installing WSL2 (no Linux distribution yet)' -ForegroundColor Cyan
wsl.exe --install --no-distribution
Write-Host "wsl --install exit $LASTEXITCODE"
Write-Host '== Writing .wslconfig' -ForegroundColor Cyan
$cfg = @'
[wsl2]
# Leave headroom for Windows and for zend's ~23 GB warm tier when it runs.
memory=24GB
processors=12
swap=8GB
# Windows and Linux share localhost, so the agent in Linux reaches zend on Windows at 127.0.0.1.
networkingMode=mirrored
[experimental]
# Give freed disk space back to D:.
sparseVhd=true
autoMemoryReclaim=gradual
'@
$p = Join-Path $env:USERPROFILE '.wslconfig'
if (Test-Path $p) { Copy-Item $p "$p.bak" -Force; Write-Host "Existing .wslconfig saved as .wslconfig.bak" }
[IO.File]::WriteAllText($p, $cfg)
Get-Content $p
Write-Host "`n== DONE. Restart Windows, then run install-ubuntu.cmd." -ForegroundColor Green
Stop-Transcript | Out-Null
