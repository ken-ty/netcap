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
# Users can also create C:\ProgramData\netcap before the install and own it, so an existing folder is taken over:
# Administrators own it and everything in it, and nothing in it keeps entries of its own (#89).
$ErrorActionPreference = 'Stop'

$p = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  [Console]::Error.WriteLine('run as Administrator'); exit 1
}

$Src = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dir = 'C:\ProgramData\netcap'

# Takes one entry and everything under it over: Administrators become the owner, the folder gets exactly
# SYSTEM full, Administrators full, Users read & execute, and everything in it only inherits those.
# takeown /A uses the take-ownership privilege, so it works even where the old owner left Administrators no rights
# (/R is not used: its /D answer is localized). A link is refused, not followed: the copy or the ACL would land elsewhere
function Lock-Entry($path, [switch]$Top) {
  $item = Get-Item -LiteralPath $path -Force
  if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    [Console]::Error.WriteLine("$path is a link; remove it, then run install.ps1 again"); exit 1
  }
  & takeown.exe /F $path /A | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "takeown failed on $path ($LASTEXITCODE)" }
  if ($Top) {
    # A new ACL, not an edit of the old one: entries someone else added to the folder do not survive
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($e in ('S-1-5-18', 'FullControl'), ('S-1-5-32-544', 'FullControl'), ('S-1-5-32-545', 'ReadAndExecute')) {
      $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule(
        (New-Object Security.Principal.SecurityIdentifier $e[0]), $e[1], 'ContainerInherit, ObjectInherit', 'None', 'Allow')))
    }
    $item.SetAccessControl($acl)
  } else {
    & icacls.exe $path /reset | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls /reset failed on $path ($LASTEXITCODE)" }
  }
  if ($item.PSIsContainer) { Get-ChildItem -LiteralPath $path -Force | ForEach-Object { Lock-Entry $_.FullName } }
}

New-Item -ItemType Directory -Force $Dir | Out-Null
Lock-Entry $Dir -Top
foreach ($f in 'netshape.ps1', 'netcap-agent.ps1', 'netcap-check.ps1', 'uninstall.ps1') {
  Copy-Item -Force (Join-Path $Src $f) (Join-Path $Dir $f)
  Lock-Entry (Join-Path $Dir $f)  # a new file is owned by whoever ran this; make it Administrators
}

'installed (boot=keep: the on / off state survives reboots)'
& (Join-Path $Dir 'netshape.ps1') get
& (Join-Path $Dir 'netshape.ps1') status | Select-Object -First 1
