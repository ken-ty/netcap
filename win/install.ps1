# install.ps1 — この Windows に netshape と netcap-agent を入れる。win/ ディレクトリごと置いてから、管理者で:
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
#
# 何をするか:
#   C:\ProgramData\netcap\netshape.ps1       本体 (NetQosPolicy。管理者で動く)
#   C:\ProgramData\netcap\netcap-agent.ps1   netcap が叩く入口 (forced command にも使う)
#   C:\ProgramData\netcap\netcap-check.ps1   実測
#   C:\ProgramData\netcap\uninstall.ps1      外すとき
#
# C:\ProgramData の既定の ACL は Users に「フォルダの作成・書き込み」を配下まで継承させる。
# そのままだと管理者でない利用者が、管理者で動くスクリプトを差し替えられる
# (mac 版で /usr/local/sbin を避けたのと同じ理由)。だから継承を切り、
# SYSTEM と Administrators だけが書け、Users は読むだけにする。名前は SID で指す (日本語版でも通る)。
$ErrorActionPreference = 'Stop'

$p = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  [Console]::Error.WriteLine('管理者で実行してください'); exit 1
}

$Src = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dir = 'C:\ProgramData\netcap'
New-Item -ItemType Directory -Force $Dir | Out-Null
& icacls.exe $Dir /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' | Out-Null
if ($LASTEXITCODE -ne 0) { throw "icacls が失敗した ($LASTEXITCODE)" }

foreach ($f in 'netshape.ps1', 'netcap-agent.ps1', 'netcap-check.ps1', 'uninstall.ps1') {
  Copy-Item -Force (Join-Path $Src $f) (Join-Path $Dir $f)
}
# 置いたファイルは親の ACL だけを継承させる (以前からあったファイルの明示的な許可も落とす)
& icacls.exe "$Dir\*" /reset | Out-Null
if ($LASTEXITCODE -ne 0) { throw "icacls /reset が失敗した ($LASTEXITCODE)" }

'installed (boot=keep: on / off の状態は再起動後も残る)'
& (Join-Path $Dir 'netshape.ps1') get
& (Join-Path $Dir 'netshape.ps1') status | Select-Object -First 1
