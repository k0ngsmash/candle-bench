# Builds zend on a LOCAL branch (bench/zend-qwen36, never pushed) whose only change is the served
# model: Qwen3.6-35B-A3B instead of Flash-Next, so vLLM and zend can run the same model. Also lays
# out a minimal standalone workspace. Logs to agent-bench\logs\build-zend.log.
$ErrorActionPreference = 'Continue'
Start-Transcript -Path (Join-Path $PSScriptRoot 'logs\build-zend.log') -Force | Out-Null
. (Join-Path $PSScriptRoot 'zend-common.ps1')

Write-Host '== Local branch with the one-line model switch' -ForegroundColor Cyan
git -C $Repo fetch upstream 2>&1 | Out-Null
git -C $Repo checkout -B bench/zend-qwen36 upstream/main 2>&1
git -C $Repo apply --verbose (Join-Path $PSScriptRoot 'zend-qwen36.patch') 2>&1
if ($LASTEXITCODE -ne 0) { throw 'patch did not apply' }
git -C $Repo diff --stat
$commit = (git -C $Repo rev-parse --short=8 HEAD).Trim()
Write-Host "Based on upstream $commit"

Write-Host '== cargo build --release -p zend' -ForegroundColor Cyan
Push-Location $Repo
cmd /c "cargo build --release -p zend > `"$Logs\cargo-zend.log`" 2>&1"
$exit = $LASTEXITCODE
Pop-Location
Write-Host "build exit $exit (full output: $Logs\cargo-zend.log)"
if ($exit -ne 0) { Get-Content "$Logs\cargo-zend.log" -Tail 40; throw 'zend build failed' }

Write-Host '== Standalone workspace' -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path "$Ws\scratch", "$Ws\jobs-agent" | Out-Null
"repos:`n  - name: scratch`n" | Set-Content "$Ws\workspace.yaml" -Encoding ascii
if (-not (Test-Path "$Ws\scratch\.git")) {
  git -C "$Ws\scratch" init -q -b main
  'Placeholder repository: zend requires one; the benchmark uses passthrough only.' | Set-Content "$Ws\scratch\README.md"
  git -C "$Ws\scratch" add README.md
  git -C "$Ws\scratch" -c user.name=bench -c user.email=bench@localhost commit -q -m 'placeholder'
}
@"
jobs_dir: $($Ws -replace '\\','/')/jobs-agent
slots: 1
checkouts:
  - name: scratch
    dir: $($Ws -replace '\\','/')/scratch
    push: false
"@ | Set-Content "$Ws\agent.yaml" -Encoding ascii
Get-Content "$Ws\workspace.yaml", "$Ws\agent.yaml"
Write-Host "`n== DONE (zend.exe at $Repo\target\release\zend.exe)" -ForegroundColor Green
Stop-Transcript | Out-Null
