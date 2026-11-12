$ErrorActionPreference = 'Stop'
$base = Split-Path -Parent $PSScriptRoot
$git = (Get-Command git.exe -ErrorAction SilentlyContinue).Source
if (!$git -and (Test-Path -LiteralPath 'D:\Git\cmd\git.exe')) { $git = 'D:\Git\cmd\git.exe' }
if (!$git) { throw 'Git is not installed or available to this task.' }
$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE = 'never'
function Invoke-RepoGit {
 param([string[]]$GitArguments)
 $savedPreference = $ErrorActionPreference
 $ErrorActionPreference = 'Continue'
 try {
  $result = & $git -C $base -c http.proxy=http://127.0.0.1:7890 -c http.version=HTTP/1.1 @GitArguments 2>&1
  $gitExit = $LASTEXITCODE
 } finally { $ErrorActionPreference = $savedPreference }
 if ($gitExit -ne 0) { throw "Git failed: $($GitArguments[0]). $($result -join [Environment]::NewLine)" }
 return $result
}
$branch = (Invoke-RepoGit -GitArguments @('branch','--show-current') | Out-String).Trim()
if (!$branch) { throw 'Detached HEAD: refusing automatic commit.' }
$staged = Invoke-RepoGit -GitArguments @('diff','--cached','--name-only')
if ($staged) { throw 'Existing staged changes detected; refusing to mix commits.' }
$lessons = @(Get-ChildItem -LiteralPath $base -File -Filter 'Day*.html')
foreach ($lesson in $lessons) {
 $html = Get-Content -LiteralPath $lesson.FullName -Raw -Encoding UTF8
 if ($html.Length -lt 2000 -or $html -notmatch '</html>' -or $html -notmatch 'https://') { throw "Invalid lesson: $($lesson.Name)" }
}
if ($lessons.Count -gt 0) {
 Invoke-RepoGit -GitArguments (@('add','--') + @($lessons | ForEach-Object { $_.Name })) | Out-Host
 $changed = Invoke-RepoGit -GitArguments @('diff','--cached','--name-only')
 if ($changed) {
  $date = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow,'China Standard Time').ToString('yyyy-MM-dd')
  Invoke-RepoGit -GitArguments @('commit','-m',"保存每日英语学习页面 $date") | Out-Host
 }
}
# Always push, including retries after a previous failed upload; never force push.
Invoke-RepoGit -GitArguments @('push','-u','origin',$branch) | Out-Host
