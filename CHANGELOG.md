# Changelog

What changed in each release, for people who use netcap. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Before 1.0.0, a minor release may break things;
each such change starts with **Breaking**.

How to keep this file: [CONTRIBUTING.md](CONTRIBUTING.md#changelog).

## [Unreleased]

## [0.13.0] - 2026-10-06

### Added

- `netcap protect <host> --for 30m` and `netcap use <profile> --for 30m` (the same times as `on --for`): each device
  they cap lifts the cap by itself after that long, even with the controller off. The table and `--json` show the time
  left. After protect's deadline, `netcap protect --off` puts back each device's cap from before protect, or leaves it
  uncapped if that cap's own `on --for` deadline has passed too; run it after the deadline as well. Agents from 0.11.0
  on support it (#103)

### Changed

- **Breaking** A name in hosts or profiles that breaks the name rule (letters, digits, `_ . -`, starting with a letter
  or digit), such as one written by hand with other characters, now stops netcap with the file and line. Rename it in
  the file (#97)
- `netcap rename` and `netcap uninstall` refuse a device that `netcap protect` capped and has not put back yet. Run
  `netcap protect --off` first (#100)
- **Breaking** Usage errors that netcap finds itself now exit 2, as docs/operations.md says, instead of 1: a bad or
  missing `--up` / `--down`, `--for`, `--bytes`, or `--load`, values given as positional arguments, `protect` without a
  host or with `all`, `uninstall all`, and a new name that breaks the name rule in `rename` and `install`. They are
  checked before anything is read or sent. A script that treats 1 as "bad arguments" should check for 2 (#101)
- `netcap doctor`, `netcap protect` when the protected device is out of reach, and `netcap install --ssh` when ssh
  cannot connect exit 3 instead of 1 when the only failures are devices out of reach (#101)
- **Breaking** A profile name that appears twice in profiles now stops netcap with the file and line, as a name twice in
  hosts does; before, the later line silently won. Remove or rename one of them (#102)

### Fixed

- On macOS, a cap with a decimal or a leading zero was not applied: `0.5` and `08` left the line unlimited and `010`
  capped at 8 Mbit/s, while `status` showed the value asked for. The shaper now hands dummynet whole bit/s, and
  refuses a value it cannot hold (above 2147.483647 Mbit/s) before changing anything (#96)
- `netcap protect --off` deletes its state only when every device is back. A device it could not put back (out of
  reach, failed, or no longer in hosts) stays in the state, and `--off` exits non-zero and says so on stderr; before,
  a failed device stayed capped and a second `--off` said "nothing to undo" (#100)
- `netcap protect` claims its state before measuring, so a second `protect` started meanwhile stops instead of
  overwriting it, and writes the state atomically. With no other device to cap, it says so and writes nothing,
  instead of crashing and leaving an empty state (#100)
- `netcap protect --off` puts a device that had an `on --for` deadline back with the time left, or leaves it uncapped
  if the deadline passed meanwhile; before, the deadline was lost (#100)
- A corrupt `protect.json` stops `protect` and `--off` with its path and what to do, instead of a traceback. With
  `--json`, `protect` and `protect --off` print only JSON on stdout (#100)
- `netcap use` and `netcap protect` report a device that refused or failed the change (`denied`, `no-sudo`, `error`)
  in the table and `--json`, and exit 1 (3 if every failure was out of reach); before, they showed the state read
  afterwards and exited 0. `protect` does not record such a device as capped, so `--off` leaves it as it is (#101)
- `netcap use` checks every value in the profile before sending anything: a bad value no longer leaves the devices
  before it capped (#101)
- `netcap install --ssh` refuses a destination that hosts would refuse, such as `ssh://host:2222`, with exit 2 before
  anything is installed. Before, it installed and registered the device, and then every command stopped on that hosts
  line, `uninstall` included (#102)
- Without a terminal, `netcap install --ssh user@host` names the device `host`; before, it took `user@host`, which the
  name rule refuses (#102)
- hosts, profiles, and a file for `netcap import` that start with a UTF-8 BOM, as Windows PowerShell 5.1 writes them,
  are read correctly (#102)
- Completion finds the command after a global option (`netcap -q on <TAB>`, `netcap --json status <TAB>`), completes
  profile names for `use`, and no longer offers `all` to `protect`, `uninstall`, and `rename`, which refuse it. The
  README says zsh needs `compinit` before the completion script (#102)
- `netcap profiles` shows entries for devices that are not in hosts, and names them; before, it hid them (#102)
- `netcap uninstall` keeps the agent when it cannot read the keys file on the device, and says so; before, it took a
  failed read for "no other controller" and removed an agent another controller may still use (#102)
- Running the CLI from a clone works on Python 3.8, which has no `str.removeprefix` (#102)
- The agent refuses arguments to verbs that take none (`status 5`) instead of passing them to sudo, which netcap showed
  as `no-sudo` (#102)
- On macOS, the boot job of `--boot on` waits up to a minute for `/etc/pf.conf` when it starts before `com.apple.pfctl`
  loads it; before, it failed and left the device uncapped until the next `on`. When something else disables pf
  (`pfctl -d`), `status` says `partial` instead of `on`, and `on` enables pf again. Installing again with `--boot on`
  keeps the cap in effect and its `--for`, as on Linux; before, it applied the default and cancelled the deadline (#102)
- On Linux, `install.sh --boot off` works without systemd (a container, for example), and `--boot on` says it needs
  systemd before changing anything. A failed `expire` at the `--for` deadline is tried again a minute later, instead of
  leaving the cap on (#102)
- On Windows, `status` and `check` print numbers the way the CLI reads them (`0.5`, not `0,5` under de-DE), `status`
  works with an empty deadline file, and `uninstall.ps1` removes links in its folder before deleting the folder, so it
  never deletes what they point to (#102)
- The device-side fixes above need each device updated with `netcap install <name>` (add `--boot on` for a device that
  has it). None of them changes what the CLI sends, so the oldest agent the CLI works with does not change (#102)

### Security

- `netcap import` writes the exporting machine's name into hosts and profiles only if it is a plain name: a newline in
  it added lines that were never checked. The completion script passes only names that follow the name rule to
  `compgen`, which ran a name like `$(…)` in hosts as a command when you pressed TAB (#97)
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

[Unreleased]: https://github.com/ken-ty/netcap/compare/v0.13.0...HEAD
[0.13.0]: https://github.com/ken-ty/netcap/compare/v0.12.0...v0.13.0
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
