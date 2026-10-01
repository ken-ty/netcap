# Changelog

What changed in each release, for people who use netcap. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Before 1.0.0, a minor release may break things;
each such change starts with **Breaking**.

How to keep this file: [CONTRIBUTING.md](CONTRIBUTING.md#changelog).

## [Unreleased]

### Changed

- Installing on a macOS or Linux device as another ssh user adds that user to its sudoers instead of replacing the
  previous one, so each controller may log in as its own user. Update the CLI on every controller first: 0.10.0 and
  earlier still replace the list. `uninstall.sh --user` removes one user (#68)

### Fixed

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

[Unreleased]: https://github.com/ken-ty/netcap/compare/v0.10.0...HEAD
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
