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

A CLI that caps the internet bandwidth of every device on your network, from one device, with one command.
Works where the router has no QoS: the cap is enforced on each device itself.

<p align="center">
  <img src="docs/overview.svg" alt="netcap use game caps laptop and server, leaving the full line to gamepc" width="760">
</p>

- Only internet traffic is capped. Traffic between devices on the same LAN is left alone
- ping (ICMP) and DNS are never capped, so latency measurements stay honest
- Commands reach each device over ssh; what is allowed is decided by that device's `authorized_keys`

## Quick Start

### 1. Install

```bash
brew tap ken-ty/netcap https://github.com/ken-ty/netcap
brew install netcap
netcap install          # sets up this machine; asks for a name (Enter gives "me")
```

`netcap install` asks for your password once (sudo; on Windows, run it as Administrator). Needs only Python 3.
Without brew, see [docs/host-setup.md](docs/host-setup.md).

### 2. Try it on your own line

```bash
netcap on me --up 2 --down 2    # cap this machine to 2 Mbit/s up and down
netcap status                   # read the cap actually in effect
netcap off me                   # remove it
```

> **If you get stuck: `netcap off me` removes the cap.** It runs locally, so it works even when the line is too thin to load anything.
> If netcap itself does not run, call the device side directly:
>
> ```bash
> sudo /Library/PrivilegedHelperTools/netcap-netshape off          # macOS
> sudo /usr/libexec/netcap/netcap-netshape off                      # Linux
> ```
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File C:\ProgramData\netcap\netshape.ps1 off   # Windows, as Administrator
> ```
>
> A reboot also clears the cap on macOS and Linux. Windows keeps it across reboots.

### 3. Manage other devices

Anything you can `ssh` into can be added. Pass its ssh destination (a Host from `~/.ssh/config` works):

```bash
netcap install --ssh gamepc     # installs the agent there; asks for a name (Enter gives "gamepc")
netcap status all
netcap on gamepc --up 5 --down 5
```

It copies the device side over, runs its installer (the device's sudo password, or an Administrator account on Windows),
and registers a netcap-only ssh key that can run nothing but netcap's verbs there.

To move several devices at once, write recipes (profiles) in `~/.config/netcap/profiles`:

```text
# name  device=up/down (Mbit/s) or off
game    me=2/2  gamepc=off
none    me=off  gamepc=off
```

```bash
netcap use game      # apply a recipe to its devices
netcap use none      # remove all caps
```

Rename a device with `netcap rename me laptop`; remove one with `netcap uninstall gamepc`.
For the file format, see [docs/configuration.md](docs/configuration.md); for what install sets up on a device, [docs/host-setup.md](docs/host-setup.md).

## Supported platforms

| Role | macOS | Linux | Windows |
| --- | --- | --- | --- |
| Controller (CLI) | ✅ | ✅ | ✅ |
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
netcap install [name] [--ssh DEST]          install the agent on a device and register it
netcap uninstall <name>                     remove the agent and the registration
netcap rename <old> <new>                   rename a device
netcap --version
```

Help and error messages follow your locale (`LANG`); Japanese is available. `LC_ALL=C netcap -h` shows English.

## Documentation

- [docs/host-setup.md](docs/host-setup.md) — device setup and ssh permissions
- [docs/configuration.md](docs/configuration.md) — config file format
- [docs/design.md](docs/design.md) — design decisions and measurements
- [CONTRIBUTING.md](CONTRIBUTING.md) — development and releases

## License

[MIT](LICENSE)
