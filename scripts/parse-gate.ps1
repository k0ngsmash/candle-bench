# Turns a gate log's last "Performance Comparison" table into rows in the same TSV columns as
# john-sharratt/candle docs/results/*.tsv. Usage: parse-gate.ps1 -Log <gate.log> -Test <test path> -Label <label> -Out <file.tsv>
param([Parameter(Mandatory)][string]$Log, [Parameter(Mandatory)][string]$Test,
      [Parameter(Mandatory)][string]$Label, [Parameter(Mandatory)][string]$Out)
$lines = [IO.File]::ReadAllLines($Log, [Text.Encoding]::UTF8)
$start = -1
for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -match '=== Performance Comparison ===') { $start = $i } }
if ($start -lt 0) { Write-Error "No Performance Comparison table in $Log"; exit 2 }
$bar = [char]0x2502   # box-drawing vertical bar
$header = $null; $rows = @()
for ($i = $start + 1; $i -lt $lines.Count; $i++) {
  $l = $lines[$i]
  if ($l.Length -eq 0) { if ($header) { break } else { continue } }
  if ($l[0] -ne $bar) { continue }
  $cells = $l.Trim($bar).Split($bar) | ForEach-Object { $_.Trim() }
  if (-not $header) { $header = $cells; continue }
  $rows += ,$cells
}
if (-not $header) { Write-Error 'Table header not found'; exit 2 }
function Col($cells, $name) { $j = [array]::IndexOf($header, $name); if ($j -ge 0) { $cells[$j] } else { '-' } }
$tsv = @("test`tlabel`tdepth`tprompt_tokens`tmode`tint8`tcontexts`tvalid`tprefill_tps`tdecode_tps`tquantized_pct`tcompress`tpeak_tokens")
foreach ($c in $rows) {
  $tsv += (@($Test, $Label, '', '-', (Col $c 'KvMode'), (Col $c 'int8'), (Col $c 'Contexts'), (Col $c 'Valid'),
             (Col $c 't/s (bulk)'), (Col $c 't/s (single)'), (Col $c '%Quantized'), (Col $c 'Compress'), (Col $c 'Peak Tokens')) -join "`t")
}
[IO.File]::WriteAllLines($Out, $tsv, (New-Object Text.UTF8Encoding $false))
Write-Host "$($rows.Count) rows -> $Out"
