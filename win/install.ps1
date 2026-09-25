# install.ps1 — installs netshape and netcap-agent on this Windows machine. Copy the whole win/ directory here, then as Administrator:
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
#
# What it does:
#   C:\ProgramData\netcap\netshape.ps1       the shaper (NetQosPolicy; runs as Administrator)
#   C:\ProgramData\netcap\netcap-agent.ps1   the entry point netcap calls (also used as the forced command)
#   C:\ProgramData\netcap\netcap-check.ps1   measurement
#   C:\ProgramData\netcap\uninstall.ps1      for removal
#
# The default ACL on C:\ProgramData grants Users "create folders / write data", inherited all the way down.
# Left as is, a non-administrator could replace scripts that run as Administrator
# (the same reason the mac version avoids /usr/local/sbin). So we cut inheritance:
# only SYSTEM and Administrators can write, Users can only read. Principals are given by SID (works on localized Windows too).
$ErrorActionPreference = 'Stop'

$p = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  [Console]::Error.WriteLine('run as Administrator'); exit 1
}

$Src = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dir = 'C:\ProgramData\netcap'
New-Item -ItemType Directory -Force $Dir | Out-Null
& icacls.exe $Dir /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-32-545:(OI)(CI)RX' | Out-Null
if ($LASTEXITCODE -ne 0) { throw "icacls failed ($LASTEXITCODE)" }

foreach ($f in 'netshape.ps1', 'netcap-agent.ps1', 'netcap-check.ps1', 'uninstall.ps1') {
  Copy-Item -Force (Join-Path $Src $f) (Join-Path $Dir $f)
}
# The copied files inherit only the parent's ACL (this also drops explicit grants on files left from before)
& icacls.exe "$Dir\*" /reset | Out-Null
if ($LASTEXITCODE -ne 0) { throw "icacls /reset failed ($LASTEXITCODE)" }

'installed (boot=keep: the on / off state survives reboots)'
& (Join-Path $Dir 'netshape.ps1') get
& (Join-Path $Dir 'netshape.ps1') status | Select-Object -First 1
