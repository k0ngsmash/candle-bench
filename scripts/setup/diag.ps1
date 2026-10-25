# Read-only snapshot: free space, running CUDA installer processes, temp usage. Writes diag.log.
$log = Join-Path $PSScriptRoot 'diag.log'
& {
  "diag $(Get-Date -Format o)"
  Get-PSDrive C,D | Select Name,@{n='FreeGB';e={[math]::Round($_.Free/1GB,1)}} | Format-Table | Out-String
  'Installer-related processes:'
  Get-Process | Where-Object { $_.Name -match 'cuda|setup|nvi|msiexec|7z|nvidia' } |
    Select Name,Id,@{n='CPUsec';e={[math]::Round($_.CPU)}},@{n='WSMB';e={[math]::Round($_.WorkingSet64/1MB)}},StartTime | Format-Table | Out-String
  'Temp folders (GB):'
  foreach ($t in $env:TEMP, 'C:\Windows\Temp') {
    $s = (Get-ChildItem $t -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    "{0}  {1:N1}" -f $t, ($s/1GB)
  }
  'CUDA dir:'
  $c = 'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9'
  if (Test-Path $c) { "{0:N1} GB in $c" -f (((Get-ChildItem $c -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum)/1GB) } else { 'not present yet' }
  'Largest items in C:\ root user folders (GB):'
  foreach ($d in "$env:USERPROFILE\Downloads","$env:LOCALAPPDATA\Temp","$env:USERPROFILE\.ollama","$env:USERPROFILE\.cache","C:\ProgramData\Package Cache") {
    if (Test-Path $d) { "{0,-55} {1:N1}" -f $d, (((Get-ChildItem $d -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum)/1GB) }
  }
} *>&1 | Out-File $log -Encoding utf8
