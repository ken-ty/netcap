# Vision

English · [日本語](vision.ja.md)

What netcap is for, what it should become, and what it will not do. Changes should move netcap toward this page;
proposals that fall under [Non-goals](#non-goals) are declined. How it compares with other tools: [why.md](why.md).

## The job

**Keep the traffic that matters fast — a game, a call, a stream, line monitoring — on a line without a usable QoS router,
by capping the other computers from one place, safely, and always being able to undo it.**

netcap is Windows Policy-based QoS without the domain: enforced on each computer, across macOS, Linux, and Windows,
with ssh as the only channel. It is not a replacement for router SQM; if you can run SQM, set that up first.

## Principles

- **Enforced on each device, decided by each device.** The controller asks; the device's `authorized_keys` decides what it may ask
- **Only internet traffic is capped.** LAN, VPN, ping, and DNS pass through, so the line stays usable and measurements stay honest
- **Every cap can be undone**, including from the capped machine itself with no network
- **One command per task.** Setting up a device, capping, and undoing are each one command
- **Small.** The CLI is one Python file with the standard library. The device side is scripts: nothing of netcap's runs between
  commands, except the OS running the shaper at boot with `boot=on` and at an `on --for` deadline, and the download
  shaper of a Windows device with WinDivert, which runs while a cap is on
- **Leave to the OS what the OS does.** Recurring schedules are cron, launchd, or Task Scheduler calling netcap; an `on --for`
  deadline is the device's scheduler (launchd, a systemd timer, Task Scheduler); the shaping is pf, tc, and NetQosPolicy,
  and for download on Windows a borrowed driver, WinDivert ([ADR 0001](adr/0001-cap-download-on-windows.md))

## Ideal and current

Open gaps are tracked with the [`vision-gap`](https://github.com/ken-ty/netcap/labels/vision-gap) label.

| Aspect | Ideal | Current | Gap |
| --- | --- | --- | --- |
| Only internet traffic | LAN, VPN, ping, DNS pass through over IPv4 and IPv6 | IPv4 and IPv6 alike; measured on Linux, macOS, and Windows | None |
| Protecting what matters | Name the device to protect; netcap caps the others and shows whether it worked | `netcap protect --load` caps the others, loads the line from them before and after, and says whether the protected device's latency improved | None |
| Undo | A cap cannot be left on by accident | `off` works locally, `on` prints how to undo, `boot` defaults to off; `on --for`, `use --for`, and `protect --for` lift each cap on the device itself | None |
| Platforms | Upload and download on all three OS | Windows caps download with WinDivert, which `on` offers to install (x64; [ADR 0001](adr/0001-cap-download-on-windows.md)); measured in CI | Open: not yet measured on a real device, anti-cheat unchecked, no ARM64 ([#108](https://github.com/ken-ty/netcap/issues/108)) |
| Setup | One command per device | `netcap install`; `--ssh` tested in CI (Linux, Windows) and measured from Windows to macOS | None |
| Several controllers | Any controller works as any ssh user | export / import; sudoers allows each user who installed; uninstall takes back one controller's part | None |
| Device decides | A second gate behind the forced command | sudoers per verb on macOS / Linux; forced command only on Windows | Accepted: no built-in second gate on Windows |
| Visible state | `status` reads the real state | Done; macOS download shows the value recorded at `on` | Accepted: dnctl does not report it |
| Schedules | Cap at night, and so on | cron, launchd, or Task Scheduler call `netcap use` | None: left to the OS |

## Non-goals

| Not netcap's job | Use instead |
| --- | --- |
| Prioritizing traffic, fixing bufferbloat on the line | Router SQM (cake / fq_codel) |
| Phones, consoles, TVs, IoT | Router QoS |
| Per-application limits | NetLimiter (Windows) |
| One process | trickle |
| Simulating delay and packet loss | Network Link Conditioner, browser devtools |
| A Windows driver of netcap's own | Borrow one ([ADR 0001](adr/0001-cap-download-on-windows.md)) |

## Keeping this page true

- A change that closes a gap updates the table in the same PR and closes its issue
- A new gap gets an issue with the `vision-gap` label and a row here
- Changing the job, the principles, or the non-goals is a decision of its own: open an issue first
