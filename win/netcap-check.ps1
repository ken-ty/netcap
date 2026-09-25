# netcap-check.ps1 — measures WAN download and upload from this device, pinging 1.1.1.1 meanwhile
#
#   netcap-check.ps1 [--bytes N]
#
# Prints the same single line (netcheck key=value …) as the mac netcap-check. No Administrator needed.
# Transfers use the built-in curl.exe; pings come from a job running Test-Connection every 0.5 s.
$ErrorActionPreference = 'Stop'

$Bytes = 1000000
$PingHost = '1.1.1.1'
if ($args.Count -gt 0) {
  if ($args.Count -ne 2 -or $args[0] -ne '--bytes' -or $args[1] -notmatch '^[0-9]+$') {
    [Console]::Error.WriteLine('usage: netcap-check.ps1 [--bytes N]'); exit 2
  }
  $Bytes = [int]$args[1]
}

$tmp = Join-Path $env:TEMP ("netcap-check-" + [guid]::NewGuid())
New-Item -ItemType Directory $tmp | Out-Null
try {
  $upFile = Join-Path $tmp 'up.bin'
  $buf = New-Object byte[] $Bytes
  (New-Object Random).NextBytes($buf)
  [IO.File]::WriteAllBytes($upFile, $buf)
  $stop = Join-Path $tmp 'stop'

  # We want the latency during the transfers, so pings run alongside them
  $job = Start-Job -ArgumentList $PingHost, $stop {
    param($h, $stop)
    while (-not (Test-Path $stop)) {
      try { (Test-Connection -ComputerName $h -Count 1 -ErrorAction Stop).ResponseTime } catch {}
      Start-Sleep -Milliseconds 500
    }
  }
  Start-Sleep -Seconds 1
  $down = & curl.exe -s -o NUL -w '%{speed_download}' "https://speed.cloudflare.com/__down?bytes=$Bytes"
  $up = & curl.exe -s -o NUL -w '%{speed_upload}' -X POST --data-binary "@$upFile" https://speed.cloudflare.com/__up
  New-Item -ItemType File $stop | Out-Null
  $pings = @(Receive-Job -Wait -AutoRemoveJob $job | ForEach-Object { [double]$_ } | Sort-Object)

  $n = $pings.Count
  if ($n -eq 0) { $med = '-'; $p95 = '-'; $max = '-' }
  else {
    $med = '{0:F1}' -f $pings[[int][math]::Floor(($n + 1) / 2) - 1]
    $i95 = [int][math]::Floor($n * 0.95); if ($i95 -lt 1) { $i95 = 1 }
    $p95 = '{0:F1}' -f $pings[$i95 - 1]
    $max = '{0:F1}' -f $pings[$n - 1]
  }
  $c = [Globalization.CultureInfo]::InvariantCulture
  $d = ([double]$down * 8 / 1000000).ToString('F2', $c)
  $u = ([double]$up * 8 / 1000000).ToString('F2', $c)
  "netcheck down_mbit=$d up_mbit=$u ping_med=$med ping_p95=$p95 ping_max=$max ping_n=$n bytes=$Bytes"
}
finally {
  Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
