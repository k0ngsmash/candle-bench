# One-off: tidy the folder into the repo layout, sign gh in, file the smoke-test result, and push
# the first commit to github.com/k0ngsmash/candle-bench. Logs to scripts\setup\logs\setup-repo.log.
$ErrorActionPreference = 'Continue'   # native tools write progress to stderr; exit codes are checked explicitly
$Bench = Split-Path $PSScriptRoot -Parent
Set-Location $Bench
$setup = Join-Path $PSScriptRoot 'setup'; $slogs = Join-Path $setup 'logs'
New-Item -ItemType Directory -Force -Path $slogs | Out-Null
Start-Transcript -Path (Join-Path $slogs 'setup-repo.log') -Force | Out-Null
$env:Path = "C:\Program Files\Git\cmd;C:\Program Files\GitHub CLI;$env:Path"

Write-Host '== Tidy: one-off setup scripts -> scripts\setup, their logs -> scripts\setup\logs' -ForegroundColor Cyan
foreach ($f in 'preflight','install-toolchain','install-cuda','install-finish','diag','build-and-smoke') {
  foreach ($ext in 'ps1','cmd') { $p = Join-Path $Bench "$f.$ext"; if (Test-Path $p) { Move-Item $p $setup -Force } }
}
Get-ChildItem $Bench -Filter *.log -File | Move-Item -Destination $slogs -Force

Write-Host '== GitHub CLI sign-in' -ForegroundColor Cyan
gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host 'A browser window will open: copy the one-time code shown below into it and approve.' -ForegroundColor Yellow
  gh auth login --hostname github.com --git-protocol https --web
  if ($LASTEXITCODE -ne 0) { throw 'gh sign-in did not complete' }
}
gh auth setup-git
$me = gh api user | ConvertFrom-Json
Write-Host "Signed in as $($me.login)"

Write-Host '== File the smoke-test result' -ForegroundColor Cyan
$run = Join-Path $Bench 'results\2026-10-25_thor_5739c544'
New-Item -ItemType Directory -Force -Path $run | Out-Null
$src = 'D:\candle-work\logs\gate_qwen2_5739c544.log'
$test = 'models::quantized_qwen2::tests::test_parallel_batched_forwarding'
Copy-Item $src "$run\qwen2-0.5b.log" -Force
& (Join-Path $PSScriptRoot 'parse-gate.ps1') -Log $src -Test $test -Label 'Qwen2-0.5B' -Out "$run\qwen2-0.5b.tsv"
$gpu = nvidia-smi --query-gpu=name,driver_version,memory.total,pcie.link.gen.current,pcie.link.width.current,compute_cap --format=csv,noheader
$ram = Get-CimInstance Win32_PhysicalMemory | ForEach-Object { "$([math]::Round($_.Capacity/1GB))GB@$($_.ConfiguredClockSpeed)" }
@('host: thor', 'commit: 5739c544 (john-sharratt/candle main)', 'date: 2026-10-25T08:24:55+08:00', "gpu: $gpu",
  "cpu: $((Get-CimInstance Win32_Processor).Name.Trim())", "ram: $($ram -join ', ')",
  'nvcc: release 12.9, V12.9.86', 'rustc: 1.99.1') | Set-Content "$run\host.txt" -Encoding UTF8
$index = Join-Path $Bench 'results\index.tsv'
@("date`thost`tcommit`tkey`texit`trows`twall_s`tvram_used_before_mib",
  "2026-10-25`tthor`t5739c544`tqwen2-0.5b`t0`t6`t-`t1905") | Set-Content $index -Encoding UTF8

Write-Host '== First commit and push' -ForegroundColor Cyan
if (-not (Test-Path (Join-Path $Bench '.git'))) { git init -b main | Out-Null }
$name = if ($me.name) { $me.name } else { $me.login }
git config user.name $name
git config user.email "$($me.id)+$($me.login)@users.noreply.github.com"
git add -A
$msg = @'
Set up candle-bench with thor's toolchain and first smoke result

Gate ladder, run and parse scripts, Windows setup scripts, host notes,
and the Qwen2-0.5B smoke gate on thor at upstream 5739c544.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Be6vadUPc2PDKiz8gJe8NN
'@
git commit -q -m $msg
if ($LASTEXITCODE -ne 0) { throw "commit failed" }
git remote remove origin 2>$null
git remote add origin "https://github.com/$($me.login)/candle-bench.git"
git push -u origin main
if ($LASTEXITCODE -ne 0) { throw 'push failed' }
git log --oneline -1
Write-Host "`nDone: https://github.com/$($me.login)/candle-bench" -ForegroundColor Green
Stop-Transcript | Out-Null
