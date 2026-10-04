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
- **Small.** The CLI is one Python file with the standard library; the device side is scripts, with nothing running between commands
- **Leave to the OS what the OS does.** Scheduling is cron / launchd; the shaping is pf, tc, and NetQosPolicy

## Ideal and current

Open gaps are tracked with the [`vision-gap`](https://github.com/ken-ty/netcap/labels/vision-gap) label.

| Aspect | Ideal | Current | Gap |
| --- | --- | --- | --- |
| Only internet traffic | LAN, VPN, ping, DNS pass through over IPv4 and IPv6 | IPv4 and IPv6 alike; measured on Linux and macOS, IPv6 to the LAN measured on Windows | Small · [#28](https://github.com/ken-ty/netcap/issues/28) (Windows: IPv6 to the internet and ICMPv6, on a line with IPv6) |
| Protecting what matters | Name the device to protect; netcap caps the others and shows whether it worked | `netcap protect --load` caps the others, loads the line from them before and after, and says whether the protected device's latency improved | None |
| Undo | A cap cannot be left on by accident | `off` works locally, `on` prints how to undo, `boot` defaults to off; `on --for` lifts a cap on the device itself | None |
| Platforms | Upload and download on all three OS | Windows caps upload only | Accepted: download on Windows needs a driver, beyond netcap's size |
| Setup | One command per device | `netcap install`; `--ssh` tested in CI (Linux, Windows) and measured from Windows to macOS | None |
| Several controllers | Any controller works as any ssh user | export / import; sudoers allows each user who installed; uninstall takes back one controller's part | None |
| Device decides | A second gate behind the forced command | sudoers per verb on macOS / Linux; forced command only on Windows | Accepted: no built-in second gate on Windows |
| Visible state | `status` reads the real state | Done; macOS download shows the value recorded at `on` | Accepted: dnctl does not report it |
| Schedules | Cap at night, and so on | cron / launchd call `netcap use` | None: left to the OS |

## Non-goals

| Not netcap's job | Use instead |
| --- | --- |
| Prioritizing traffic, fixing bufferbloat on the line | Router SQM (cake / fq_codel) |
| Phones, consoles, TVs, IoT | Router QoS |
| Per-application limits | NetLimiter (Windows) |
| One process | trickle |
| Simulating delay and packet loss | Network Link Conditioner, browser devtools |
| Download caps on Windows through a custom driver | Out of scope |

## Keeping this page true

- A change that closes a gap updates the table in the same PR and closes its issue
- A new gap gets an issue with the `vision-gap` label and a row here
- Changing the job, the principles, or the non-goals is a decision of its own: open an issue first
