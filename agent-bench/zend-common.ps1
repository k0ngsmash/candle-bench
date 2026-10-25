# Shared by the zend scripts: toolchain environment, paths, and a status probe.
$Work = 'D:\candle-work'; $Repo = "$Work\candle"; $Logs = "$Work\logs"
$Ws = "$Work\zend-ws"; $ZendPort = 8090; $ZendBase = "http://127.0.0.1:$ZendPort"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null
$vs = & "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -latest -property installationPath
cmd /c "`"$vs\VC\Auxiliary\Build\vcvars64.bat`" >nul && set" | ForEach-Object {
  $k = $_.IndexOf('='); if ($k -gt 0) { Set-Item -Path "env:$($_.Substring(0,$k))" -Value $_.Substring($k+1) } }
$env:CUDA_PATH = 'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9'
$env:CUDARC_CUDA_VERSION = '12090'; $env:HF_HOME = "$Work\hf-cache"
$env:RUSTUP_HOME = 'D:\rust\rustup'; $env:CARGO_HOME = 'D:\rust\cargo'
$env:Path = "$env:CUDA_PATH\bin;D:\rust\cargo\bin;C:\Program Files\Git\cmd;$env:Path"
function Get-ZendStatus { try { Invoke-RestMethod "$ZendBase/v1/status" -TimeoutSec 5 } catch { $null } }
