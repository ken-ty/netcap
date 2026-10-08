# Platforms

English · [日本語](platforms.ja.md)

What each OS supports. ✅ supported · ⚠️ with a limit · ❌ not supported · ❓ not verified

## As a capped device

| Feature | macOS | Linux | Windows |
| --- | --- | --- | --- |
| How it caps | pf + dummynet | tc (HTB, ingress through ifb) | NetQosPolicy; download with WinDivert ([why](adr/0001-cap-download-on-windows.md)) |
| Upload cap | ✅ | ✅ | ✅ |
| Download cap | ✅ | ✅ | ⚠️ installed with `--with-download`, x64 only ([how](design.md#download-on-windows-windivert)); otherwise ❌ (shown as `unsupported`) |
| `status` reads the real state | ⚠️ download shows the value recorded at `on`, marked `*` ([why](design.md#the--on-macos-download-in-status)) | ✅ | ✅ |
| After a reboot (`boot`) | `off` (default) or `on` | `off` (default) or `on` | `keep` only: the state survives reboots ([why](design.md#windows-keeps-its-state-across-reboots)) |
| `check` (measure up / down + ping) | ✅ | ✅ | ✅ |
| `on --for` (the device lifts the cap by itself) | ✅ | ✅ (needs systemd) | ✅ |
| LAN and VPN (IPv4 private, 100.64/10) pass through | ✅ | ✅ | ✅ |
| DNS passes through | ✅ | ✅ | ✅ |
| ICMP (ping) passes through | ✅ | ✅ | ✅ (measured, IPv4) |
| IPv6 (LAN, ICMPv6, and DNS pass) | ✅ (measured) | ✅ (measured) | ✅ (upload measured; download's filter checked in CI) |
| Gates | forced command + sudoers per verb | forced command + sudoers per verb | forced command only |
| `netcap install` on this machine | ✅ (sudo) | ✅ (sudo) | ✅ (as Administrator) |
| `netcap install --ssh` from a controller | ✅ | ✅ | ✅ (the ssh user must be an Administrator) |

The exempt ranges are in [design.md](design.md#destinations-that-pass-through). The IPv6 row for Linux is measured in CI.
On macOS and Windows, IPv6 to the LAN was measured on real machines on 2026-10-01: 2 MB over link-local took 8.1 s
(macOS at 2 Mbit/s) and 17.1 s (Windows at 1 Mbit/s) with the rules of 0.10.0, and 0.14 s with these.
On macOS, IPv6 to the internet was measured on 2026-10-04 over a phone's tethering: at a 1/1 Mbit/s cap, IPv6 download
fell from 28.7 to 0.89 Mbit/s and upload held at 0.62. While that download filled the cap, new TCP connections over IPv6
waited 0.8 to 1.8 s, but ping6 stayed at 31 ms and DNS queries over IPv6 at 26 to 52 ms, as without a cap.
On Windows, measured on 2026-10-06 on the same tethering: at a 1/1 cap, IPv6 upload fell from 11.3 to 0.92 Mbit/s. While
that upload filled the cap, new TCP connections over IPv6 took 1.0 to 1.3 s, but ping6 stayed at 18 to 61 ms and DNS over
IPv6 at 30 to 38 ms, as without a cap: nothing names ICMPv6, yet the throttling policy does not hold it back.

## As a controller (the CLI)

| Feature | macOS | Linux | Windows |
| --- | --- | --- | --- |
| `status` `get` `on` `off` `set` `check` `use` `profiles` | ✅ | ✅ | ✅ |
| `install` / `uninstall` / `rename` for this machine | ✅ | ✅ | ✅ |
| `install --ssh`, and `uninstall` of a device reached over ssh | ✅ | ✅ | ✅ |
| `doctor` | ✅ | ✅ | ✅ |
| `protect` | ✅ | ✅ | ❓ |
| `export` / `import` | ✅ | ✅ | ✅ |
| Install with brew | ✅ | ✅ (Homebrew on Linux) | ❌ (curl or zip, see [host-setup.md](host-setup.md#where-the-scripts-are)) |
| Help and errors in Japanese under a Japanese locale | ✅ | ✅ | ⚠️ English unless `LANG` / `LC_ALL` is set |
| Shell completion (`completion`) | ✅ bash, zsh | ✅ bash, zsh | ⚠️ bash and zsh only (no PowerShell) |

The CLI needs only Python 3 and the OpenSSH client.

CI tests `--ssh` (install, the forced command, `doctor`, `on` / `off`, and uninstall) from Linux to Linux and from Windows
to Windows by connecting each runner to itself through a real sshd (`tests/test_e2e_ssh.py`). On Windows it runs twice: with sshd's default shell (`cmd.exe`) and with PowerShell.
The same test, run by hand from a Windows 11 controller to a macOS 26.3 device on 2026-10-01, showed install, the forced
command, `doctor`, `on` / `off`, and uninstall working. It needs 0.11.0 or later, which sends the device side
with LF from a Windows git clone (#65). macOS to Windows is in daily use.
