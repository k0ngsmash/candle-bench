# Final step: env vars + verification (the CUDA installer finished, but install-cuda.ps1 hung on
# PowerShell 5.1's Start-Process -Wait). Must run elevated (install-finish.cmd elevates). Logs to install-finish.log.
$ErrorActionPreference = 'Continue'
$log = Join-Path $PSScriptRoot 'install-finish.log'
Start-Transcript -Path $log -Force | Out-Null
function Step($n) { Write-Host "`n===== $n =====" -ForegroundColor Cyan }
$work = 'D:\candle-work'
$v129 = 'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9'

Step 'Check the toolkit pieces the build needs are present'
foreach ($f in 'bin\nvcc.exe','bin\cudart64_12.dll','bin\cublas64_12.dll','bin\cublasLt64_12.dll','bin\curand64_10.dll','bin\nvrtc64_120_0.dll','lib\x64\cuda.lib','lib\x64\cublas.lib','include\cuda_runtime.h','include\cub\cub.cuh','include\thrust\version.h') {
  "{0,-30} {1}" -f $f, (Test-Path (Join-Path $v129 $f))
}

Step 'Environment variables'
$parts = ([Environment]::GetEnvironmentVariable('Path','Machine')).Split(';') |
  Where-Object { $_ -ne '' -and $_ -notmatch 'CUDA\\v13' -and $_ -notmatch 'CUDA\\v12\.4' -and $_ -ne "$v129\bin" -and $_ -ne "$v129\libnvvp" }
[Environment]::SetEnvironmentVariable('Path', ((@("$v129\bin","$v129\libnvvp") + $parts) -join ';'), 'Machine')
[Environment]::SetEnvironmentVariable('CUDA_PATH', $v129, 'Machine')
[Environment]::SetEnvironmentVariable('CUDARC_CUDA_VERSION', '12090', 'User')
[Environment]::SetEnvironmentVariable('HF_HOME', "$work\hf-cache", 'User')
'CUDA_PATH (Machine)      = ' + [Environment]::GetEnvironmentVariable('CUDA_PATH','Machine')
'CUDARC_CUDA_VERSION (User) = ' + [Environment]::GetEnvironmentVariable('CUDARC_CUDA_VERSION','User')
'HF_HOME (User)           = ' + [Environment]::GetEnvironmentVariable('HF_HOME','User')
'RUSTUP_HOME / CARGO_HOME = ' + [Environment]::GetEnvironmentVariable('RUSTUP_HOME','User') + ' / ' + [Environment]::GetEnvironmentVariable('CARGO_HOME','User')

Step 'Verify tools'
& "$v129\bin\nvcc.exe" --version
& 'D:\rust\cargo\bin\rustc.exe' --version
& 'D:\rust\cargo\bin\cargo.exe' --version
$vsw = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs = & $vsw -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -latest -property installationPath
"VS C++ tools at: $vs"
"vcvars64.bat present: " + (Test-Path "$vs\VC\Auxiliary\Build\vcvars64.bat")
& 'C:\Program Files\Git\cmd\git.exe' --version
& 'C:\Program Files\GitHub CLI\gh.exe' --version
"Driver now: " + (nvidia-smi --query-gpu=driver_version --format=csv,noheader).Trim() + "  (was 616.56)"
Get-PSDrive C,D | Select Name,@{n='FreeGB';e={[math]::Round($_.Free/1GB,1)}} | Format-Table
Write-Host "`n===== DONE =====" -ForegroundColor Green
Stop-Transcript | Out-Null
