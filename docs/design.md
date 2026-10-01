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
end up measuring the shaper's queue. Windows excludes only DNS explicitly: NetQosPolicy cannot match ICMP. Measured on
Windows 11 the way `test_36_icmp_passes_on_windows` in `tests/test_e2e.py` does, the throttling policy does not hold ICMP back either
(IPv4 only, since GitHub's Windows runners cannot send ICMP to the internet).

Only the inside of a VPN tunnel passes through via 100.64/10. The outer UDP that goes out to the internet is capped.

IPv6 is treated the same way: the IPv6 ranges in the table, ICMPv6, and DNS pass through. On Linux this is measured in CI
(`PassThrough` in `tests/test_e2e.py`); on macOS and Windows it comes from the rules. On Windows, as with ICMP, nothing
names ICMPv6, and it has not been measured there.

One exception on Linux: an ICMPv6 message too large for one packet is capped. tc reads the protocol from the IPv6
header, which names the fragment header when the message is split. Pings of the usual size are not split.

## Where the root-owned parts live

Binaries that can become root without a password live where every parent directory is writable only by root.
If a user could write to the directory, replacing the file would be enough to get root (on a Mac that has
used Homebrew, `/usr/local/sbin` can be like that).

- macOS: binaries in `/Library/PrivilegedHelperTools`, settings in `/etc`. `install.sh` checks owner and
  permissions all the way up to `/`. Settings are not sourced; they are read as numeric key=value pairs
- Linux: binaries in `/usr/libexec/netcap`, settings in `/etc`. Checked the same way as macOS
- Windows: Users can write to `C:\ProgramData`, so `install.ps1` breaks inheritance

## pf and dnctl: touch only our own

- Rules are loaded into the anchor `com.apple/netcap-netshape`; `/etc/pf.conf` is never replaced
- `off` flushes the anchor and deletes only pipes 1 / 2. Enabling pf is counted with the `pfctl -E` token, and only our own reference is released

Pipe numbers are shared by the whole machine, so netcap cannot be used together with tools that use pipes 1 / 2, such as Network Link Conditioner.

## tc: touch only our own qdisc (Linux)

- The root qdisc of the default route's interface is replaced with our own HTB (handle `ca9:`); `off` deletes it and restores the default.
  If another tool already put a qdisc at the root, netcap stops instead of replacing it
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
