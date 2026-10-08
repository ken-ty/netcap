# Design

English · [日本語](design.ja.md)

## Destinations that pass through

Traffic that does not leave for the internet is never capped.

| Destination | Ranges |
| --- | --- |
| Private IP | 10/8, 172.16/12, 192.168/16, fc00::/7 (IPv6 ULA) |
| CGNAT range (Tailscale and other VPNs) | 100.64/10 |
| Loopback, link-local, multicast | 127/8, 169.254/16, 224/4, ::1/128, fe80::/10, ff00::/8 |

ICMP and DNS (53) are not capped even toward the internet, so that pinging to monitor latency does not
end up measuring the shaper's queue. On Windows, the upload policies exclude only DNS explicitly: NetQosPolicy cannot match
ICMP. (The download shaper excludes ICMP and ICMPv6 by name; see [below](#download-on-windows-windivert).) Measured on
Windows 11 the way `test_36_icmp_passes_on_windows` in `tests/test_e2e.py` does, the throttling policy does not hold ICMP back either
(IPv4 only, since GitHub's Windows runners cannot send ICMP to the internet).

Only the inside of a VPN tunnel passes through via 100.64/10. The outer UDP that goes out to the internet is capped.

IPv6 is treated the same way: the IPv6 ranges in the table, ICMPv6, and DNS pass through. On Linux this is measured in CI
(`PassThrough` in `tests/test_e2e.py`), and on macOS and Windows on real machines with IPv6 to the internet
([platforms.md](platforms.md)). On Windows, as with ICMP, nothing names ICMPv6, but the throttling policy does not hold it
back.

One exception on Linux: an ICMPv6 message too large for one packet is capped. tc reads the protocol from the IPv6
header, which names the fragment header when the message is split. Pings of the usual size are not split.

## Where the root-owned parts live

Binaries that can become root without a password live where every parent directory is writable only by root.
If a user could write to the directory, replacing the file would be enough to get root (on a Mac that has
used Homebrew, `/usr/local/sbin` can be like that).

- macOS: binaries in `/Library/PrivilegedHelperTools`, settings in `/etc`. `install.sh` checks owner and
  permissions all the way up to `/`. Settings are not sourced; they are read as numeric key=value pairs
- Linux: binaries in `/usr/libexec/netcap`, settings in `/etc`. Checked the same way as macOS
- Windows: Users can write to `C:\ProgramData`, so `install.ps1` breaks inheritance. They can also create
  `C:\ProgramData\netcap` before the install, so `install.ps1` makes Administrators the owner of the folder and
  everything in it, leaves only SYSTEM, Administrators, and Users (read) on the folder and nothing of their own on
  what is in it, and refuses a link in it

## pf and dnctl: touch only our own

- Rules are loaded into the anchor `com.apple/netcap-netshape`; `/etc/pf.conf` is never replaced
- `off` flushes the anchor and deletes only pipes 1 / 2. Enabling pf is counted with the `pfctl -E` token, and only our own reference is released
- If something else disables pf (`pfctl -d`), the rules stay loaded but do nothing: `status` shows `partial`, and `on`
  enables pf again with a new token
- At boot, `com.apple.pfctl` may load `/etc/pf.conf` after the boot job (`--boot on`) starts. The job waits up to a
  minute for it; a command you run stops at once

Pipe numbers are shared by the whole machine, so netcap cannot be used together with tools that use pipes 1 / 2, such as Network Link Conditioner.

## tc: touch only our own qdisc (Linux)

- The root qdisc of the interface of the IPv4 route to the internet (`ip -4 route get 1.1.1.1`) is replaced with our own
  HTB (handle `ca9:`); `off` deletes it and restores the kernel's default. netcap stops instead only when another tool has
  put a shaping qdisc at the root (htb, hfsc, cake, tbf, prio, drr, qfq, cbq, or ets). A plain root qdisc, such as the
  default `fq_codel` or `noqueue`, is replaced
- If there is no default route, `on` waits up to 3 seconds for one before it gives up. systemd-networkd on Ubuntu 24.04
  can crash on the first `on` after boot and drop the DHCP routes for a moment while it restarts ([#42](https://github.com/ken-ty/netcap/issues/42))
- Download is capped by redirecting ingress to `ifb-netcap` and shaping it with an HTB there. If another tool has filters on ingress, netcap stops
  (a filter that settles the verdict first would silently keep download from being capped)
- Pass-through destinations, ICMP, and DNS are classified into a class that is not capped. IPv6 has its own filters in
  another prio, since tc keeps one protocol per prio

## The `*` on macOS download in status

On macOS, `dnctl` cannot show the bandwidth of the second pipe (macOS 26). For download, netcap only checks that
the pipe exists, reads the value from what was recorded at `on`, and marks it with `*`.

## Windows keeps its state across reboots

The ActiveStore, which is cleared on reboot, did not keep the destination conditions and capped LAN traffic too.
So the policy is kept in the persistent store.

## Download on Windows (WinDivert)

NetQosPolicy acts only on what the machine sends. On a device that took WinDivert (`netcap on` asks; see
[host-setup.md](host-setup.md#download-on-windows-windivert)), download is capped with it, a signed driver netcap
borrows and fetches when it is installed. Why this driver, and what
it costs: [ADR 0001](adr/0001-cap-download-on-windows.md).

- `netshape-down.ps1` compiles a small C# class with `Add-Type` that calls `WinDivert.dll`; netcap has no compiled
  binary of its own. It runs as SYSTEM from the scheduled task `\netcap\download`, which `on` registers and starts and
  `off` removes. The task also runs at startup, so the download cap survives a reboot like the upload cap (`boot=keep`)
- Its WinDivert filter takes inbound packets from the internet: not loopback, not from the ranges in the table above,
  not to a multicast or broadcast address, not DNS (port 53 at the far end), and not ICMP or ICMPv6. For an inbound
  packet the far end is the source, so the ranges are matched on the source address
- The packets wait in a queue and go on at the rate, by a token bucket that may run 50 ms ahead. A packet that arrives
  while 50 are waiting is dropped, as the download pipe on macOS does (`queue 50`). At 1 Mbit/s a full queue is about
  0.6 s
- `on` and `set` write the rate to `download.mbit`; the running shaper reads it again within a second, so the WinDivert
  handle stays open. `off` (and an `on --for` deadline) removes the file, and the shaper closes its handle and ends
- netcap does not stop the WinDivert service on its own: stopping it while a handle is open makes later opens fail
  ([basil00/WinDivert#406](https://github.com/basil00/WinDivert/issues/406)), and netcap cannot see every program that may
  hold one. The driver stays loaded after `off`, until the next reboot, but holds nothing back: with no handle open it
  passes everything (measured in CI by `test_68`, and over 20 `on` / `off` cycles by `test_69`). `netcap unload-driver`
  stops it on request, after checking that no shaper runs and no process has WinDivert.dll loaded. The shaper waits
  while the service is starting or stopping, and retries the open with a backoff
  ([basil00/WinDivert#408](https://github.com/basil00/WinDivert/issues/408))
- `status` shows `down_src=windivert` and `shaper=running`, `stopped` (the task is registered but its shaper does not hold
  a handle), or `none`. A stopped shaper while the cap should be on makes the state `partial`; `download.log` says why.
  `status` and `get` also show `download=enabled|declined|unset`, the device's choice, which `on` reads before it asks

## How `on --for` lifts a cap

The device keeps the deadline and hands it to the OS scheduler, so it works with the controller off. A later `on` or `off`
cancels it; `set` keeps it. If the timer cannot be started, `on --for` lifts the cap again and fails: a cap meant to end
is never left without its timer. If lifting the cap fails at the deadline, macOS and Linux try again a minute later.

| | Scheduler | After sleep | After a reboot |
| --- | --- | --- | --- |
| macOS | a launchd job, started every minute while it is loaded | runs once on wake | gone, with the cap (unless `boot=on`, which caps without a deadline) |
| Linux | a transient systemd timer on the wall clock | catches up on resume | gone, as on macOS |
| Windows | a one-time task as SYSTEM, also at startup, allowed on battery | runs when the machine is available | kept, with the cap (`boot=keep`) |

Linux needs systemd for `--for`; without it, `on --for` changes nothing.

`use --for` and `protect --for` send the same `on … --for <seconds>` to each device they cap, so each device keeps its
own deadline; the agent is unchanged since 0.11.0.

## Measurements

One macOS device, a 4G-class line, `scripts/measure.sh` (2026-09-21).

| Condition | Down (Mbit/s) | Up (Mbit/s) |
| --- | ---: | ---: |
| off | 18.5–32.8 | 5.2–8.0 |
| on 1/1 | 0.52–0.72 | 0.35–0.85 |
| set 2/3 | 2.04–2.65 | 0.90–1.33 |

Results stay below the cap because the device's other traffic shares the same pipe.

## Origin

On the author's FWA line (a 5G home router), a download on another device pushed League of Legends latency up to 500–1,600 ms.
Powering off the other PCs every time just to play comfortably was absurd.
The router has no QoS, so the cap went onto the devices themselves; capping that device to 1 Mbit/s up and down
brought latency back to a median of 44 ms. That is how netcap was born.
Thanks to it, the gaming PC plays LoL while the server keeps running without interruption,
and another device keeps running Claude.
