param([switch]$Preview, [switch]$RefreshIndex)
$ErrorActionPreference = 'Stop'
$base = Split-Path -Parent $PSScriptRoot
$lock = $null
try {
 $lock = [IO.File]::Open((Join-Path $PSScriptRoot 'run.lock'),'OpenOrCreate','ReadWrite','None')
 $arguments = @((Join-Path $PSScriptRoot 'lesson.py'), '--root', $base)
 if ($Preview) { $arguments += '--preview' }
 if ($RefreshIndex) { $arguments += '--refresh-index' }
 & python @arguments
 if ($LASTEXITCODE -ne 0) { throw "Daily lesson failed (exit $LASTEXITCODE). See logs." }
} finally { if ($lock) { $lock.Dispose() } }
