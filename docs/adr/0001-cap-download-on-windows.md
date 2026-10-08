# ADR 0001: Cap download on Windows with WinDivert

English · [日本語](0001-cap-download-on-windows.ja.md)

- Status: Accepted
- Date: 2026-10-09
- Decided by: Ken, in [#108](https://github.com/ken-ty/netcap/issues/108)

## Context

[vision.md](../vision.md) promises upload and download caps on all three OS. Windows capped upload only: NetQosPolicy
throttles what the machine sends, and Windows has no built-in way to cap a whole machine's download (checked up to
Windows 11 25H2). The gap had been accepted as "download on Windows needs a driver, beyond netcap's size". #108 reopened it.

## Options

Where the download is held back:

| | Where | Windows side | Caps download |
| --- | --- | --- | --- |
| 1 | Inside Windows: a kernel driver holds inbound packets back | a signed driver, and a process that runs while capped | yes |
| 2 | Outside Windows: another device on the LAN is its exit and caps it there (a Tailscale exit node, or the default gateway with NAT) | a route or `tailscale set --exit-node`; nothing installed | yes |
| 3 | Built-ins and apps: TCP receive window, link speed, per-app limits (Steam, OneDrive, BITS) | settings only | no: per connection or per app, not a cap |

**Option 1.** Option 2 breaks "enforced on each device" and stops working when the exit device is down. Option 3 is not a
cap; it can only help alongside 1 or 2.

Writing our own driver (a WFP callout or an NDIS filter) means EV signing and kernel maintenance, which stays out of scope.
So the driver is borrowed:

| | WinDivert | Windows Packet Filter (ndisapi) |
| --- | --- | --- |
| Driver | WFP-based | NDIS lightweight filter |
| License | LGPL v3 or GPL v2 | library MIT; the driver free for personal, education, and non-profit use, $3,000 to redistribute in a product |
| Maintenance | last release 2.2.2 (2022-09-21) | commits in 2025 |
| ARM64 | no signed build | yes |
| Used by | mitmproxy (through pydivert), GoodbyeDPI, zapret, Suricata, clumsy | few open-source projects |

**WinDivert**, for its adoption. Each project above has far more users than netcap. Those users put pressure on WinDivert
to be fixed or succeeded, and netcap rides on that rather than on a driver few others use. Windows Packet Filter is better
maintained, but that pressure is missing.

## Decision

- **On demand, with confirmation** (decided 2026-10-09, after the first CI run): nothing installs WinDivert without an
  answer. `netcap on` run from a terminal asks, for a Windows device that has not decided, before installing it:
  "Capping download on <host> needs WinDivert (a third-party kernel driver, LGPL). Install it now? [y/N]". `--yes` and
  `netcap install <name> --with-download` install it without asking. Without a terminal, with `--json` or `-q`, and in
  `use` and `protect`, which touch many devices, nothing is asked: the device is capped on upload only, as before, and
  named. ARM64 Windows is refused
- **Declining in advance**: `netcap install <name> --without-download` removes WinDivert and records the refusal on the
  device (`download.declined`), so every controller sees the same answer and `on` stops asking; `--with-download` clears
  it. `netcap get` shows the choice. An install without either flag keeps it
- **Fetched, not shipped**: the installer downloads the official 2.2.2 release over HTTPS, refuses it unless its SHA-256
  matches the pin, and keeps only the x64 `WinDivert.dll`, `WinDivert64.sys`, and `LICENSE`, in
  `C:\ProgramData\netcap\windivert` with the same ACL as the rest of netcap. netcap's repository and formula contain no
  WinDivert binary
- **The shaper is a script**: `netshape-down.ps1` compiles a small C# class with `Add-Type` that calls WinDivert.dll. It
  takes inbound packets with the same exemptions as upload (LAN, VPN, loopback, link-local, multicast; DNS; ICMP and
  ICMPv6), sends them on at the rate with a token bucket, and drops beyond a 50-packet queue, as the download pipe on
  macOS does. It runs as SYSTEM from the scheduled task `\netcap\download`, started at `on` and at startup while the cap is
  on, and ended at `off` and by the `on --for` deadline. A rate change goes through a file the shaper reads; the handle stays open
- **Around WinDivert's known bugs**: the shaper waits while the service is starting or stopping and retries the open
  with a backoff instead of racing a driver that is loading
  ([basil00/WinDivert#408](https://github.com/basil00/WinDivert/issues/408))
- **The driver stays loaded until reboot by default**: `off` only closes netcap's handle. WinDivert does not unload the
  driver when the last handle closes, and netcap does not stop its service, because stopping it while any handle is open
  makes later opens fail with 1058 ([basil00/WinDivert#406](https://github.com/basil00/WinDivert/issues/406)) and netcap
  cannot see every program that may hold one. A loaded driver with no handle holds nothing back: CI measures that `off`
  lifts the cap while the driver stays loaded (on the 2026-10-09 run: 842 Mbit/s without a cap, 0.95 at a 1 Mbit/s cap, 826 after `off`, with the service still running), and that 20 `on` / `off` cycles each cap and each end the
  shaper (20 cycles in 206 s; 0.95 Mbit/s after the last `on`, 849 after the last `off`)
- **`unload-driver` as a low-level command**: `netcap unload-driver <host>` stops the service on request, listed only by
  `netcap help --all`, as git lists its plumbing. The device refuses while a download cap is on or while any process has
  WinDivert.dll loaded. It is not the default because those checks cannot see a program that talks to the driver
  without the DLL, and because #406 leaves the driver unusable until reboot when a check misses one

## License

netcap fetches WinDivert at install time and does not distribute it. Users receive it from upstream under LGPL v3 (or
GPL v2, their choice), with its license file next to it. netcap calls the unmodified DLL at run time and stays MIT.

## Consequences

Accepted with this choice (none has a CVE):

- [LOLDrivers](https://www.loldrivers.io/) lists WinDivert 2.2 as malicious (2024-09): attackers bring it in to mute
  security products. Malwarebytes flags it, and Bitdefender has quarantined it
  ([basil00/WinDivert#395](https://github.com/basil00/WinDivert/issues/395))
- Its signing certificate expired in 2023. The signature is timestamped, so Windows still loads it (GitHub's Windows
  Server 2022 and 2025 runners did), but some security software blocks it
  ([basil00/WinDivert#397](https://github.com/basil00/WinDivert/issues/397),
  [basil00/WinDivert#401](https://github.com/basil00/WinDivert/issues/401))
- Open crash bugs: a 0xD1 bugcheck when the device is opened while the driver is still loading
  ([basil00/WinDivert#408](https://github.com/basil00/WinDivert/issues/408), the root cause of
  [basil00/WinDivert#330](https://github.com/basil00/WinDivert/issues/330)), and frequent bugchecks reported after a BIOS
  update ([basil00/WinDivert#398](https://github.com/basil00/WinDivert/issues/398))
- No ARM64 build: it compiles, but nobody can sign it ([basil00/WinDivert#236](https://github.com/basil00/WinDivert/issues/236),
  [basil00/WinDivert#379](https://github.com/basil00/WinDivert/issues/379))
- The last release is from 2022; the author says it is active and feature-complete
  ([basil00/WinDivert#395](https://github.com/basil00/WinDivert/issues/395))
- The driver stays loaded after `off`, until the next reboot: WinDivert does not unload it when the last handle closes, and
  netcap does not stop its service. On GitHub's runners the service stayed running, marked for deletion, after `off` and
  after uninstall; its `.sys` cannot be deleted until then, so uninstall leaves that one file to a task at the next
  startup. A device that never turns a download cap on never loads it. Whether anti-cheat software (Vanguard, Easy
  Anti-Cheat, BattlEye) objects is not yet checked
- A device that opts in runs a third-party kernel driver while capped, and security software may report it.
  [SECURITY.md](../../SECURITY.md) says so

## When to revisit

- A successor appears that the projects above move to (a fork, or a new driver the community migrates to): netcap follows
- A Windows update stops WinDivert from loading
- Anti-cheat software or security software makes the opt-in unusable in practice
