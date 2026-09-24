# netcap-agent.ps1 — netcap が Windows の端末側で叩く入口。ssh の forced command にもそのまま使う
#
#   netcap-agent.ps1 <動詞> [引数...]              直接
#   netcap-agent.ps1 --allow '<動詞> <動詞> …'     forced command として。頼まれた中身は
#                                                  $env:SSH_ORIGINAL_COMMAND で来る
#
# 動詞: status get check on off set (mac 版の netcap-agent と同じ)
#
# 許可を決めるのは操作される側。管理者の鍵なら
# C:\ProgramData\ssh\administrators_authorized_keys の 1 行で、その鍵に頼めることを絞る:
#
#   restrict,command="powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\netcap\netcap-agent.ps1 --allow 'status get check'" ssh-ed25519 AAAA… netcap@laptop
#
# Windows の管理者の ssh セッションは昇格した状態で動く。mac の sudoers のような二段目は無く、
# ここが唯一の関門になる。だから forced command で固定することが mac 以上に効く。
$ErrorActionPreference = 'Stop'

$Dir = 'C:\ProgramData\netcap'
$Verbs = 'status', 'get', 'check', 'on', 'off', 'set'

function Deny([string]$m) {
  [Console]::Error.WriteLine("netcap-agent: $m")
  exit 77
}

$words = @($args)
$allowed = $Verbs
if ($words.Count -ge 1 -and $words[0] -eq '--allow') {
  if ($words.Count -ne 2) { Deny "usage: netcap-agent.ps1 --allow '<動詞> …'" }
  $allowed = @($words[1] -split '\s+' | Where-Object { $_ })
  $orig = $env:SSH_ORIGINAL_COMMAND
  if (-not $orig) { Deny "コマンドを付けて呼ぶ (許可されている動詞: $($allowed -join ' '))" }
  # 頼まれた中身は空白で区切るだけ。引用も式も解釈しない
  $words = @($orig -split '\s+' | Where-Object { $_ })
  # netcap は "powershell … -File …\netcap-agent.ps1 <動詞> …" の形で送ってくる。agent より前を捨てる
  for ($i = 0; $i -lt $words.Count; $i++) {
    if ($words[$i] -match 'netcap-agent\.ps1$') { $words = @($words | Select-Object -Skip ($i + 1)); break }
  }
}

if ($words.Count -eq 0) { Deny "usage: netcap-agent.ps1 <動詞> [引数...] (動詞: $($Verbs -join ' '))" }
$verb = $words[0]
$rest = @($words | Select-Object -Skip 1)
if ($Verbs -notcontains $verb) { Deny "知らない動詞: $verb" }
if ($allowed -notcontains $verb) { Deny "この鍵には許可されていない: $verb (許可: $($allowed -join ' '))" }

if ($verb -eq 'check') {
  # 実測が受けるのは --bytes <数値> だけ
  if ($rest.Count -gt 0 -and ($rest.Count -ne 2 -or $rest[0] -ne '--bytes' -or $rest[1] -notmatch '^[0-9]+$')) {
    Deny 'check が受けるのは --bytes <数値> だけ'
  }
  & (Join-Path $Dir 'netcap-check.ps1') @rest
  exit $LASTEXITCODE
}

# 数値を取るのは on / set だけ。それ以外の動詞は引数を取らない
foreach ($a in $rest) { if ($a -notmatch '^[0-9]+([.][0-9]+)?$') { Deny "引数は数値だけ: $a" } }
& (Join-Path $Dir 'netshape.ps1') $verb @rest
exit $LASTEXITCODE
