# Security

English · [日本語](SECURITY.ja.md)

## Reporting a vulnerability

Please report it privately: on GitHub, the **Security** tab → **Report a vulnerability**.
If that is not available, open an issue asking for a private contact, and leave the details out of it.

Fixes go into the latest release. To update, `brew upgrade netcap`, then `netcap install <name>` for each device.

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

- Read the state and settings of each device (`status`, `get`) and run a measurement (`check`)
- Change or lift caps (`on`, `off`, `set`)

**It cannot cut a device off:** `0` is refused on every OS. It can, however, set a very small cap such as
`0.01/0.01`, which makes the device's line unusable until someone runs `netcap off`.

### The gates on each device

| OS | First gate | Second gate |
| --- | --- | --- |
| macOS, Linux | The forced command: only the verbs in `--allow`, numeric arguments only (and `--for <seconds>` at the end of `on`) | sudoers: only the shaper's fixed verbs, without a password |
| Windows | The forced command | None. An Administrator's ssh session runs elevated |

On Windows the forced command is the only gate, so a netcap key line added by hand without
`restrict,command="…"` gives an elevated shell. `netcap install` writes the line for you; prefer it over editing by hand.

The files that run as root live only in directories that root alone can write
(`/Library/PrivilegedHelperTools`, `/usr/libexec/netcap`, and on Windows `C:\ProgramData\netcap` with its inheritance cut).
The shaper reads its config as numbers and never runs it as a script. See [docs/design.md](docs/design.md).

### Out of scope

- A device's own users. netcap caps a device at its owner's request; it is not meant to stop someone with an
  administrator account on that device from lifting the cap
- The ssh setup itself (host keys, sshd configuration, who else can log in). netcap relies on it
