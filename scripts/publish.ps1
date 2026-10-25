# Commits everything new (results, notes, ladder/hosts/scripts edits) and pushes.
# Usage: publish.ps1 "one-line message"   or   publish.ps1 -MessageFile <file>
param([string]$Message = "Add results from $(Get-Date -Format 'yyyy-MM-dd')", [string]$MessageFile)
$ErrorActionPreference = 'Continue'
$Bench = Split-Path $PSScriptRoot -Parent
Set-Location $Bench
$env:Path = "C:\Program Files\Git\cmd;C:\Program Files\GitHub CLI;$env:Path"
if ($MessageFile) { $MessageFile = (Resolve-Path $MessageFile).Path }
git add -A
git diff --cached --stat
if ($MessageFile) { git commit -q -F $MessageFile } else { git commit -q -m $Message }
if ($LASTEXITCODE -ne 0) { Write-Host 'Nothing to commit.'; exit 0 }
git push
if ($LASTEXITCODE -ne 0) { throw 'push failed' }
git log --oneline -1
