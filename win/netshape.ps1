# netshape.ps1 — caps this Windows machine's own WAN traffic (NetQosPolicy; download with WinDivert when installed)
#
#   netshape.ps1 on [UP_MBIT DOWN_MBIT]  apply the cap. With arguments, use those values this time only
#   netshape.ps1 off                     remove the cap
#   netshape.ps1 status                  current state. Line 1 is derived from the actual NetQosPolicy objects
#   netshape.ps1 set UP_MBIT DOWN_MBIT   change the defaults. Reapplies the cap if one is in effect
#   netshape.ps1 get                     defaults and boot behavior on one line
#   netshape.ps1 unload-driver           unload the WinDivert driver now instead of at the next reboot (refused while in use)
#
# Differences from the mac version (pf + dummynet):
#   - Windows QoS policies act only on the sending side, so they cap upload. Download is capped only on a device
#     installed with --with-download (install.ps1 -WithDownload), which fetches WinDivert: on starts netshape-down.ps1
#     as SYSTEM from the scheduled task \netcap\download, also at startup while the cap is on, and off stops it.
#     status returns down_src=windivert and shaper=running|stopped|none there. Elsewhere DOWN_MBIT is accepted but
#     unused, and status returns down_src=unsupported (docs/adr/0001-cap-download-on-windows.md). get and status say
#     download=enabled|declined|unset: declined is install.ps1 -WithoutDownload, so that netcap on stops offering it
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
$Local = '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '100.64.0.0/10', '127.0.0.0/8', '169.254.0.0/16', '224.0.0.0/4',
         'fc00::/7', '::1/128', 'fe80::/10', 'ff00::/8'

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

# --- download (WinDivert). Present only after install.ps1 -WithDownload
$Wd = Join-Path $Dir 'windivert'
$DownRate = Join-Path $Dir 'download.mbit'
$DownState = Join-Path $Dir 'download.state'
$DownLog = Join-Path $Dir 'download.log'
$System = New-ScheduledTaskPrincipal -UserId 'S-1-5-18' -LogonType ServiceAccount -RunLevel Highest

function Can-Down { Test-Path -LiteralPath (Join-Path $Wd 'WinDivert.dll') }
function Download-Choice {
  if (Can-Down) { 'enabled' } elseif (Test-Path -LiteralPath (Join-Path $Dir 'download.declined')) { 'declined' } else { 'unset' }
}
function Down-Task { Get-ScheduledTask -TaskPath '\netcap\' -TaskName download -ErrorAction SilentlyContinue }

# The running shaper as @{pid; mbit}, or $null: download.state names a process that is still there
function Shaper {
  if (-not (Test-Path $DownState)) { return $null }
  $s = @{}
  foreach ($kv in "$(Get-Content -Raw $DownState)".Trim() -split '\s+') { $k, $v = $kv -split '=', 2; $s[$k] = $v }
  if ($s['pid'] -notmatch '^[0-9]+$' -or -not (Get-Process -Id ([int]$s['pid']) -ErrorAction SilentlyContinue)) { return $null }
  $s
}

function Last-DownLog { if (Test-Path $DownLog) { @(Get-Content $DownLog | Where-Object { $_ })[-1] } }

function Start-Down([string]$mbit) {
  $tmp = "$DownRate.tmp"
  [IO.File]::WriteAllText($tmp, $mbit)
  Move-Item -Force $tmp $DownRate
  if (-not (Down-Task)) {
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
      -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $Dir 'netshape-down.ps1')`""
    # No time limit (the default stops a task after 3 days), not stopped on battery, one instance
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
      -ExecutionTimeLimit ([TimeSpan]::Zero)
    Register-ScheduledTask -TaskPath '\netcap\' -TaskName download -Action $action -Trigger (New-ScheduledTaskTrigger -AtStartup) `
      -Settings $settings -Principal $System -Force | Out-Null
  }
  # A shaper already running reads the new rate within a second; otherwise start one and wait for its handle
  if (-not (Shaper)) { Start-ScheduledTask -TaskPath '\netcap\' -TaskName download }
  $want = ([double]::Parse($mbit, [Globalization.CultureInfo]::InvariantCulture)).ToString('G', [Globalization.CultureInfo]::InvariantCulture)
  for ($i = 0; $i -lt 120; $i++) {
    $s = Shaper
    if ($s -and $s['mbit'] -eq $want) { return }
    # Gone without a handle: it wrote why
    if ($i -ge 4 -and -not $s -and (Down-Task).State -ne 'Running') { break }
    Start-Sleep -Milliseconds 500
  }
  throw "the download shaper did not start: $(Last-DownLog) (see $DownLog)"
}

# Never stops the WinDivert service (basil00/WinDivert#406): the shaper closes its handle and ends, and Windows
# keeps the driver loaded until reboot
function Stop-Down {
  Remove-Item -Force $DownRate -ErrorAction SilentlyContinue
  for ($i = 0; $i -lt 10 -and (Shaper); $i++) { Start-Sleep -Milliseconds 500 }  # it checks once a second
  if (Down-Task) {
    Stop-ScheduledTask -TaskPath '\netcap\' -TaskName download -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskPath '\netcap\' -TaskName download -Confirm:$false
  }
  Remove-Item -Force $DownState -ErrorAction SilentlyContinue
}

function Remove-Ours {
  foreach ($q in Ours) { Remove-NetQosPolicy -Name $q.Name -Confirm:$false }
}

function Apply([string[]]$a) {
  if ($a.Count -ne 0) {
    if ($a.Count -ne 2 -or -not (IsNumber $a[0]) -or -not (IsNumber $a[1])) { Usage 'on [UP_MBIT DOWN_MBIT] [--for SECONDS]' }
    $script:UpMbit = $a[0]; $script:DownMbit = $a[1]
  }
  Remove-Ours
  $bps = [uint64]([double]$UpMbit * 1000000)
  New-NetQosPolicy -Name netcap-wan -Default -ThrottleRateActionBitsPerSecond $bps | Out-Null
  for ($i = 0; $i -lt $Local.Count; $i++) {
    New-NetQosPolicy -Name "netcap-local-$i" -IPDstPrefixMatchCondition $Local[$i] -DSCPAction 0 | Out-Null
  }
  New-NetQosPolicy -Name netcap-dns -IPDstPortMatchCondition 53 -DSCPAction 0 | Out-Null
  if (Can-Down) { Start-Down $DownMbit; "netshape ON  up=${UpMbit}Mbit/s down=${DownMbit}Mbit/s" }
  else { "netshape ON  up=${UpMbit}Mbit/s down=unsupported" }
}

# on --for: the deadline (epoch seconds) and a one-time task that runs expire as SYSTEM. The cap survives reboots
# here (boot=keep), so the task also runs at startup, and StartWhenAvailable runs a start missed while the machine
# was off or asleep; it needs an end boundary to do that. Without AllowStartIfOnBatteries a laptop on battery
# would never run it
$Until = Join-Path $Dir 'until'

function Now { [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() }

function Read-Until {
  # Get-Content -Raw returns $null for an empty file (a write cut short): no deadline, not an error
  if (Test-Path $Until) { $u = "$(Get-Content -Raw $Until)".Trim(); if ($u -match '^[0-9]+$') { return [int64]$u } }
  return $null
}

function Stop-Timer {
  Remove-Item -Force $Until -ErrorAction SilentlyContinue
  # When the deadline lifts the cap, this runs inside the task itself: keep it last
  Unregister-ScheduledTask -TaskPath '\netcap\' -TaskName expire -Confirm:$false -ErrorAction SilentlyContinue
}

function Start-Timer([int64]$s) {
  $at = [DateTimeOffset]::UtcNow.AddSeconds($s)
  [IO.File]::WriteAllText($Until, [string]$at.ToUnixTimeSeconds())
  $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $Dir 'netshape.ps1')`" expire"
  $once = New-ScheduledTaskTrigger -Once -At $at.LocalDateTime
  $once.StartBoundary = $at.UtcDateTime.ToString('yyyy-MM-ddTHH:mm:ssZ')
  $once.EndBoundary = $at.UtcDateTime.AddDays(1).ToString('yyyy-MM-ddTHH:mm:ssZ')
  $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
  Register-ScheduledTask -TaskPath '\netcap\' -TaskName expire -Action $action -Trigger $once, (New-ScheduledTaskTrigger -AtStartup) `
    -Settings $settings -Principal $System -Force | Out-Null
}

function On([string[]]$a) {
  $for = $null
  if ($a.Count -ge 2 -and $a[-2] -eq '--for') {
    $for = $a[-1]
    if ($for -notmatch '^[0-9]+$' -or [int64]$for -lt 60 -or [int64]$for -gt 86400) {
      [Console]::Error.WriteLine("--for takes seconds, 60 to 86400: $for"); exit 2
    }
    $a = @($a | Select-Object -First ($a.Count - 2))
  }
  try { Apply $a } catch {
    if ($for) { Off | Out-Null }  # never leave a cap that was meant to end
    [Console]::Error.WriteLine("$_"); exit 1
  }
  if (-not $for) { Stop-Timer; return }
  try { Start-Timer ([int64]$for) } catch {
    # Never leave a cap that was meant to end
    Off | Out-Null
    [Console]::Error.WriteLine("could not start the timer for --for; lifted the cap: $_"); exit 3
  }
}

function Off {
  Remove-Ours
  Stop-Down
  'netshape OFF'
  Stop-Timer
}

function Expire {
  $u = Read-Until
  if ($null -eq $u) { Stop-Timer } elseif ((Now) -ge $u) { Off }
}

# until=<epoch> left=<seconds> while --for is pending, else -
function Timer-Fields {
  $u = Read-Until
  if ($null -eq $u) { return 'until=- left=-' }
  "until=$u left=$([Math]::Max(0, $u - (Now)))"
}

function Status {
  $ours = Ours
  $wan = $ours | Where-Object Name -eq 'netcap-wan'
  $expected = $Local.Count + 2
  $up = '-'
  # A machine reads this: not the current culture's format (0,5 under de-DE)
  if ($wan) { $up = ($wan.ThrottleRate / 1000000).ToString('G', [Globalization.CultureInfo]::InvariantCulture) }
  $on = $wan -and $ours.Count -eq $expected
  $off = $ours.Count -eq 0
  $down = "down_mbit=- down_src=unsupported"
  if (Can-Down) {
    # Download is on when the task is registered and its shaper holds the handle; a task without a running shaper
    # (it could not open WinDivert, or it has not started yet after boot) is partial
    $task = Down-Task; $s = Shaper
    $on = $on -and $task -and $s
    $off = $off -and -not $task -and -not $s
    $mbit = if ($s) { $s['mbit'] } else { '-' }
    $shaper = if ($s) { 'running' } elseif ($task) { 'stopped' } else { 'none' }
    $down = "down_mbit=$mbit down_src=windivert shaper=$shaper"
  }
  if ($on) { $state = 'on' }
  elseif ($off) { $state = 'off' }
  else { $state = 'partial' }  # only some are left. Run on or off again
  "netshape state=$state up_mbit=$up $down download=$(Download-Choice) policies=$($ours.Count) $(Timer-Fields)"
  '--- policies (netcap-*)'
  if ($ours.Count -eq 0) { '(none)' }
  foreach ($q in $ours) { "$($q.Name) template=$($q.Template) throttle=$($q.ThrottleRate) dst=$($q.IPDstPrefixMatchCondition) port=$($q.IPDstPortStartMatchCondition)" }
  if (Can-Down) {
    '--- download (WinDivert)'
    "task=$(if ($task) { $task.State } else { 'none' }) shaper_pid=$(if ($s) { $s['pid'] } else { '-' }) driver=$((Get-Service WinDivert -ErrorAction SilentlyContinue).Status)"
    "log: $(Last-DownLog)"
  }
}

function Get-Default {
  $c = if (Test-Path $Conf) { $Conf } else { 'none' }
  "netshape default_up=$UpMbit default_down=$DownMbit boot=keep conf=$c download=$(Download-Choice)"
}

function Set-Default([string[]]$a) {
  if ($a.Count -ne 2 -or -not (IsNumber $a[0]) -or -not (IsNumber $a[1])) { Usage 'set UP_MBIT DOWN_MBIT' }
  $tmp = "$Conf.tmp"
  "# netshape.ps1 defaults. Written by netshape.ps1 set`r`nUP_MBIT=$($a[0])`r`nDOWN_MBIT=$($a[1])" | Set-Content -Path $tmp -Encoding ASCII
  Move-Item -Force $tmp $Conf
  if (Ours | Where-Object Name -eq 'netcap-wan') {
    try { Apply $a | Out-Null } catch { [Console]::Error.WriteLine("$_"); exit 1 }  # keeps a pending --for
    "netshape SET up=$($a[0])Mbit/s down=$($a[1])Mbit/s (reapplied, since a cap was in effect)"
  } else {
    "netshape SET up=$($a[0])Mbit/s down=$($a[1])Mbit/s (takes effect at the next on)"
  }
}

# unload-driver: netcap never stops the WinDivert service on its own (basil00/WinDivert#406: stopping it under an open
# handle makes later opens fail with 1058), so the driver stays loaded until reboot. This low-level verb unloads it now,
# only when nothing can hold a handle: not while a download cap is on, and not while another process has WinDivert.dll
# loaded (32-bit ones included). A program that talks to the driver without the DLL is not seen
function Unload-Driver {
  if ((Shaper) -or (Down-Task)) { [Console]::Error.WriteLine('netshape: a download cap is on here; run off first'); exit 1 }
  $svc = Get-Service WinDivert -ErrorAction SilentlyContinue
  if (-not $svc -or $svc.Status -eq 'Stopped') { 'netshape driver=unloaded (it was not loaded)'; return }
  Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class NetcapModules {
  [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
  [DllImport("psapi.dll")] static extern bool EnumProcessModulesEx(IntPtr h, IntPtr[] mods, int cb, out int needed, uint filter);
  [DllImport("psapi.dll", CharSet = CharSet.Unicode)] static extern uint GetModuleBaseNameW(IntPtr h, IntPtr mod, StringBuilder name, int size);
  // LIST_MODULES_ALL (3): a 32-bit process's modules too, which Process.Modules leaves out from a 64-bit PowerShell
  public static bool Has(int pid, string dll) {
    IntPtr h = OpenProcess(0x0410, false, pid);  // PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
    if (h == IntPtr.Zero) return false;
    try {
      var mods = new IntPtr[2048]; int needed;
      if (!EnumProcessModulesEx(h, mods, mods.Length * IntPtr.Size, out needed, 3)) return false;
      var name = new StringBuilder(260);
      for (int i = 0; i < Math.Min(mods.Length, needed / IntPtr.Size); i++) {
        name.Length = 0;
        if (GetModuleBaseNameW(h, mods[i], name, name.Capacity) > 0 &&
            string.Equals(name.ToString(), dll, StringComparison.OrdinalIgnoreCase)) return true;
      }
      return false;
    } finally { CloseHandle(h); }
  }
}
'@
  $users = @(foreach ($p in Get-Process) { if ($p.Id -ne $PID -and [NetcapModules]::Has($p.Id, 'WinDivert.dll')) { "$($p.ProcessName) ($($p.Id))" } })
  if ($users.Count) {
    [Console]::Error.WriteLine("netshape: WinDivert is in use by $($users -join ', '); unloading it now would break their handles")
    exit 1
  }
  & sc.exe stop WinDivert | Out-Null
  # WinDivert marked the service for deletion, so once it stops it is gone
  for ($i = 0; $i -lt 20; $i++) {
    $svc = Get-Service WinDivert -ErrorAction SilentlyContinue
    if (-not $svc -or $svc.Status -eq 'Stopped') { 'netshape driver=unloaded'; return }
    Start-Sleep -Milliseconds 500
  }
  [Console]::Error.WriteLine("netshape: the WinDivert driver did not stop ($($svc.Status))"); exit 1
}

$verb = if ($args.Count -gt 0) { $args[0] } else { '' }
$rest = @($args | Select-Object -Skip 1)
switch ($verb) {
  'on' { On $rest }
  'off' { Off }
  'expire' { Expire }
  'stop-download' { Stop-Down }  # install.ps1, before it removes WinDivert
  'status' { Status }
  'set' { Set-Default $rest }
  'get' { Get-Default }
  'unload-driver' { Unload-Driver }
  default { Usage '{on [UP_MBIT DOWN_MBIT] [--for SECONDS]|off|status|set UP_MBIT DOWN_MBIT|get|unload-driver}' }
}
