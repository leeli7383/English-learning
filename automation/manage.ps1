param([ValidateSet('Menu','Install','Status','Run','Pause','Resume','Test','Logs','Remove')][string]$Action='Menu')
$ErrorActionPreference='Stop'
$base=Split-Path -Parent $PSScriptRoot
$configPath=Join-Path $PSScriptRoot 'scheduler.local.json'
$taskName='EnglishLearningDailyV2'
function Read-Config {
 if (!(Test-Path -LiteralPath $configPath)) { throw 'Run Install first.' }
 Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
}
function Get-TaskFolder {
 $service=New-Object -ComObject 'Schedule.Service'
 $service.Connect()
 $service.GetFolder('\')
}
function Find-OurTask {
 try { (Get-TaskFolder).GetTask($taskName) }
 catch { if ($_.Exception.HResult -notin @(-2147024894,-2147352567)) { throw }; return $null }
}
function Get-OurTask {
 $task=Find-OurTask
 if (!$task) { throw 'Task is not installed. Run Install first.' }
 $expected=Join-Path $PSScriptRoot 'scheduled-run.ps1'
 if ($task.Definition.Actions.Item(1).Arguments -notlike "*$expected*") { throw 'Task name belongs to another action; refusing modification.' }
 $task
}
if ($Action -eq 'Menu') {
 do {
  Write-Host "`n每日英语管理（本地操作不调用模型）" -ForegroundColor Cyan
  Write-Host '1 查看状态  2 立即运行  3 暂停  4 恢复  5 检查环境  6 打开日志  0 退出'
  $choice=Read-Host '请选择'
  $next=@{'1'='Status';'2'='Run';'3'='Pause';'4'='Resume';'5'='Test';'6'='Logs'}[$choice]
  if ($next) { try { & $PSCommandPath -Action $next } catch { Write-Host $_.Exception.Message -ForegroundColor Red } }
 } while ($choice -ne '0')
 return
}
switch ($Action) {
 'Install' {
  if ((Get-TimeZone).Id -ne 'China Standard Time') { throw 'System timezone must be China Standard Time for Beijing 09:00.' }
  $config=[ordered]@{version=1;taskName=$taskName;root=$base;timezone='Asia/Shanghai';time='09:00';python=(Get-Command python.exe -ErrorAction Stop).Source;codex=(Get-Command codex.cmd -ErrorAction Stop).Source;git=(Get-Command git.exe -ErrorAction Stop).Source;powershell=(Get-Command powershell.exe -ErrorAction Stop).Source}
  $config | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8
  & $PSCommandPath -Action Test
  $existing=Find-OurTask
  if ($existing) { $null=Get-OurTask }
  $runner=Join-Path $PSScriptRoot 'scheduled-run.ps1'
  $a=New-ScheduledTaskAction -Execute $config.powershell -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$runner`"" -WorkingDirectory $base
  $trigger=New-ScheduledTaskTrigger -Daily -At '09:00'
  $settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 45) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
  $principal=New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
  $task=New-ScheduledTask -Action $a -Trigger $trigger -Settings $settings -Principal $principal -Description '每日英语：真实检索、固定模板、离线配图及 GitHub 备份。由 D:\English_learning 管理。'
  Register-ScheduledTask -TaskName $taskName -TaskPath '\' -InputObject $task -Force | Out-Null
  & $PSCommandPath -Action Status
 }
 'Status' {
  $task=Get-OurTask
  [pscustomobject]@{Task=$task.Name;State=@('Unknown','Disabled','Queued','Ready','Running')[[int]$task.State];Daily='09:00 Beijing';NextRun=$task.NextRunTime;LastRun=$task.LastRunTime;LastResult=$task.LastTaskResult} | Format-List
  foreach ($path in @((Join-Path $base 'data/scheduler-status.json'),(Join-Path $base 'data/state.json'))) {
   if (Test-Path -LiteralPath $path) { Write-Host $path; Get-Content -LiteralPath $path -Raw -Encoding UTF8 }
  }
 }
 'Run' { $task=Get-OurTask; $null=$task.Run($null); Write-Host '已提交后台运行；当天已有课程时跳过模型，只检查备份。用查看状态查询结果。' }
 'Pause' { $task=Get-OurTask; $task.Enabled=$false; Write-Host '每日调度已暂停（不会强制终止已开始的任务）。' }
 'Resume' { $task=Get-OurTask; $task.Enabled=$true; Write-Host '每日 09:00 调度已恢复。' }
 'Test' {
  $c=Read-Config
  if ($c.root -ne $base) { throw 'Root changed; run Install again.' }
  foreach($path in @($c.python,$c.codex,$c.git,$c.powershell,(Join-Path $base 'automation/prompt.txt'),(Join-Path $base 'templates/lesson.html'))) { if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing: $path" } }
  & $c.python (Join-Path $PSScriptRoot 'lesson.py') --root $base --refresh-index
  if ($LASTEXITCODE -ne 0) { throw 'Index check failed.' }
  & $c.python -c "import unittest,sys; suite=unittest.defaultTestLoader.discover(sys.argv[1], pattern='test_lesson.py'); result=unittest.TextTestRunner(stream=sys.stdout).run(suite); sys.exit(not result.wasSuccessful())" $PSScriptRoot
  if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
  foreach($file in @('run.ps1','scheduled-run.ps1','manage.ps1','sync-github.ps1')) {
   $tokens=$null;$errors=$null
   [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $file),[ref]$tokens,[ref]$errors)
   if ($errors) { throw "PowerShell syntax failed: $file" }
  }
  Write-Host '环境、索引、测试和脚本语法通过；未调用模型。'
 }
 'Logs' { Start-Process explorer.exe -ArgumentList @((Join-Path $base 'logs')) }
 'Remove' { $null=Get-OurTask; (Get-TaskFolder).DeleteTask($taskName,0); Write-Host '只移除了新定时任务，课程和配置文件仍保留。' }
}
