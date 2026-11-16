$ErrorActionPreference='Stop'
$base=Split-Path -Parent $PSScriptRoot
$statusPath=Join-Path $base 'data/scheduler-status.json'
$started=Get-Date
$log=Join-Path $base ('logs/scheduler-'+$started.ToString('yyyyMMdd-HHmmss-fff')+'.log')
$exitCode=1
$status=[ordered]@{status='running';startedAt=$started.ToString('o');finishedAt=$null;exitCode=$null;log=$log;error=$null}
function Write-Status {
 $temp=$statusPath+'.partial'
 $status | ConvertTo-Json | Set-Content -LiteralPath $temp -Encoding UTF8
 Move-Item -LiteralPath $temp -Destination $statusPath -Force
}
try {
 New-Item -ItemType Directory -Path (Join-Path $base 'data'),(Join-Path $base 'logs') -Force | Out-Null
 Write-Status
 $config=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'scheduler.local.json') -Raw -Encoding UTF8 | ConvertFrom-Json
 $env:PATH=(@((Split-Path $config.python),(Split-Path $config.codex),(Split-Path $config.git)) -join ';')+';'+$env:PATH
 Set-Location -LiteralPath $base
 # Keep the wrapper lock and all existing content/backup rules.
 $ErrorActionPreference='Continue'
 & $config.powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'run.ps1') *> $log
 $exitCode=$LASTEXITCODE
 $ErrorActionPreference='Stop'
 if ($exitCode -ne 0) { throw "Daily runner exit $exitCode; see log." }
 $status.status='success'
} catch {
 $status.status='failed'
 $status.error=$_.Exception.Message
 if ($exitCode -eq 0) { $exitCode=1 }
 $_ | Out-String | Add-Content -LiteralPath $log -Encoding UTF8
} finally {
 $status.exitCode=$exitCode
 $status.finishedAt=(Get-Date).ToString('o')
 Write-Status
}
exit $exitCode
