# Spike for #108: can GitHub's Windows runner load WinDivert, open a handle from PowerShell (Add-Type), and reinject?
$ErrorActionPreference = 'Stop'
$url = 'https://github.com/basil00/WinDivert/releases/download/v2.2.2/WinDivert-2.2.2-A.zip'
$sha = '63cb41763bb4b20f600b6de04e991a9c2be73279e317d4d82f237b150c5f3f15'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$bytes = (New-Object Net.WebClient).DownloadData($url)
$h = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($bytes)).Replace('-', '').ToLower()
"zip sha256 $h ($($bytes.Length) bytes)"
if ($h -ne $sha) { throw 'hash mismatch' }
Add-Type -AssemblyName System.IO.Compression
$zip = New-Object IO.Compression.ZipArchive (New-Object IO.MemoryStream (, $bytes))
$d = Join-Path $env:RUNNER_TEMP 'windivert'
New-Item -ItemType Directory -Force $d | Out-Null
foreach ($n in 'x64/WinDivert.dll', 'x64/WinDivert64.sys', 'LICENSE') {
  $e = $zip.GetEntry("WinDivert-2.2.2-A/$n")
  $s = $e.Open(); $f = [IO.File]::Create((Join-Path $d (Split-Path -Leaf $n))); $s.CopyTo($f); $f.Close(); $s.Close()
}
Get-ChildItem $d | Format-Table Name, Length -AutoSize | Out-String
try { Get-AuthenticodeSignature (Join-Path $d 'WinDivert64.sys') | Format-List Status, StatusMessage, SignerCertificate | Out-String } catch { "signature: $_" }
"os: $((Get-CimInstance Win32_OperatingSystem).Caption) $([Environment]::OSVersion.Version)"
try { "device guard: $((Get-CimInstance -Namespace root\Microsoft\Windows\DeviceGuard -ClassName Win32_DeviceGuard).SecurityServicesRunning -join ',')" } catch { "device guard: $_" }

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Threading;
public static class Spike {
  [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)] static extern IntPtr LoadLibraryW(string path);
  [DllImport("WinDivert.dll", SetLastError = true, CharSet = CharSet.Ansi)] static extern IntPtr WinDivertOpen(string filter, int layer, short priority, ulong flags);
  [DllImport("WinDivert.dll", SetLastError = true)] static extern bool WinDivertRecv(IntPtr h, byte[] packet, uint len, out uint got, byte[] addr);
  [DllImport("WinDivert.dll", SetLastError = true)] static extern bool WinDivertSend(IntPtr h, byte[] packet, uint len, out uint sent, byte[] addr);
  [DllImport("WinDivert.dll", SetLastError = true)] static extern bool WinDivertShutdown(IntPtr h, int how);
  [DllImport("WinDivert.dll", SetLastError = true)] static extern bool WinDivertClose(IntPtr h);
  static IntPtr handle;
  public static long Packets, Bytes, SendErrors;
  public static int LastError;
  static Thread worker;
  public static void Load(string path) { if (LoadLibraryW(path) == IntPtr.Zero) throw new Exception("LoadLibrary " + Marshal.GetLastWin32Error()); }
  public static int Open(string filter) {
    handle = WinDivertOpen(filter, 0, 0, 0);
    if (handle == new IntPtr(-1)) return Marshal.GetLastWin32Error();
    return 0;
  }
  // Reinject everything; with bytesPerSec > 0 hold each packet back so the average stays at that rate
  public static void Start(double bytesPerSec) {
    worker = new Thread(() => {
      var buf = new byte[65535]; var addr = new byte[80];
      var t0 = DateTime.UtcNow;
      while (true) {
        uint got, sent;
        if (!WinDivertRecv(handle, buf, (uint)buf.Length, out got, addr)) { LastError = Marshal.GetLastWin32Error(); return; }
        Packets++; Bytes += got;
        if (bytesPerSec > 0) {
          double due = Bytes / bytesPerSec - (DateTime.UtcNow - t0).TotalSeconds;
          if (due > 0) Thread.Sleep((int)(due * 1000));
        }
        if (!WinDivertSend(handle, buf, got, out sent, addr)) SendErrors++;
      }
    });
    worker.IsBackground = true;
    worker.Start();
  }
  public static void Stop() { WinDivertShutdown(handle, 3); worker.Join(5000); WinDivertClose(handle); }
}
'@

function Drv { "service: $((sc.exe query WinDivert) -join ' | ')" }
function Down([int]$n) {
  $s = & curl.exe -s -o NUL -w '%{speed_download}' "https://speed.cloudflare.com/__down?bytes=$n"
  ([double]$s * 8 / 1000000).ToString('F2', [Globalization.CultureInfo]::InvariantCulture)
}

Drv
[Spike]::Load((Join-Path $d 'WinDivert.dll'))
"no shaper: down $(Down 20000000) Mbit/s"
$t = Get-Date
$rc = [Spike]::Open('inbound and !loopback and !impostor and tcp')
"open: rc=$rc in $([int]((Get-Date) - $t).TotalMilliseconds) ms"
if ($rc -ne 0) { Drv; exit 1 }
Drv
[Spike]::Start(0)
"reinject only: down $(Down 20000000) Mbit/s, packets=$([Spike]::Packets) bytes=$([Spike]::Bytes) send_errors=$([Spike]::SendErrors)"
[Spike]::Stop()
"closed (recv error after shutdown: $([Spike]::LastError))"
Drv
Start-Sleep 5
"5 s after close:"; Drv
try { "driver: $((Get-CimInstance Win32_SystemDriver -Filter "Name='WinDivert'" | ForEach-Object { "$($_.State) $($_.StartMode) $($_.PathName)" }))" } catch { "driver: $_" }

# Open again (off then on) and hold back to 2 Mbit/s
[Spike]::Packets = 0; [Spike]::Bytes = 0
$rc = [Spike]::Open('inbound and !loopback and !impostor and tcp')
"reopen: rc=$rc"
if ($rc -ne 0) { Drv; exit 1 }
[Spike]::Start(250000)
"held to 2 Mbit/s: down $(Down 2000000) Mbit/s, packets=$([Spike]::Packets) send_errors=$([Spike]::SendErrors)"
[Spike]::Stop()
"closed again"
Start-Sleep 5
Drv
"after: down $(Down 20000000) Mbit/s"
