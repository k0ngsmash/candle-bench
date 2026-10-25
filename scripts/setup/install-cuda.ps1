# Finishes install-toolchain.ps1 from the CUDA step: resumes the CUDA 12.9.1 download with curl.exe
# (PowerShell 5.1's Invoke-WebRequest is far too slow for 3 GB), installs TOOLKIT ONLY (no driver),
# sets env vars, verifies. Must run elevated (install-cuda.cmd elevates). Logs to install-cuda.log.
$ErrorActionPreference = 'Stop'
$log = Join-Path $PSScriptRoot 'install-cuda.log'
Start-Transcript -Path $log -Force | Out-Null
function Step($n) { Write-Host "`n===== $n =====" -ForegroundColor Cyan }
$work = 'D:\candle-work'; $dl = "$work\installers"
$url  = 'https://developer.download.nvidia.com/compute/cuda/12.9.1/local_installers/cuda_12.9.1_576.57_windows.exe'
$cuda = "$dl\cuda_12.9.1_576.57_windows.exe"
$driverBefore = (nvidia-smi --query-gpu=driver_version --format=csv,noheader).Trim()
Write-Host "Driver before: $driverBefore"

Step 'Download CUDA 12.9.1 (resuming)'
$head = & curl.exe -sIL $url
$expected = [int64](($head | Select-String -Pattern '^content-length:\s*(\d+)' -AllMatches | Select-Object -Last 1).Matches[0].Groups[1].Value)
Write-Host "Expected size: $expected bytes"
& curl.exe -L --fail --retry 5 -C - -o $cuda $url
$have = (Get-Item $cuda).Length
Write-Host "Downloaded: $have bytes"
if ($have -ne $expected) {
  Write-Host 'Size mismatch - deleting partial file and downloading fresh' -ForegroundColor Yellow
  Remove-Item $cuda -Force
  & curl.exe -L --fail --retry 5 -o $cuda $url
  $have = (Get-Item $cuda).Length
  if ($have -ne $expected) { throw "CUDA download still wrong size ($have vs $expected)" }
}
$sig = Get-AuthenticodeSignature $cuda
Write-Host "Signature: $($sig.Status) by $($sig.SignerCertificate.Subject)"
if ($sig.Status -ne 'Valid') { throw 'CUDA installer signature is not valid - stopping' }

Step 'Install CUDA toolkit components only (NO Display.Driver)'
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
& 'D:\rust\cargo\bin\rustc.exe' --version
$vsw = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
& $vsw -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
& 'C:\Program Files\Git\cmd\git.exe' --version
& 'C:\Program Files\GitHub CLI\gh.exe' --version
$driverAfter = (nvidia-smi --query-gpu=driver_version --format=csv,noheader).Trim()
Write-Host "Driver after: $driverAfter (before: $driverBefore) -> $(if ($driverAfter -eq $driverBefore) {'UNCHANGED, good'} else {'CHANGED - tell Claude'})"
Get-PSDrive C,D | Select Name,@{n='FreeGB';e={[math]::Round($_.Free/1GB)}} | Format-Table
Write-Host "`n===== DONE ====="
Stop-Transcript | Out-Null
