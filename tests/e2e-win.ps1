# docs/host-setup.md の Windows を実機でなぞる。管理者の PowerShell で (CI の Windows ランナー向け)
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File tests\e2e-win.ps1
$ErrorActionPreference = 'Continue'
$script:fail = 0
$Agent = 'C:\ProgramData\netcap\netcap-agent.ps1'

function Expect([string]$what, [string]$re, [scriptblock]$cmd) {
  $out = (& $cmd 2>&1 | Out-String)
  if ($out -match $re) { "ok   $what" } else { "FAIL $what"; $out; $script:fail = 1 }
}
function Agent { powershell -NoProfile -ExecutionPolicy Bypass -File $Agent @args }

$root = Split-Path -Parent $PSScriptRoot
powershell -NoProfile -ExecutionPolicy Bypass -File "$root\win\install.ps1" | Out-Null

Expect 'status: 最初は off' 'state=off' { Agent status }
Expect 'get: boot=keep' 'boot=keep' { Agent get }
Expect 'on: 上りだけ、下りは非対応' 'state=on up_mbit=2 down_mbit=- down_src=unsupported' { Agent on 2 3; Agent status }
Expect 'set: 既定を書き換える' 'default_up=4 default_down=5' { Agent set 4 5; Agent get }
Expect 'set: かかっていれば張り直す' 'state=on up_mbit=4 ' { Agent status }

# docs/design.md「素通しにする宛先」: 宛先ごとに絞らないポリシーがある
$local = Get-NetQosPolicy | Where-Object Name -like 'netcap-local-*' | ForEach-Object { $_.IPDstPrefixMatchCondition }
foreach ($n in '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '100.64.0.0/10', '127.0.0.0/8', '169.254.0.0/16', '224.0.0.0/4') {
  Expect "素通し: $n" 'True' { $local -contains $n }
}
Expect '素通し: DNS' '53' { (Get-NetQosPolicy -Name netcap-dns).IPDstPortStartMatchCondition }

Expect 'off' 'state=off' { Agent off; Agent status }

# docs/host-setup.md: forced command で許可していない動詞は denied
Expect '--allow にない動詞は拒む' 'netcap-agent: .*on' {
  $env:SSH_ORIGINAL_COMMAND = "powershell -File $Agent on"; Agent --allow 'status get'
}
Remove-Item Env:SSH_ORIGINAL_COMMAND

# docs/design.md: C:\ProgramData\netcap は Users が書けない
Expect 'Users は書けない' '^\s*$' {
  (Get-Acl 'C:\ProgramData\netcap').Access |
    Where-Object { $_.IdentityReference -match 'Users$' -and $_.FileSystemRights -match 'Write|Modify|FullControl' }
}

powershell -NoProfile -ExecutionPolicy Bypass -File 'C:\ProgramData\netcap\uninstall.ps1' | Out-Null
Expect 'uninstall: ポリシーが残らない' '^\s*$' { Get-NetQosPolicy | Where-Object Name -like 'netcap-*' }
Expect 'uninstall: フォルダが残らない' 'False' { Test-Path 'C:\ProgramData\netcap' }

exit $script:fail
