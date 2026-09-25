<p align="center">
  <img src="docs/logo.svg" alt="netcap" height="72">
</p>

<p align="center">
  <a href="https://github.com/ken-ty/netcap/tags"><img alt="version" src="https://img.shields.io/github/v/tag/ken-ty/netcap?label=version&sort=semver"></a>
  <a href="LICENSE"><img alt="license" src="https://img.shields.io/github/license/ken-ty/netcap"></a>
  <img alt="platform" src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey">
  <img alt="python" src="https://img.shields.io/badge/python-3-blue">
</p>

<p align="center">
  English · <a href="README.ja.md">日本語</a>
</p>

A CLI that caps the internet bandwidth of every device on your network, from one machine, with one command.
Works where the router has no QoS: the cap is enforced on each device itself.

<p align="center">
  <img src="docs/overview.svg" alt="netcap use game caps laptop and server, leaving the full line to gamepc" width="760">
</p>

- Only internet traffic is capped. Traffic between devices on the same LAN is left alone
- ping (ICMP) and DNS are never capped, so latency measurements stay honest
- Commands reach each device over ssh; what is allowed is decided by that device's `authorized_keys`

## Quick Start

1. Install the CLI on the machine you control from (macOS or Linux, needs only Python 3)

   ```bash
   brew tap ken-ty/netcap https://github.com/ken-ty/netcap
   brew install netcap
   ```

2. Install the agent on each device to be capped, as root / Administrator (Windows: see [docs/host-setup.md](docs/host-setup.md))

   ```bash
   sudo bash mac/install.sh --boot off     # macOS
   sudo bash linux/install.sh --boot off   # Linux
   ```

3. Describe your devices and profiles in `~/.config/netcap/` (templates in [examples/](examples/))

   ```text
   # hosts — name  OS  ssh Host (- for this machine)
   laptop   mac  -
   gamepc   win  gamepc

   # profiles — name  device=up/down (Mbit/s) or off
   game    laptop=2/2  gamepc=off
   none    laptop=off  gamepc=off
   ```

4. Use it

   ```bash
   netcap use game      # apply a profile to all devices
   netcap status all    # read the cap actually in effect on each device
   netcap use none      # remove all caps
   ```

## Supported platforms

| Role | macOS | Linux | Windows |
| --- | --- | --- | --- |
| Controller (CLI) | ✅ | ✅ | — |
| Capped device | ✅ up & down (pf + dummynet) | ✅ up & down (tc) | ⚠️ upload only (NetQosPolicy) |

## Use cases

- **Protect latency** — keep other devices' big downloads from choking games or video calls
- **Tame background traffic** — stop OS updates, cloud sync, and backups from eating the whole line
- **Stay within a data cap** — limit each device on mobile or tethered connections
- **Test on a slow network** — see how an app or stream behaves on a thin line, on real hardware
- **Schedule it** — call `netcap use` from cron or launchd, e.g. to cap only at night

## Usage

```text
netcap status [host|all] [--json]           read the cap actually in effect
netcap get    [host|all] [--json]           read the settings (default, boot behavior)
netcap on     <host|all> [--up N --down N]  apply a cap (flags apply this time only)
netcap off    <host|all>                    remove the cap (default returns on reboot)
netcap set    <host|all> --up N --down N    change the default
netcap check  <host|all> [--json]           measure (curl up/down + ping)
netcap use    <profile>                     apply a profile
netcap profiles                             list profiles
netcap --version
```

## Documentation

The detailed docs are in Japanese.

- [docs/host-setup.md](docs/host-setup.md) — device setup and ssh permissions
- [docs/configuration.md](docs/configuration.md) — config file format
- [docs/design.md](docs/design.md) — design decisions and measurements
- [CONTRIBUTING.md](CONTRIBUTING.md) — development and releases

## License

[MIT](LICENSE)
