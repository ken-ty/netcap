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
| ICMP (ping) passes through | ✅ | ✅ | ❓ |
| IPv6 | ⚠️ capped toward the LAN too; ICMPv6 and DNS pass | ⚠️ all IPv6 is capped, LAN, ICMPv6, and DNS included | ⚠️ capped toward the LAN too; DNS passes |
| Gates | forced command + sudoers per verb | forced command + sudoers per verb | forced command only |
| `netcap install` on this machine | ✅ (sudo) | ✅ (sudo) | ✅ (as Administrator) |
| `netcap install --ssh` from a controller | ✅ | ⚠️ tested with a fake ssh only | ✅ (the ssh user must be an Administrator) |

The exempt ranges are in [design.md](design.md#destinations-that-pass-through). The IPv6 rows for macOS and Windows
come from reading the rules (only IPv4 ranges are exempt), not from a measurement.

## As a controller (the CLI)

| Feature | macOS | Linux | Windows |
| --- | --- | --- | --- |
| `status` `get` `on` `off` `set` `check` `use` `profiles` | ✅ | ✅ | ✅ |
| `install` / `uninstall` / `rename` for this machine | ✅ | ✅ | ✅ |
| `install` / `uninstall` with `--ssh` to other devices | ✅ | ❓ | ❓ |
| `export` / `import` | ✅ | ✅ | ✅ |
| Install with brew | ✅ | ❓ (Homebrew on Linux, not tested) | ❌ (curl or zip, see [host-setup.md](host-setup.md#where-the-scripts-are)) |
| Help and errors in Japanese under a Japanese locale | ✅ | ✅ | ⚠️ English unless `LANG` / `LC_ALL` is set |

The CLI needs only Python 3 and the OpenSSH client.
