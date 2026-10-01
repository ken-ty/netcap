# Platforms

English · [日本語](platforms.ja.md)

What each OS supports. ✅ supported · ⚠️ with a limit · ❌ not supported · ❓ not verified

## As a capped device

| Feature | macOS | Linux | Windows |
| --- | --- | --- | --- |
| How it caps | pf + dummynet | tc (HTB, ingress through ifb) | NetQosPolicy |
| Upload cap | ✅ | ✅ | ✅ |
| Download cap | ✅ | ✅ | ❌ (shown as `unsupported`) |
| `status` reads the real state | ⚠️ download shows the value recorded at `on`, marked `*` ([why](design.md#the--on-macos-download-in-status)) | ✅ | ✅ |
| After a reboot (`boot`) | `off` (default) or `on` | `off` (default) or `on` | `keep` only: the state survives reboots ([why](design.md#windows-keeps-its-state-across-reboots)) |
| `check` (measure up / down + ping) | ✅ | ✅ | ✅ |
| LAN and VPN (IPv4 private, 100.64/10) pass through | ✅ | ✅ | ✅ |
| DNS passes through | ✅ | ✅ | ✅ |
| ICMP (ping) passes through | ✅ | ✅ | ✅ (measured, IPv4) |
| IPv6 (LAN, ICMPv6, and DNS pass) | ✅ (from the rules) | ✅ (measured) | ⚠️ LAN and DNS pass (from the rules); ICMPv6 ❓ |
| Gates | forced command + sudoers per verb | forced command + sudoers per verb | forced command only |
| `netcap install` on this machine | ✅ (sudo) | ✅ (sudo) | ✅ (as Administrator) |
| `netcap install --ssh` from a controller | ✅ | ✅ | ✅ (the ssh user must be an Administrator) |

The exempt ranges are in [design.md](design.md#destinations-that-pass-through). The IPv6 row for Linux is measured in CI;
for macOS and Windows it comes from reading the rules, not from a measurement.

## As a controller (the CLI)

| Feature | macOS | Linux | Windows |
| --- | --- | --- | --- |
| `status` `get` `on` `off` `set` `check` `use` `profiles` | ✅ | ✅ | ✅ |
| `install` / `uninstall` / `rename` for this machine | ✅ | ✅ | ✅ |
| `install` / `uninstall` with `--ssh` to other devices | ✅ | ✅ | ✅ |
| `export` / `import` | ✅ | ✅ | ✅ |
| Install with brew | ✅ | ✅ (Homebrew on Linux) | ❌ (curl or zip, see [host-setup.md](host-setup.md#where-the-scripts-are)) |
| Help and errors in Japanese under a Japanese locale | ✅ | ✅ | ⚠️ English unless `LANG` / `LC_ALL` is set |

The CLI needs only Python 3 and the OpenSSH client.

CI tests `--ssh` from Linux to Linux and from Windows to Windows by connecting each runner to itself through a real sshd
(`tests/test_e2e_ssh.py`). On Windows it runs twice: with sshd's default shell (`cmd.exe`) and with PowerShell.
The same test, run by hand from a Windows 11 controller to a macOS 26.3 device on 2026-10-01, showed install, the forced
command, `doctor`, `on` / `off`, and uninstall working. It needs a version after 0.10.0, which sends the device side
with LF from a Windows git clone (#65). macOS to Windows is in daily use.
