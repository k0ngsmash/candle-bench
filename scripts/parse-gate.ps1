# Turns every "Performance Comparison" table in a gate log into rows in the same TSV columns as
# john-sharratt/candle docs/results/*.tsv. Depth gates print one table per depth rung; the rung's
# depth is read from the "--- <label> | depth N (M prompt tokens) | ..." line before its table.
# Usage: parse-gate.ps1 -Log <gate.log> -Test <test path> -Label <label> -Out <file.tsv>
param([Parameter(Mandatory)][string]$Log, [Parameter(Mandatory)][string]$Test,
      [Parameter(Mandatory)][string]$Label, [Parameter(Mandatory)][string]$Out)
$lines = [IO.File]::ReadAllLines($Log, [Text.Encoding]::UTF8)
$bar = [char]0x2502   # box-drawing vertical bar
$tsv = @("test`tlabel`tdepth`tprompt_tokens`tmode`tint8`tcontexts`tvalid`tprefill_tps`tdecode_tps`tquantized_pct`tcompress`tpeak_tokens")
$depth = ''; $prompt = '-'; $tables = 0
for ($i = 0; $i -lt $lines.Count; $i++) {
  if ($lines[$i] -match '\| depth (\d+) \((\d+) prompt tokens\)') { $depth = $Matches[1]; $prompt = $Matches[2]; continue }
  if ($lines[$i] -notmatch '=== Performance Comparison ===') { continue }
  $tables++; $header = $null
  for ($j = $i + 1; $j -lt $lines.Count; $j++) {
    $l = $lines[$j]
    if ($l.Length -eq 0) { if ($header) { break } else { continue } }
    if ($l[0] -ne $bar) { continue }
    $cells = $l.Trim($bar).Split($bar) | ForEach-Object { $_.Trim() }
    if (-not $header) { $header = $cells; continue }
    $col = { param($n) $k = [array]::IndexOf($header, $n); if ($k -ge 0) { $cells[$k] } else { '-' } }
    $tsv += (@($Test, $Label, $depth, $prompt, (& $col 'KvMode'), (& $col 'int8'), (& $col 'Contexts'), (& $col 'Valid'),
               (& $col 't/s (bulk)'), (& $col 't/s (single)'), (& $col '%Quantized'), (& $col 'Compress'), (& $col 'Peak Tokens')) -join "`t")
  }
  $i = $j
}
if ($tables -eq 0) { Write-Error "No Performance Comparison table in $Log"; exit 2 }
[IO.File]::WriteAllLines($Out, $tsv, (New-Object Text.UTF8Encoding $false))
Write-Host "$($tsv.Count - 1) rows from $tables table(s) -> $Out"
