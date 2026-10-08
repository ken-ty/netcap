# Security

English · [日本語](SECURITY.ja.md)

## Reporting a vulnerability

Please report it privately: on GitHub, the **Security** tab → **Report a vulnerability**.
If that is not available, open an issue asking for a private contact, and leave the details out of it.

Fixes go into the latest release. To update, `brew upgrade netcap`, then `netcap install <name>` for each device
(add `--boot on` or `--with-download` for a device that had it: reinstalling sets both again).

## Threat model

netcap changes the network settings of several machines from one of them, so it is worth knowing where trust sits.

### The controller is the root of trust

The machine that runs the CLI holds `~/.ssh/netcap`, a key registered on every device by `netcap install`.
It has no passphrase, so that netcap can run unattended (from cron, for example). **Whoever can read that file can
run netcap's verbs on every registered device.** Keep it readable only by you (`ssh-keygen` creates it that way),
and protect the controller as you would protect any machine that can reach all the others.

### What a leaked netcap key allows

The key is pinned to the agent on each device (`restrict,command="… netcap-agent --allow '…'"`), so it runs
the verbs in `--allow` and nothing else: no shell, no pty, no forwarding. With the default verbs, a holder of the key can:

- Read the state and settings of each device (`status`, `get`) and run a measurement (`check`). `check --bytes N` sets how
  much the measurement transfers, and the agent refuses more than 100 MB (`N` from 1 to 100000000)
- Change or lift caps (`on`, `off`, `set`)

**It cannot cut a device off:** `0` is refused on every OS. It can, however, set a very small cap such as
`0.01/0.01`, which makes the device's line unusable until someone runs `netcap off`.

### The gates on each device

| OS | First gate | Second gate |
| --- | --- | --- |
| macOS, Linux | The forced command: only the verbs in `--allow`, numeric arguments only (plus `--for <seconds>` at the end of `on`, and `--bytes` of 1 to 100000000 for `check`) | sudoers: only the shaper's fixed verbs, without a password |
| Windows | The forced command, with the same checks | None. An Administrator's ssh session runs elevated |

On Windows the forced command is the only gate, so a netcap key line added by hand without
`restrict,command="…"` gives an elevated shell. `netcap install` writes the line for you; prefer it over editing by hand.

The files that run as root live only in directories that root alone can write
(`/Library/PrivilegedHelperTools`, `/usr/libexec/netcap`, and on Windows `C:\ProgramData\netcap` with its inheritance cut and Administrators as its owner).
The shaper reads its config as numbers and never runs it as a script. See [docs/design.md](docs/design.md).

### Download capping on Windows is a kernel driver

`netcap install <name> --with-download` puts a third-party kernel driver on that Windows device: WinDivert 2.2.2. Without
the flag, nothing of it is installed. Why it was chosen and what was accepted with it:
[docs/adr/0001-cap-download-on-windows.md](docs/adr/0001-cap-download-on-windows.md).

- netcap does not ship it. The installer fetches the official release zip from GitHub over HTTPS and refuses it unless
  its SHA-256 is the one pinned in `win/install.ps1`; it keeps only the x64 driver, its DLL, and the license, in
  `C:\ProgramData\netcap\windivert` with the same ACL as the rest (only SYSTEM and Administrators can write)
- The driver is loaded by the download shaper, which runs as SYSTEM while a cap is on. After `off` the driver stays loaded
  until the next reboot: netcap never stops its service, because that breaks later opens
  ([basil00/WinDivert#406](https://github.com/basil00/WinDivert/issues/406))
- [LOLDrivers](https://www.loldrivers.io/) lists WinDivert 2.2 as malicious: attackers bring it in to mute security
  products. Security software may report or quarantine it (Malwarebytes and Bitdefender have), and a quarantined driver
  makes `on` fail with the reason in `C:\ProgramData\netcap\download.log`
- Its signing certificate expired in 2023. Windows still loads it because the signature is timestamped, but some security
  software blocks it
- WinDivert can capture and change any packet on the machine. Whoever can replace its files can do the same; that is why
  the folder is writable only by SYSTEM and Administrators, and why reinstalling checks the files against their pins
- x64 only: WinDivert has no signed ARM64 driver

### Out of scope

- A device's own users. netcap caps a device at its owner's request; it is not meant to stop someone with an
  administrator account on that device from lifting the cap
- The ssh setup itself (host keys, sshd configuration, who else can log in). netcap relies on it
