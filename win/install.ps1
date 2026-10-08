# install.ps1 — installs netshape and netcap-agent on this Windows machine. Copy the whole win/ directory here, then as Administrator:
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 [-WithDownload]
#
# What it does:
#   C:\ProgramData\netcap\netshape.ps1       the shaper (NetQosPolicy; runs as Administrator)
#   C:\ProgramData\netcap\netshape-down.ps1  the download shaper (WinDivert; runs as SYSTEM, only with -WithDownload)
#   C:\ProgramData\netcap\netcap-agent.ps1   the entry point netcap calls (also used as the forced command)
#   C:\ProgramData\netcap\netcap-check.ps1   measurement
#   C:\ProgramData\netcap\uninstall.ps1      for removal
#   C:\ProgramData\netcap\windivert\        with -WithDownload: WinDivert.dll, WinDivert64.sys, and LICENSE
#
# -WithDownload also caps download (docs/adr/0001-cap-download-on-windows.md). netcap ships no WinDivert: this fetches
# the official 2.2.2 release over HTTPS, refuses it unless its SHA-256 is the one pinned below, and takes only the x64
# driver, its DLL, and the license out of it. x64 Windows only: WinDivert has no signed ARM64 driver.
# Without -WithDownload, a WinDivert fetched before is stopped and removed: each install sets this again, as --boot does.
#
# The default ACL on C:\ProgramData grants Users "create folders / write data", inherited all the way down.
# Left as is, a non-administrator could replace scripts that run as Administrator
# (the same reason the mac version avoids /usr/local/sbin). So we cut inheritance:
# only SYSTEM and Administrators can write, Users can only read. Principals are given by SID (works on localized Windows too).
# Users can also create C:\ProgramData\netcap before the install and own it, so an existing folder is taken over:
# Administrators own it and everything in it, and nothing in it keeps entries of its own (#89).
param([switch]$WithDownload)
$ErrorActionPreference = 'Stop'

$p = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  [Console]::Error.WriteLine('run as Administrator'); exit 1
}

$Src = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dir = 'C:\ProgramData\netcap'
$Wd = Join-Path $Dir 'windivert'
$WdUrl = 'https://github.com/basil00/WinDivert/releases/download/v2.2.2/WinDivert-2.2.2-A.zip'
$WdZip = '63cb41763bb4b20f600b6de04e991a9c2be73279e317d4d82f237b150c5f3f15'
$WdFiles = [ordered]@{
  'x64/WinDivert.dll'   = 'c1e060ee19444a259b2162f8af0f3fe8c4428a1c6f694dce20de194ac8d7d9a2'
  'x64/WinDivert64.sys' = '8da085332782708d8767bcace5327a6ec7283c17cfb85e40b03cd2323a90ddc2'
  'LICENSE'             = '14a0cb5214d536e4fdae6aa3f5696f981eeda106cd026e9794bba489ee79d628'
}

function Sha256($bytes) { -join ([Security.Cryptography.SHA256]::Create().ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) }

# The files in place match their pins (an earlier install fetched them, and nobody changed them since)
function WinDivert-InPlace {
  foreach ($e in $WdFiles.GetEnumerator()) {
    $f = Join-Path $Wd (Split-Path -Leaf $e.Key)
    if (-not (Test-Path -LiteralPath $f) -or (Sha256 ([IO.File]::ReadAllBytes($f))) -ne $e.Value) { return $false }
  }
  $true
}

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

# Everything that can fail with -WithDownload happens before anything here changes
$zip = $null
if ($WithDownload) {
  # The machine's architecture, not this process's (an x64 PowerShell on ARM64 says AMD64)
  $arch = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment').PROCESSOR_ARCHITECTURE
  if ($arch -ne 'AMD64') {
    [Console]::Error.WriteLine("-WithDownload needs x64 Windows: WinDivert has no signed driver for $arch. Nothing was changed")
    exit 1
  }
  if (-not (WinDivert-InPlace)) {
    try {
      [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
      $bytes = (New-Object Net.WebClient).DownloadData($WdUrl)
    } catch {
      [Console]::Error.WriteLine("could not fetch WinDivert from $WdUrl ($($_.Exception.Message)). Nothing was changed")
      exit 1
    }
    $got = Sha256 $bytes
    if ($got -ne $WdZip) {
      [Console]::Error.WriteLine("refused $WdUrl`: its SHA-256 is $got, not the pinned $WdZip. Nothing was changed")
      exit 1
    }
    Add-Type -AssemblyName System.IO.Compression
    $zip = New-Object IO.Compression.ZipArchive (New-Object IO.MemoryStream (, $bytes))
  }
}

New-Item -ItemType Directory -Force $Dir | Out-Null
Lock-Entry $Dir -Top
foreach ($f in 'netshape.ps1', 'netshape-down.ps1', 'netcap-agent.ps1', 'netcap-check.ps1', 'uninstall.ps1') {
  Copy-Item -Force (Join-Path $Src $f) (Join-Path $Dir $f)
  Lock-Entry (Join-Path $Dir $f)  # a new file is owned by whoever ran this; make it Administrators
}

if ($zip) {
  & (Join-Path $Dir 'netshape.ps1') stop-download | Out-Null  # a file in use cannot be replaced
  New-Item -ItemType Directory -Force $Wd | Out-Null
  foreach ($e in $WdFiles.GetEnumerator()) {
    $entry = $zip.GetEntry("WinDivert-2.2.2-A/$($e.Key)")
    $in = $entry.Open(); $out = [IO.File]::Create((Join-Path $Wd (Split-Path -Leaf $e.Key)))
    try { $in.CopyTo($out) } finally { $out.Close(); $in.Close() }
  }
  Lock-Entry $Wd
  'fetched WinDivert 2.2.2 (SHA-256 verified) into ' + $Wd
} elseif ($WithDownload) {
  'WinDivert 2.2.2 is in place (SHA-256 verified)'
} elseif (Test-Path -LiteralPath $Wd) {
  # Installed without -WithDownload: back to upload only
  & (Join-Path $Dir 'netshape.ps1') stop-download | Out-Null
  Remove-Item -Recurse -Force -LiteralPath $Wd
  'removed WinDivert: download is no longer capped here (install with --with-download to keep it)'
}

'installed (boot=keep: the on / off state survives reboots' + $(if ($WithDownload) { '; download capped with WinDivert)' } else { ')' })
& (Join-Path $Dir 'netshape.ps1') get
& (Join-Path $Dir 'netshape.ps1') status | Select-Object -First 1
