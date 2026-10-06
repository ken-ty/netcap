# Changelog

What changed in each release, for people who use netcap. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Before 1.0.0, a minor release may break things;
each such change starts with **Breaking**.

How to keep this file: [CONTRIBUTING.md](CONTRIBUTING.md#changelog).

## [Unreleased]

### Fixed

- On macOS, a cap with a decimal or a leading zero was not applied: `0.5` and `08` left the line unlimited and `010`
  capped at 8 Mbit/s, while `status` showed the value asked for. The shaper now hands dummynet whole bit/s, and
  refuses a value it cannot hold (above 2147.483647 Mbit/s) before changing anything (#96)

### Security

- The agent refuses `check --bytes` outside 1 to 100000000 (100 MB), so a key allowed only `status get check` can no
  longer make a device transfer as much as it asks; `netcap check --bytes` says so before sending. This narrows what
  the agent accepts, but the CLI never sends what it refuses, so the oldest agent the CLI works with does not change.
  Update each device with `netcap install <name>` to get the limit there (#98)
- On Windows, `install.ps1` takes over an existing `C:\ProgramData\netcap`: Administrators now own the folder and
  everything in it, and entries someone else added to it or to files in it are removed. Before, a standard user who
  created the folder before the install could still change the scripts that run as Administrator. A link in the
  folder is refused. Run `win\install.ps1` (or `netcap install`) again to apply this to an existing install (#99)

## [0.12.0] - 2026-10-06

### Added

- `netcap help [<command>|exit-codes]`, `netcap version`, `-q` / `--quiet` (before or after the command), and
  `netcap completion bash|zsh`, which also completes the names in hosts (#82)

### Changed

- When the only failures are devices out of reach (ssh could not connect, or timed out), netcap exits with 3 instead
  of 1, so a script can try again later. docs/operations.md lists the exit codes (#82)

### Fixed

- `status` said `off in 0m` for a cap whose `--for` deadline had passed but that the device had not lifted yet;
  it now says `due, lifting soon` (#80)

## [0.11.0] - 2026-10-02

### Added

- `netcap protect <host> [--up N --down N]` caps every other device and shows `<host>`'s check before and after;
  `netcap protect --off` puts each device back as it was. With `--load MB` the others load the line meanwhile,
  and the result says whether latency on `<host>` improved (#73, #77)
- `netcap on <host> --for 30m` (or `2h`, `1h30m`; 1 minute to 24 hours): the device lifts the cap by itself after that
  long, even with the controller off. `status` shows the time left. It needs the agent from this release on each device:
  run `netcap install <name>` (#71, #72)

### Changed

- **Breaking** `netcap uninstall <name>` removes only this controller's key and, on macOS / Linux, its ssh user from the
  device's sudoers. The agent stays while another controller's netcap key is on the device, and goes with the last one.
  To remove everything at once, run the device's `uninstall.sh` (Windows: `uninstall.ps1`) (#70)
- Installing on a macOS or Linux device as another ssh user adds that user to its sudoers instead of replacing the
  previous one, so each controller may log in as its own user. Update the CLI on every controller first: 0.10.0 and
  earlier still replace the list. `uninstall.sh --user` removes one user (#68)

### Fixed

- IPv6 is treated like IPv4: LAN (`fc00::/7`, `fe80::/10`), loopback, multicast, ICMPv6, and DNS pass through the cap.
  Before, Linux capped all IPv6, and macOS and Windows capped IPv6 toward the LAN. Run `netcap install <name>` and then
  `netcap on <name>` again to apply it; a Windows device left capped shows `partial` until then (#67)
- `netcap install --ssh` from a Windows controller running from a git clone failed on macOS and Linux devices:
  the clone had CRLF line endings, which bash on the device cannot read. The device side now goes out with LF (#65)
- The Quick Start adds `brew trust ken-ty/netcap`: Homebrew 7 refuses to load a formula from a tap you have not
  trusted, so `brew install netcap` failed (#60)
- On a Windows device whose sshd uses its default shell (`cmd.exe`), every request was denied: `cmd.exe` split the
  verbs after `--allow` in the netcap key's line. Run `netcap install <name>` to update the agent there (#59)

## [0.10.0] - 2026-10-01

### Added

- `-v` (`--verbose`) prints what the table leaves out, one block per device after the table, and the whole output
  of a device that failed. `-vv` also prints the raw output of every device. `netcap doctor -v` also shows the
  options on the netcap key's line, and this controller's version, config directory, and key. Its `--json` gains `options` (#54)
- This CHANGELOG (#53)

### Changed

- **Breaking** `-v` means `--verbose`, as in ssh, curl, and flutter. The version is `-V` or `--version` (#54)

### Removed

- **Breaking** `--raw`. Use `-vv` (#54)

## [0.9.1] - 2026-10-01

### Added

- [docs/compatibility.md](docs/compatibility.md): which agent versions each CLI release works with (#51)

### Fixed

- `netcap install` and `uninstall` remove the temporary directory on the device when scp fails (#47)
- A failure to create the temporary directory on Windows is reported instead of crashing with IndexError (#49)

## [0.9.0] - 2026-10-01

### Added

- `netcap doctor` finds devices where the netcap key has no forced command (#41)
- [SECURITY.md](SECURITY.md): the threat model and how to report a vulnerability (#40)

### Fixed

- Linux: `on` waits up to 3 seconds for the default route instead of failing while systemd-networkd restarts (#43)

### Security

- **Breaking** ssh offers only the netcap key. Before, ssh-agent's keys went first, and a device that trusted
  the user's own key ran the request in a normal shell, outside the forced command. A device added to `hosts`
  by hand now needs `netcap install` (#39)

## [0.8.0] - 2026-09-28

### Added

- `netcap export` and `netcap import`: hosts and profiles as JSON, with no keys (#27)
- Docs: [why](docs/why.md) (#33), [vision](docs/vision.md) (#33), [platforms](docs/platforms.md) (#26),
  and [operations](docs/operations.md) (#25)

### Changed

- The agents refuse a cap of 0 too, not only the CLI (#25)

## [0.7.1] - 2026-09-25

### Fixed

- `netcap install` from brew writes the version into the agents, instead of leaving it at "unknown"

## [0.7.0] - 2026-09-25

### Added

- `netcap install`, `uninstall`, and `rename` (#19)
- `netcap on` prints how to undo it

### Changed

- The Quick Start starts on your own line, with `netcap install` (#20)

### Fixed

- A cap of 0 is an error and changes nothing. dummynet on macOS read 0 as unlimited, the opposite of what was
  asked. Use `off` to lift a cap

## [0.6.0] - 2026-09-25

### Added

- Linux as a capped device, up and down (tc) (#12)
- Help and errors in Japanese under a Japanese locale

### Changed

- English is the source of truth for the docs and the CLI output; Japanese is a translation

## [0.5.0] - 2026-09-25

### Added

- `netcap --version` (`-v`) (#10)

## [0.4.0] - 2026-09-25

### Added

- Windows as a capped device, upload only (NetQosPolicy) (#8)
- The MIT license (#7)

## [0.3.0] - 2026-09-25

### Added

- A Homebrew formula: this repository is its own tap (#3)

### Changed

- **Breaking** Devices and profiles live in `~/.config/netcap/` (#4)
- **Breaking** Commands reach devices through `netcap-agent`, and each device's forced command decides what is
  allowed (#5)

## [0.2.0] - 2026-09-25

### Security

- The shaper lives where only root can write, and touches only its own pf anchor and pipes (#1)

## [0.1.0] - 2026-09-23

### Added

- The `netcap` CLI, with verbs shaped after tailscale's, and the macOS shaper (pf + dummynet)

[Unreleased]: https://github.com/ken-ty/netcap/compare/v0.12.0...HEAD
[0.12.0]: https://github.com/ken-ty/netcap/compare/v0.11.0...v0.12.0
[0.11.0]: https://github.com/ken-ty/netcap/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/ken-ty/netcap/compare/v0.9.1...v0.10.0
[0.9.1]: https://github.com/ken-ty/netcap/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/ken-ty/netcap/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/ken-ty/netcap/compare/v0.7.1...v0.8.0
[0.7.1]: https://github.com/ken-ty/netcap/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/ken-ty/netcap/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/ken-ty/netcap/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/ken-ty/netcap/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/ken-ty/netcap/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/ken-ty/netcap/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/ken-ty/netcap/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ken-ty/netcap/releases/tag/v0.1.0
