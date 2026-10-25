# After the restart: installs Ubuntu 24.04 with its disk on D:\wsl\ubuntu (not C:), then installs
# Docker Engine, NVIDIA container support and Python tooling inside it. Logs to install-ubuntu.log.
$log = Join-Path $PSScriptRoot 'install-ubuntu.log'
Start-Transcript -Path $log -Force | Out-Null
New-Item -ItemType Directory -Force -Path 'D:\wsl\ubuntu' | Out-Null
Write-Host '== WSL version' -ForegroundColor Cyan
wsl.exe --update
wsl.exe --version
Write-Host '== Installing Ubuntu-24.04 to D:\wsl\ubuntu' -ForegroundColor Cyan
wsl.exe --install Ubuntu-24.04 --location D:\wsl\ubuntu --no-launch
Write-Host "install exit $LASTEXITCODE"
wsl.exe -l -v
Write-Host '== Provisioning inside Ubuntu (as root)' -ForegroundColor Cyan
$sh = Join-Path $PSScriptRoot 'provision-ubuntu.sh'
$wslPath = (wsl.exe -d Ubuntu-24.04 -u root wslpath -a ($sh -replace '\\','/')).Trim()
wsl.exe -d Ubuntu-24.04 -u root bash $wslPath
Write-Host "provision exit $LASTEXITCODE"
Write-Host "`n== DONE. Tell Claude." -ForegroundColor Green
Stop-Transcript | Out-Null
