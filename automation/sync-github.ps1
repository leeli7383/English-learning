param([Parameter(Mandatory=$true)][string]$LessonName)
$ErrorActionPreference = 'Stop'
$base = Split-Path -Parent $PSScriptRoot
$git = (Get-Command git.exe -ErrorAction SilentlyContinue).Source
if (!$git -and (Test-Path -LiteralPath 'D:\Git\cmd\git.exe')) { $git = 'D:\Git\cmd\git.exe' }
if (!$git) { throw 'Git is not installed or available to this task.' }
# Local approval gate: keep scheduled uploads disabled until visibility is confirmed.
$uploadApproval = & $git -C $base config --local --get englishlearning.githubUploadApproved
if ($uploadApproval -ne 'true') { throw 'GitHub upload paused: confirm private repository or explicitly approve public upload first.' }
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
 return @($result | ForEach-Object { $_.ToString() })
}
$branch = (Invoke-RepoGit -GitArguments @('branch','--show-current') | Out-String).Trim()
if ($branch -ne 'ai/daily-html-backup') { throw 'Expected branch ai/daily-html-backup; refusing to push another branch.' }
$remote = (Invoke-RepoGit -GitArguments @('remote','get-url','origin') | Out-String).Trim()
if ($remote -notin @('https://github.com/leeli7383/English-learning.git','https://github.com/leeli7383/English-learning','git@github.com:leeli7383/English-learning.git')) { throw 'Unexpected origin; refusing upload.' }
if ($LessonName -notmatch '^Day\s*\d+.*\d{4}-\d{2}-\d{2}.*\.html$' -or [IO.Path]::GetFileName($LessonName) -ne $LessonName) { throw 'Invalid lesson filename.' }
$staged = Invoke-RepoGit -GitArguments @('diff','--cached','--name-only')
if ($staged) { throw 'Existing staged changes detected; refusing to mix commits.' }
$lesson = Join-Path $base $LessonName
if (!(Test-Path -LiteralPath $lesson -PathType Leaf)) { throw 'Lesson is missing.' }
$html = Get-Content -LiteralPath $lesson -Raw -Encoding UTF8
if ($html.Length -lt 2000 -or $html -notmatch '</html>' -or $html -notmatch 'https://') { throw 'Lesson validation failed.' }
$stageFiles = @($LessonName, 'data/expressions.json', 'data/used-expressions.json', 'PROGRESS.md')
Invoke-RepoGit -GitArguments (@('add','--') + $stageFiles) | Out-Host
$changed = Invoke-RepoGit -GitArguments @('diff','--cached','--name-only')
if ($changed) {
 $date = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow,'China Standard Time').ToString('yyyy-MM-dd')
 Invoke-RepoGit -GitArguments @('commit','-m',"保存每日英语学习页面 $date") | Out-Host
}
# Always push, including retries after a previous failed upload; never force push.
Invoke-RepoGit -GitArguments @('push','-u','origin',$branch) | Out-Host
