# Installs the toolchain john-sharratt/candle's INSTALL.md requires, adapted for THOR:
#   Git + GitHub CLI, VS 2022 Build Tools (C++ workload, installed to D:), Rust (on D:),
#   CUDA Toolkit 12.9.1 TOOLKIT ONLY (never the bundled driver), and env vars.
# Must run elevated (install-toolchain.cmd elevates). Logs to install.log beside this script.
$ErrorActionPreference = 'Stop'
$log = Join-Path $PSScriptRoot 'install.log'
Start-Transcript -Path $log -Force | Out-Null
function Step($n) { Write-Host "`n===== $n =====" -ForegroundColor Cyan }
$work = 'D:\candle-work'; $dl = "$work\installers"
New-Item -ItemType Directory -Force -Path $dl | Out-Null
$driverBefore = (nvidia-smi --query-gpu=driver_version --format=csv,noheader).Trim()
Write-Host "Driver before: $driverBefore"

Step 'Git + GitHub CLI'
foreach ($id in 'Git.Git','GitHub.cli') {
  winget install --id $id -e --source winget --accept-package-agreements --accept-source-agreements --silent
  Write-Host "$id exit $LASTEXITCODE"
}

Step 'Visual Studio 2022 Build Tools (C++ workload) -> D:\VS\BuildTools'
winget install --id Microsoft.VisualStudio.2022.BuildTools -e --source winget --accept-package-agreements --accept-source-agreements --override "--quiet --wait --norestart --installPath D:\VS\BuildTools --add Microsoft.VisualStudio.Workload.VCTools --add Microsoft.VisualStudio.Component.VC.Tools.x86.x64 --add Microsoft.VisualStudio.Component.Windows11SDK.26100"
Write-Host "BuildTools exit $LASTEXITCODE (0 or 3010 = ok)"

Step 'Rust (rustup, MSVC host) with RUSTUP_HOME/CARGO_HOME on D:'
[Environment]::SetEnvironmentVariable('RUSTUP_HOME', 'D:\rust\rustup', 'User')
[Environment]::SetEnvironmentVariable('CARGO_HOME',  'D:\rust\cargo',  'User')
$env:RUSTUP_HOME = 'D:\rust\rustup'; $env:CARGO_HOME = 'D:\rust\cargo'
Invoke-WebRequest 'https://win.rustup.rs/x86_64' -OutFile "$dl\rustup-init.exe"
& "$dl\rustup-init.exe" -y --default-host x86_64-pc-windows-msvc --default-toolchain stable --profile default
Write-Host "rustup exit $LASTEXITCODE"

Step 'CUDA Toolkit 12.9.1 (toolkit components only, NO Display.Driver)'
$cuda = "$dl\cuda_12.9.1_576.57_windows.exe"
if (-not (Test-Path $cuda)) {
  Invoke-WebRequest 'https://developer.download.nvidia.com/compute/cuda/12.9.1/local_installers/cuda_12.9.1_576.57_windows.exe' -OutFile $cuda
}
$pkgs = 'nvcc_12.9 cudart_12.9 cuobjdump_12.9 nvprune_12.9 cuxxfilt_12.9 nvfatbin_12.9 nvjitlink_12.9 cuda_profiler_api_12.9 nvrtc_12.9 nvrtc_dev_12.9 cublas_12.9 cublas_dev_12.9 curand_12.9 curand_dev_12.9 cusparse_12.9 cusparse_dev_12.9 cusolver_12.9 cusolver_dev_12.9 cufft_12.9 cufft_dev_12.9 thrust_12.9 nvtx_12.9'
$p = Start-Process -FilePath $cuda -ArgumentList "-s $pkgs" -Wait -PassThru
Write-Host "CUDA installer exit $($p.ExitCode)"

Step 'Environment variables'
$v129 = 'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9'
$parts = ([Environment]::GetEnvironmentVariable('Path','Machine')).Split(';') |
  Where-Object { $_ -ne '' -and $_ -notmatch 'CUDA\\v13' -and $_ -notmatch 'CUDA\\v12\.4' -and $_ -ne "$v129\bin" -and $_ -ne "$v129\libnvvp" }
[Environment]::SetEnvironmentVariable('Path', ((@("$v129\bin","$v129\libnvvp") + $parts) -join ';'), 'Machine')
[Environment]::SetEnvironmentVariable('CUDA_PATH', $v129, 'Machine')
[Environment]::SetEnvironmentVariable('CUDARC_CUDA_VERSION', '12090', 'User')
[Environment]::SetEnvironmentVariable('HF_HOME', "$work\hf-cache", 'User')

Step 'Verify'
& "$v129\bin\nvcc.exe" --version
& "D:\rust\cargo\bin\rustc.exe" --version
& "D:\rust\cargo\bin\cargo.exe" --version
Test-Path 'D:\VS\BuildTools\VC\Auxiliary\Build\vcvars64.bat' | ForEach-Object { "vcvars64.bat present: $_" }
& 'C:\Program Files\Git\cmd\git.exe' --version
& 'C:\Program Files\GitHub CLI\gh.exe' --version
$driverAfter = (nvidia-smi --query-gpu=driver_version --format=csv,noheader).Trim()
Write-Host "Driver after: $driverAfter (before: $driverBefore) -> $(if ($driverAfter -eq $driverBefore) {'UNCHANGED, good'} else {'CHANGED - tell Claude'})"
Get-PSDrive C,D | Select Name,@{n='FreeGB';e={[math]::Round($_.Free/1GB)}} | Format-Table
Write-Host "`n===== DONE ====="
Stop-Transcript | Out-Null
