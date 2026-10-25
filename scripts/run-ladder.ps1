# Runs the enabled gates in ladder.csv (or -Only <keys>) against the latest john-sharratt/candle,
# one cargo process per gate, and files results under results/<date>_<host>_<commit>/.
# Usage: run-ladder.ps1 [-Only qwen3-8b,qwen3-30b-a3b] [-NoUpdate]
param([string[]]$Only, [switch]$NoUpdate)
$ErrorActionPreference = 'Continue'   # git/cargo write progress to stderr; exit codes are checked explicitly
$Bench = Split-Path $PSScriptRoot -Parent
$Work  = 'D:\candle-work'; $Repo = "$Work\candle"; $Logs = "$Work\logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

# --- toolchain environment (imported from vcvars64, plus CUDA/Rust/HF) ---
$vs = & "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -latest -property installationPath
cmd /c "`"$vs\VC\Auxiliary\Build\vcvars64.bat`" >nul && set" | ForEach-Object {
  $k = $_.IndexOf('='); if ($k -gt 0) { Set-Item -Path "env:$($_.Substring(0,$k))" -Value $_.Substring($k+1) } }
$env:CUDA_PATH = 'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9'
$env:CUDARC_CUDA_VERSION = '12090'; $env:HF_HOME = "$Work\hf-cache"
$env:RUSTUP_HOME = 'D:\rust\rustup'; $env:CARGO_HOME = 'D:\rust\cargo'
$env:Path = "$env:CUDA_PATH\bin;D:\rust\cargo\bin;C:\Program Files\Git\cmd;$env:Path"

# --- model packs: keep ~/.cache/zend on D: (the engine hard-codes this path under USERPROFILE) ---
$zend = Join-Path $env:USERPROFILE '.cache\zend'; $zendD = "$Work\zend-cache"
$item = Get-Item $zend -Force -ErrorAction SilentlyContinue
if (-not $item -or -not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
  New-Item -ItemType Directory -Force -Path $zendD | Out-Null
  if ($item) { Get-ChildItem $zend -Force | Move-Item -Destination $zendD -Force; Remove-Item $zend -Force -Recurse }
  New-Item -ItemType Directory -Force -Path (Split-Path $zend) | Out-Null
  cmd /c "mklink /J `"$zend`" `"$zendD`"" | Out-Null
  Write-Host "Linked $zend -> $zendD"
}

# --- update to John's latest ---
if (-not $NoUpdate) {
  git -C $Repo fetch upstream 2>&1 | Out-Null
  git -C $Repo checkout main 2>&1 | Out-Null
  git -C $Repo merge --ff-only upstream/main 2>&1 | Out-Null
}
$commit = (git -C $Repo rev-parse --short=8 HEAD).Trim()
$hostName = $env:COMPUTERNAME.ToLower()
$runDir = Join-Path $Bench ("results\{0}_{1}_{2}" -f (Get-Date -Format 'yyyy-MM-dd'), $hostName, $commit)
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

# --- host facts for this run ---
$gpu = nvidia-smi --query-gpu=name,driver_version,memory.total,pcie.link.gen.current,pcie.link.width.current,compute_cap --format=csv,noheader
$ram = Get-CimInstance Win32_PhysicalMemory | ForEach-Object { "$([math]::Round($_.Capacity/1GB))GB@$($_.ConfiguredClockSpeed)" }
$cpu = (Get-CimInstance Win32_Processor).Name.Trim()
@("host: $hostName", "commit: $commit (john-sharratt/candle main)", "date: $(Get-Date -Format o)", "gpu: $gpu",
  "cpu: $cpu", "ram: $($ram -join ', ')", "nvcc: $((& nvcc --version | Select-String 'release').ToString().Trim())",
  "rustc: $((& rustc --version).Trim())") | Set-Content -Path "$runDir\host.txt" -Encoding UTF8

# --- build once ---
Write-Host "Building $commit ..." -ForegroundColor Cyan
Push-Location $Repo
cmd /c "cargo test --release --features cuda -p candle-transformers --lib --no-run > `"$Logs\build_$commit.log`" 2>&1"
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Build failed - see $Logs\build_$commit.log" }

# --- gates ---
$ladder = Import-Csv (Join-Path $Bench 'ladder.csv')
$todo = if ($Only) { $ladder | Where-Object { $Only -contains $_.key } } else { $ladder | Where-Object { $_.enabled -eq '1' } }
$index = Join-Path $Bench 'results\index.tsv'
if (-not (Test-Path $index)) { "date`thost`tcommit`tkey`texit`trows`twall_s`tvram_used_before_mib" | Set-Content $index -Encoding UTF8 }
foreach ($g in $todo) {
  $vram = (nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits).Trim()
  Write-Host "`n[$($g.key)] $($g.test)  (VRAM in use before: $vram MiB)" -ForegroundColor Cyan
  $log = "$Logs\gate_$($g.key)_$commit.log"
  $t0 = Get-Date
  cmd /c "cargo test --release --features cuda -p candle-transformers --lib $($g.test) -- --exact --ignored --nocapture --test-threads=1 > `"$log`" 2>&1"
  $exit = $LASTEXITCODE; $wall = [math]::Round(((Get-Date) - $t0).TotalSeconds)
  Copy-Item $log "$runDir\$($g.key).log" -Force
  $rows = 0
  try {
    & (Join-Path $PSScriptRoot 'parse-gate.ps1') -Log $log -Test $g.test -Label $g.label -Out "$runDir\$($g.key).tsv"
    $rows = (Get-Content "$runDir\$($g.key).tsv").Count - 1
  } catch { Write-Warning "No table parsed for $($g.key): $_" }
  "$(Get-Date -Format 'yyyy-MM-dd')`t$hostName`t$commit`t$($g.key)`t$exit`t$rows`t$wall`t$vram" | Add-Content $index -Encoding UTF8
  Write-Host "[$($g.key)] exit $exit, $rows rows, $wall s" -ForegroundColor $(if ($exit -eq 0) {'Green'} else {'Red'})
}
Pop-Location
Write-Host "`nResults in $runDir" -ForegroundColor Green
