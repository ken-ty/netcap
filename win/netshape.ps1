# netshape.ps1 — この Windows 自身の WAN 向け通信に上限をかける (NetQosPolicy)
#
#   netshape.ps1 on [UP_MBIT DOWN_MBIT]  上限をかける。引数を付けると今回だけその値
#   netshape.ps1 off                     上限を外す
#   netshape.ps1 status                  いまの状態。1 行目は実物 (NetQosPolicy) から導く
#   netshape.ps1 set UP_MBIT DOWN_MBIT   既定を書き換える。いま上限がかかっていれば張り直す
#   netshape.ps1 get                     既定と起動時の挙動を 1 行で
#
# mac 版 (pf + dummynet) との違い:
#   - 絞れるのは上り (送信) だけ。Windows の QoS ポリシーは送信側にしか効かない。
#     DOWN_MBIT は受け取るが使わず、status は down_src=unsupported を返す
#   - ポリシーはこの機械の永続の保存先 (localhost) に置く。on / off の状態は再起動してもそのまま
#     残る (get は boot=keep を返す)。ActiveStore (再起動で消える保存先) は宛先の条件
#     (-IPDstPrefixMatchCondition) を保持せず、宅内宛ても絞ってしまった (2026-09-25 実機で実測)
#
# 触るのは名前が netcap- で始まるポリシーだけ。
#   netcap-wan       -Default (他のどれにも当たらない通信) を UP_MBIT に絞る
#   netcap-local-N   プライベート IP・CGNAT 帯などの宛先。絞らない (DSCP 0 を付けるだけ)
#   netcap-dns       宛先ポート 53。絞らない
# 他に当たるポリシーがある通信は -Default に落ちないので、宛先ごとのポリシーで素通しにできる。
#
# 管理者で動く。置き場所 (C:\ProgramData\netcap) は install.ps1 が管理者だけ書けるようにする。
$ErrorActionPreference = 'Stop'

$Dir = 'C:\ProgramData\netcap'
$Conf = Join-Path $Dir 'netshape.conf'
$Local = '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '100.64.0.0/10', '127.0.0.0/8', '169.254.0.0/16', '224.0.0.0/4'

function IsNumber([string]$s) { $s -match '^[0-9]+([.][0-9]+)?$' }
function Usage([string]$m) { [Console]::Error.WriteLine("usage: netshape.ps1 $m"); exit 2 }

$p = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  [Console]::Error.WriteLine('管理者で実行してください'); exit 1
}

# 既定値。設定は数値の key=value として読むだけ
$UpMbit = '1'; $DownMbit = '1'
if (Test-Path $Conf) {
  foreach ($line in Get-Content $Conf) {
    $k, $v = $line -split '=', 2
    if (-not (IsNumber $v)) { continue }
    if ($k -eq 'UP_MBIT') { $UpMbit = $v }
    if ($k -eq 'DOWN_MBIT') { $DownMbit = $v }
  }
}

function Ours { @(Get-NetQosPolicy -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'netcap-*' }) }

function Remove-Ours {
  foreach ($q in Ours) { Remove-NetQosPolicy -Name $q.Name -Confirm:$false }
}

function On([string[]]$a) {
  if ($a.Count -ne 0) {
    if ($a.Count -ne 2 -or -not (IsNumber $a[0]) -or -not (IsNumber $a[1])) { Usage 'on [UP_MBIT DOWN_MBIT]' }
    $script:UpMbit = $a[0]; $script:DownMbit = $a[1]
  }
  Remove-Ours
  $bps = [uint64]([double]$UpMbit * 1000000)
  New-NetQosPolicy -Name netcap-wan -Default -ThrottleRateActionBitsPerSecond $bps | Out-Null
  for ($i = 0; $i -lt $Local.Count; $i++) {
    New-NetQosPolicy -Name "netcap-local-$i" -IPDstPrefixMatchCondition $Local[$i] -DSCPAction 0 | Out-Null
  }
  New-NetQosPolicy -Name netcap-dns -IPDstPortMatchCondition 53 -DSCPAction 0 | Out-Null
  "netshape ON  up=${UpMbit}Mbit/s down=unsupported"
}

function Off {
  Remove-Ours
  'netshape OFF'
}

function Status {
  $ours = Ours
  $wan = $ours | Where-Object Name -eq 'netcap-wan'
  $expected = $Local.Count + 2
  $up = '-'
  if ($wan) { $up = '{0:G}' -f ($wan.ThrottleRate / 1000000) }
  if ($wan -and $ours.Count -eq $expected) { $state = 'on' }
  elseif ($ours.Count -eq 0) { $state = 'off' }
  else { $state = 'partial' }  # 一部だけ残っている。on か off を打ち直す
  "netshape state=$state up_mbit=$up down_mbit=- down_src=unsupported policies=$($ours.Count)"
  '--- policies (netcap-*)'
  if ($ours.Count -eq 0) { '(none)' }
  foreach ($q in $ours) { "$($q.Name) template=$($q.Template) throttle=$($q.ThrottleRate) dst=$($q.IPDstPrefixMatchCondition) port=$($q.IPDstPortStartMatchCondition)" }
}

function Get-Default {
  $c = if (Test-Path $Conf) { $Conf } else { 'none' }
  "netshape default_up=$UpMbit default_down=$DownMbit boot=keep conf=$c"
}

function Set-Default([string[]]$a) {
  if ($a.Count -ne 2 -or -not (IsNumber $a[0]) -or -not (IsNumber $a[1])) { Usage 'set UP_MBIT DOWN_MBIT' }
  $tmp = "$Conf.tmp"
  "# netshape.ps1 の既定値。netshape.ps1 set が書く`r`nUP_MBIT=$($a[0])`r`nDOWN_MBIT=$($a[1])" | Set-Content -Path $tmp -Encoding ASCII
  Move-Item -Force $tmp $Conf
  if (Ours | Where-Object Name -eq 'netcap-wan') {
    On $a | Out-Null
    "netshape SET up=$($a[0])Mbit/s down=$($a[1])Mbit/s (適用中だったので張り直した)"
  } else {
    "netshape SET up=$($a[0])Mbit/s down=$($a[1])Mbit/s (次の on から効く)"
  }
}

$verb = if ($args.Count -gt 0) { $args[0] } else { '' }
$rest = @($args | Select-Object -Skip 1)
switch ($verb) {
  'on' { On $rest }
  'off' { Off }
  'status' { Status }
  'set' { Set-Default $rest }
  'get' { Get-Default }
  default { Usage '{on [UP_MBIT DOWN_MBIT]|off|status|set UP_MBIT DOWN_MBIT|get}' }
}
