# netshape-down.ps1 — caps this Windows machine's download from the internet, with WinDivert (docs/adr/0001)
#
#   netshape-down.ps1          run the shaper until download.mbit is removed. netshape.ps1 starts it at on, as SYSTEM,
#                              from the scheduled task \netcap\download (also at startup while the cap is on)
#   netshape-down.ps1 filter   print the WinDivert filter (for tests)
#
# Only there with netcap install <name> --with-download, which fetches WinDivert into C:\ProgramData\netcap\windivert.
# NetQosPolicy caps only what this machine sends, so upload stays with netshape.ps1; this script holds back what arrives:
#   - a WinDivert handle takes inbound packets from the internet. Not loopback, not the ranges in $Local (LAN, VPN,
#     link-local, multicast; the same as netshape.ps1), not to a multicast or broadcast address, not DNS (port 53),
#     not ICMP / ICMPv6
#   - they wait in a queue and are sent on (WinDivertSend) at the rate in download.mbit: a token bucket that may
#     run 50 ms ahead
#   - a packet that arrives while 50 are waiting is dropped, as the download pipe on macOS does (queue 50)
#   - download.mbit is read again when it changes, so on and set change the rate without reopening the handle
#   - when download.mbit is gone (off), the handle is closed and the script ends
# While the handle is open, download.state says "pid=<pid> mbit=<rate>"; download.log keeps what went wrong.
#
# WinDivert issues it works around:
#   - It never stops the WinDivert service. Stopping it while a handle is open makes later opens fail with 1058
#     (basil00/WinDivert#406). Closing the handle is all off does; Windows keeps the driver loaded until reboot
#   - It waits while the service is starting or stopping, and retries WinDivertOpen with a backoff instead of racing
#     a driver that is still loading (basil00/WinDivert#408)
$ErrorActionPreference = 'Stop'

$Dir = 'C:\ProgramData\netcap'
$Wd = Join-Path $Dir 'windivert'
$RateFile = Join-Path $Dir 'download.mbit'
$StateFile = Join-Path $Dir 'download.state'
$Log = Join-Path $Dir 'download.log'
$Local = '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '100.64.0.0/10', '127.0.0.0/8', '169.254.0.0/16', '224.0.0.0/4',
         'fc00::/7', '::1/128', 'fe80::/10', 'ff00::/8'
$C = [Globalization.CultureInfo]::InvariantCulture

# First and last address of a prefix, as WinDivert's filter language writes them
function Bounds([string]$prefix) {
  $a, $bits = $prefix -split '/'
  $lo = ([Net.IPAddress]::Parse($a)).GetAddressBytes(); $hi = $lo.Clone()
  for ($i = [int]$bits; $i -lt $lo.Length * 8; $i++) {
    $k = [Math]::Floor($i / 8); $m = 0x80 -shr ($i % 8)
    $lo[$k] = [byte]($lo[$k] -band (0xFF -bxor $m)); $hi[$k] = [byte]($hi[$k] -bor $m)
  }
  ([Net.IPAddress]::new($lo)).ToString(), ([Net.IPAddress]::new($hi)).ToString()
}

# A field of another protocol fails any test on it, negated or not, so each family and port test sits behind a ?:
function Get-Filter {
  $v4 = @(); $v6 = @()
  foreach ($p in $Local) {
    $lo, $hi = Bounds $p
    if ($p.Contains(':')) { $v6 += "(ipv6.SrcAddr < $lo or ipv6.SrcAddr > $hi)" }
    else { $v4 += "(ip.SrcAddr < $lo or ip.SrcAddr > $hi)" }
  }
  # Spaces around ? and :, so that neither is read as part of a number or an IPv6 address
  "inbound and !loopback and !impostor and !icmp and !icmpv6" +
  " and (tcp ? tcp.SrcPort != 53 : true) and (udp ? udp.SrcPort != 53 : true)" +
  " and (ip ? ip.DstAddr < 224.0.0.0 and $($v4 -join ' and ') : (ipv6 ? ipv6.DstAddr < ff00:: and $($v6 -join ' and ') : false))"
}

if ($args.Count -eq 1 -and $args[0] -eq 'filter') { Get-Filter; exit 0 }
if ($args.Count -ne 0) { [Console]::Error.WriteLine('usage: netshape-down.ps1 [filter]'); exit 2 }

function Say([string]$m) { [IO.File]::AppendAllText($Log, "$([DateTime]::UtcNow.ToString('s', $C))Z $m`r`n") }

function Read-Rate {
  # The rate in Mbit/s, or $null when the file is gone or not a positive number
  try { $v = "$([IO.File]::ReadAllText($RateFile))".Trim() } catch { return $null }
  if ($v -notmatch '^[0-9]+([.][0-9]+)?$' -or [double]::Parse($v, $C) -le 0) { return $null }
  [double]::Parse($v, $C)
}

# Add-Type compiles in TEMP. As SYSTEM that is C:\Windows\Temp, where Users can create files: compile in our own folder
$env:TEMP = $env:TMP = Join-Path $Dir 'tmp'
New-Item -ItemType Directory -Force $env:TEMP | Out-Null

Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;

public static class NetcapDown {
  [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)] static extern IntPtr LoadLibraryW(string path);
  [DllImport("winmm.dll")] static extern uint timeBeginPeriod(uint ms);
  [DllImport("WinDivert.dll", SetLastError = true, CharSet = CharSet.Ansi)] static extern IntPtr WinDivertOpen(string filter, int layer, short priority, ulong flags);
  [DllImport("WinDivert.dll", SetLastError = true)] static extern bool WinDivertRecv(IntPtr h, byte[] packet, uint len, out uint got, byte[] addr);
  [DllImport("WinDivert.dll", SetLastError = true)] static extern bool WinDivertSend(IntPtr h, byte[] packet, uint len, out uint sent, byte[] addr);
  [DllImport("WinDivert.dll", SetLastError = true)] static extern bool WinDivertShutdown(IntPtr h, int how);
  [DllImport("WinDivert.dll", SetLastError = true)] static extern bool WinDivertClose(IntPtr h);

  public const int Limit = 50;          // packets waiting, as macOS's download pipe (queue 50)
  const double Burst = 0.05;            // seconds the bucket may run ahead
  const int AddrSize = 80;              // sizeof(WINDIVERT_ADDRESS)

  class Item { public byte[] Packet; public uint Length; public byte[] Addr; }

  static IntPtr handle = new IntPtr(-1);
  static readonly object gate = new object();
  static readonly Queue<Item> queue = new Queue<Item>();
  static double rate;                   // bytes per second
  static volatile bool stopping;
  static Thread receiver, sender;
  public static long Received, Sent, Dropped;
  public static string Error;

  public static void Load(string dll) {
    // By full path: the DllImports above then bind to this copy, never one found on the search path
    if (LoadLibraryW(dll) == IntPtr.Zero) throw new Exception("could not load " + dll + " (" + Marshal.GetLastWin32Error() + ")");
    timeBeginPeriod(1);
  }

  public static int Open(string filter) {
    handle = WinDivertOpen(filter, 0, 0, 0);
    return handle == new IntPtr(-1) ? Marshal.GetLastWin32Error() : 0;
  }

  public static void SetRate(double bytesPerSecond) { lock (gate) { rate = bytesPerSecond; Monitor.PulseAll(gate); } }

  public static bool Running { get { return receiver.IsAlive && sender.IsAlive; } }

  public static void Start() {
    receiver = new Thread(Receive); receiver.IsBackground = true; receiver.Start();
    sender = new Thread(Send); sender.IsBackground = true; sender.Priority = ThreadPriority.AboveNormal; sender.Start();
  }

  static void Receive() {
    var buf = new byte[65535];
    while (!stopping) {
      var it = new Item { Addr = new byte[AddrSize] };
      if (!WinDivertRecv(handle, buf, (uint)buf.Length, out it.Length, it.Addr)) {
        if (!stopping) Error = "WinDivertRecv failed (" + Marshal.GetLastWin32Error() + ")";
        return;
      }
      it.Packet = new byte[it.Length];
      Buffer.BlockCopy(buf, 0, it.Packet, 0, (int)it.Length);
      lock (gate) {
        Received++;
        if (queue.Count >= Limit) { Dropped++; continue; }
        queue.Enqueue(it);
        Monitor.Pulse(gate);
      }
    }
  }

  static void Send() {
    double tokens = 0;
    long last = Stopwatch.GetTimestamp();
    while (!stopping) {
      Item it = null;
      int wait;
      lock (gate) {
        while (queue.Count == 0 && !stopping) Monitor.Wait(gate, 500);
        long now = Stopwatch.GetTimestamp();
        tokens = Math.Min(rate * Burst, tokens + (now - last) * rate / Stopwatch.Frequency);
        last = now;
        // A packet goes as soon as the bucket is not in debt, so one larger than the bucket still goes
        if (tokens >= 0 && queue.Count > 0) { it = queue.Dequeue(); tokens -= it.Length; }
        wait = it != null || rate <= 0 ? 0 : (int)Math.Ceiling(-tokens / rate * 1000);
      }
      if (it == null) { Thread.Sleep(Math.Max(1, wait)); continue; }
      uint sent;
      if (WinDivertSend(handle, it.Packet, it.Length, out sent, it.Addr)) Interlocked.Increment(ref Sent);
    }
  }

  public static void Close() {
    stopping = true;
    lock (gate) Monitor.PulseAll(gate);
    if (handle != new IntPtr(-1)) { WinDivertShutdown(handle, 3); WinDivertClose(handle); }
    handle = new IntPtr(-1);
  }
}
'@

Remove-Item -Force $StateFile -ErrorAction SilentlyContinue
[IO.File]::WriteAllText($Log, '')
$opened = $false
try {
  $mbit = Read-Rate
  if ($null -eq $mbit) { Say 'download.mbit is missing or not a number: nothing to cap'; exit 0 }
  [NetcapDown]::Load((Join-Path $Wd 'WinDivert.dll'))
  [Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'High'
  $filter = Get-Filter
  # Up to about a minute: the service may be in the middle of starting or stopping (another program, or boot)
  for ($try = 1; ; $try++) {
    for ($i = 0; $i -lt 20 -and (Get-Service WinDivert -ErrorAction SilentlyContinue).Status -in 'StartPending', 'StopPending'; $i++) {
      Start-Sleep -Milliseconds 500
    }
    $rc = [NetcapDown]::Open($filter)
    if ($rc -eq 0) { break }
    Say "WinDivertOpen failed ($rc), try $try"
    # 87: the filter itself is wrong; trying again will not help
    if ($rc -eq 87 -or $try -ge 6) { exit 1 }
    Start-Sleep -Seconds ([Math]::Min(16, [Math]::Pow(2, $try - 1)))
  }
  $opened = $true
  [NetcapDown]::SetRate($mbit * 1000000 / 8)
  [NetcapDown]::Start()
  [IO.File]::WriteAllText($StateFile, "pid=$PID mbit=$($mbit.ToString('G', $C))")
  Say "capping download at $($mbit.ToString('G', $C)) Mbit/s"
  $seen = [IO.File]::GetLastWriteTimeUtc($RateFile)
  while ($true) {
    Start-Sleep -Seconds 1
    if (-not [NetcapDown]::Running) { Say ([NetcapDown]::Error); exit 1 }
    if (-not (Test-Path $RateFile)) { Say 'download.mbit removed: closing'; break }
    $t = [IO.File]::GetLastWriteTimeUtc($RateFile)
    if ($t -ne $seen) {
      $seen = $t
      $new = Read-Rate
      if ($null -ne $new -and $new -ne $mbit) {
        $mbit = $new
        [NetcapDown]::SetRate($mbit * 1000000 / 8)
        [IO.File]::WriteAllText($StateFile, "pid=$PID mbit=$($mbit.ToString('G', $C))")
        Say "rate changed to $($mbit.ToString('G', $C)) Mbit/s"
      }
    }
  }
}
catch { Say "$_"; exit 1 }
finally {
  if ($opened) { [NetcapDown]::Close() }
  Remove-Item -Force $StateFile -ErrorAction SilentlyContinue
}
