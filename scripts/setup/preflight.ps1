# Read-only environment check for building john-sharratt/candle on this PC.
# Writes preflight.log next to this script. Changes nothing except creating D:\candle-work.
$ErrorActionPreference = 'Continue'
$log = Join-Path $PSScriptRoot 'preflight.log'
function Section($name, [scriptblock]$body) {
  "`n===== $name =====" | Out-File $log -Append -Encoding utf8
  try { & $body 2>&1 | Out-String -Width 250 | Out-File $log -Append -Encoding utf8 }
  catch { "ERROR: $_" | Out-File $log -Append -Encoding utf8 }
}
"preflight $(Get-Date -Format o) on $env:COMPUTERNAME" | Out-File $log -Encoding utf8
Section 'GPU' { nvidia-smi --query-gpu=name,driver_version,memory.total,pcie.link.gen.max,pcie.link.gen.current,pcie.link.width.max,pcie.link.width.current,compute_cap --format=csv }
Section 'nvidia-smi' { nvidia-smi }
Section 'CPU/RAM' { Get-CimInstance Win32_Processor | Select Name,NumberOfCores,NumberOfLogicalProcessors | Format-List; Get-CimInstance Win32_PhysicalMemory | Select Capacity,Speed,ConfiguredClockSpeed,PartNumber | Format-Table }
Section 'Disks' { Get-PSDrive -PSProvider FileSystem | Select Name,@{n='FreeGB';e={[math]::Round($_.Free/1GB)}},@{n='UsedGB';e={[math]::Round($_.Used/1GB)}} | Format-Table; Get-PhysicalDisk | Select FriendlyName,MediaType,BusType,@{n='SizeGB';e={[math]::Round($_.Size/1GB)}} | Format-Table }
Section 'nvcc' { nvcc --version }
Section 'CUDA_PATH' { Get-ChildItem env: | Where-Object Name -like 'CUDA_PATH*' | Format-Table -AutoSize; Get-ChildItem 'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA' -ErrorAction SilentlyContinue | Select Name }
Section 'Rust' { rustc --version; cargo --version; rustup show }
Section 'MSVC (vswhere)' { & "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" -products * -format text -property displayName,installationVersion,installationPath }
Section 'cl.exe on PATH' { where.exe cl }
Section 'Windows SDK' { Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\Include' -ErrorAction SilentlyContinue | Select Name }
Section 'git / gh' { git --version; git config --global user.name; git config --global user.email; gh --version; gh auth status }
Section 'HF cache env' { Get-ChildItem env: | Where-Object Name -like 'HF_*' | Format-Table -AutoSize }
Section 'Create D:\candle-work' { New-Item -ItemType Directory -Force -Path 'D:\candle-work' | Select FullName }
"`n===== DONE =====" | Out-File $log -Append -Encoding utf8
