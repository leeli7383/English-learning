param([switch]$Preview)
$ErrorActionPreference = 'Stop'
$env:HTTPS_PROXY = 'http://127.0.0.1:7890'
$env:HTTP_PROXY = 'http://127.0.0.1:7890'
$env:NO_PROXY = 'localhost,127.0.0.1'
$base = 'D:\English_learning'
$now = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow,'China Standard Time')
$start = [datetime]'2026-11-07'
if (!$Preview -and $now.Date -lt $start) { exit 0 }
$day = [Math]::Max(1, [int]($now.Date-$start).TotalDays+1)
$name = if ($Preview) { 'Preview.html' } else { 'Day{0:D3}_{1}.html' -f $day,$now.ToString('yyyy-MM-dd') }
$out = Join-Path $base $name
$lock = $null
try {
 $lock = [IO.File]::Open((Join-Path $base 'automation\run.lock'),'OpenOrCreate','ReadWrite','None')
 if (Test-Path -LiteralPath $out) {
  if (!$Preview) { & (Join-Path $base 'automation\sync-github.ps1') }
  return
 }
 $prompt = Get-Content -LiteralPath (Join-Path $base 'automation\prompt.txt') -Raw -Encoding UTF8
 $prompt += "`nOutput filename: $name . Beijing date: $($now.ToString('yyyy-MM-dd'))."
 $history = Get-ChildItem -LiteralPath $base -Filter 'Day*.html' | Sort-Object Name | Select-Object -Last 90 | ForEach-Object { [regex]::Matches((Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8), '(?is)<h2[^>]*>(.*?)</h2>') | ForEach-Object { $_.Groups[1].Value -replace '<[^>]+>','' } }
 $prompt += "`nAvoid these previous expressions: $($history -join '; ')"
 $log = Join-Path $base ('logs\run-'+$now.ToString('yyyyMMdd-HHmmss')+'.log')
 $ErrorActionPreference = 'Continue'
 $prompt | & (Join-Path $env:APPDATA 'npm\codex.cmd') exec --sandbox read-only -c 'web_search="live"' -C $base --skip-git-repo-check --color never -o ($out + '.partial') - 2>&1 | Out-File -LiteralPath $log -Encoding UTF8
 $ErrorActionPreference = 'Stop'
 if ($LASTEXITCODE -ne 0) { throw "Codex failed. See $log" }
 $partial = $out + '.partial'
 if (Test-Path -LiteralPath $partial) {
  $doc = Get-Content -LiteralPath $partial -Raw -Encoding UTF8
  $doc = $doc -replace '(?s)^\s*```html\s*','' -replace '\s*```\s*$',''
  $doc = [regex]::Replace($doc, '<img\b[^>]*src="(https://[^"]+)"[^>]*>', {
   param($m)
   try {
    $uri = [uri][System.Net.WebUtility]::HtmlDecode($m.Groups[1].Value)
    if ($uri.IsLoopback) { throw 'Invalid image URL' }
    $client = New-Object System.Net.WebClient
    $client.Proxy = New-Object System.Net.WebProxy('http://127.0.0.1:7890')
    $bytes = $client.DownloadData($uri)
    $type = $client.ResponseHeaders['Content-Type'].Split(';')[0]
    $client.Dispose()
    if ($type -notmatch '^image/(jpeg|png|webp|gif)$' -or $bytes.Length -gt 10000000) { throw 'Unsupported image' }
    return $m.Value.Replace($m.Groups[1].Value, ('data:'+$type+';base64,'+[Convert]::ToBase64String($bytes)))
   } catch { return '<p>原始配图未能下载，本条暂缺图片。</p>' }
  })
  if ($doc.Length -lt 2000 -or $doc -notmatch '</html>' -or $doc -notmatch 'https://') { throw 'Invalid lesson HTML' }
  [IO.File]::WriteAllText($partial,$doc,[Text.UTF8Encoding]::new($true))
  Move-Item -LiteralPath $partial -Destination $out
 }
 if (!(Test-Path -LiteralPath $out)) { throw "No final lesson. See $log" }
 $html = Get-Content -LiteralPath $out -Raw -Encoding UTF8
 if ($html.Length -lt 2000 -or $html -notmatch '</html>' -or $html -notmatch 'https://') { throw 'Lesson validation failed' }
 if (!$Preview) { & (Join-Path $base 'automation\sync-github.ps1') }
} finally { if ($lock) { $lock.Dispose() } }
