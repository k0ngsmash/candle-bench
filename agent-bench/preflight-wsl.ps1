# Read-only check of what the agent benchmark needs on Windows: WSL2, virtualisation, Docker,
# and where things would be stored. Writes preflight-wsl.log beside this script.
$log = Join-Path $PSScriptRoot 'preflight-wsl.log'
function Section($name, [scriptblock]$body) {
  "`n===== $name =====" | Out-File $log -Append -Encoding utf8
  try { & $body 2>&1 | Out-String -Width 250 | Out-File $log -Append -Encoding utf8 } catch { "ERROR: $_" | Out-File $log -Append -Encoding utf8 }
}
"preflight-wsl $(Get-Date -Format o)" | Out-File $log -Encoding utf8
Section 'Windows build' { [Environment]::OSVersion.Version; (Get-CimInstance Win32_OperatingSystem).Caption }
Section 'Virtualisation' { Get-CimInstance Win32_ComputerSystem | Select HypervisorPresent; Get-CimInstance Win32_Processor | Select VirtualizationFirmwareEnabled }
Section 'wsl --version' { wsl.exe --version }
Section 'wsl --status' { wsl.exe --status }
Section 'wsl -l -v' { wsl.exe -l -v }
Section '.wslconfig' { $p = Join-Path $env:USERPROFILE '.wslconfig'; if (Test-Path $p) { Get-Content $p } else { 'none' } }
Section 'Optional features' { Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux,VirtualMachinePlatform -ErrorAction SilentlyContinue | Select FeatureName,State }
Section 'Docker' { Get-Command docker -ErrorAction SilentlyContinue | Select Source; docker --version; Get-Service *docker* -ErrorAction SilentlyContinue | Select Name,Status }
Section 'WSL disk images' { Get-ChildItem "$env:LOCALAPPDATA\Packages" -Recurse -Filter ext4.vhdx -ErrorAction SilentlyContinue | Select FullName,@{n='GB';e={[math]::Round($_.Length/1GB,1)}} }
Section 'Free space' { Get-PSDrive C,D | Select Name,@{n='FreeGB';e={[math]::Round($_.Free/1GB)}} }
Section 'RAM in use' { $os = Get-CimInstance Win32_OperatingSystem; "free {0:N1} GB of {1:N1} GB" -f ($os.FreePhysicalMemory/1MB), ($os.TotalVisibleMemorySize/1MB) }
"`n===== DONE =====" | Out-File $log -Append -Encoding utf8
