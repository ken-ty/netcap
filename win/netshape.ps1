# netshape.ps1 — caps this Windows machine's own WAN traffic (NetQosPolicy)
#
#   netshape.ps1 on [UP_MBIT DOWN_MBIT]  apply the cap. With arguments, use those values this time only
#   netshape.ps1 off                     remove the cap
#   netshape.ps1 status                  current state. Line 1 is derived from the actual NetQosPolicy objects
#   netshape.ps1 set UP_MBIT DOWN_MBIT   change the defaults. Reapplies the cap if one is in effect
#   netshape.ps1 get                     defaults and boot behavior on one line
#
# Differences from the mac version (pf + dummynet):
#   - Only upload (send) can be capped. Windows QoS policies act only on the sending side.
#     DOWN_MBIT is accepted but unused, and status returns down_src=unsupported
#   - Policies go in this machine's persistent store (localhost), so the on / off state survives
#     reboots (get returns boot=keep). ActiveStore (a store cleared on reboot) dropped the destination
#     condition (-IPDstPrefixMatchCondition) and capped LAN traffic too (measured on real hardware, 2026-09-25)
#
# Only policies whose names start with netcap- are touched.
#   netcap-wan       caps -Default (traffic no other policy matches) to UP_MBIT
#   netcap-local-N   destinations such as private IPs and the CGNAT range. Not capped (only sets DSCP 0)
#   netcap-dns       destination port 53. Not capped
# Traffic matched by another policy never falls through to -Default, so per-destination policies let it pass through.
#
# Runs as Administrator. install.ps1 makes its location (C:\ProgramData\netcap) writable by Administrators only.
$ErrorActionPreference = 'Stop'

$Dir = 'C:\ProgramData\netcap'
$Conf = Join-Path $Dir 'netshape.conf'
$Local = '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '100.64.0.0/10', '127.0.0.0/8', '169.254.0.0/16', '224.0.0.0/4'

function IsNumber([string]$s) { $s -match '^[0-9]+([.][0-9]+)?$' }
function Usage([string]$m) { [Console]::Error.WriteLine("usage: netshape.ps1 $m"); exit 2 }

$p = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  [Console]::Error.WriteLine('run as Administrator'); exit 1
}

# Defaults. The config is read only as numeric key=value pairs
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
  else { $state = 'partial' }  # only some are left. Run on or off again
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
  "# netshape.ps1 defaults. Written by netshape.ps1 set`r`nUP_MBIT=$($a[0])`r`nDOWN_MBIT=$($a[1])" | Set-Content -Path $tmp -Encoding ASCII
  Move-Item -Force $tmp $Conf
  if (Ours | Where-Object Name -eq 'netcap-wan') {
    On $a | Out-Null
    "netshape SET up=$($a[0])Mbit/s down=$($a[1])Mbit/s (reapplied, since a cap was in effect)"
  } else {
    "netshape SET up=$($a[0])Mbit/s down=$($a[1])Mbit/s (takes effect at the next on)"
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
