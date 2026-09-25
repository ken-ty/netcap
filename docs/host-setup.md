# Device setup

English · [日本語](host-setup.ja.md)

The CLI calls the agent on each device over ssh; the agent checks the verb and arguments and hands them to the shaper.
The shortest path is in the [README](../README.md#quick-start).

## What `netcap install` does

`netcap install` (this machine) and `netcap install --ssh DEST` (another device) do everything below, so the rest of this
page is for reference and for setting a device up by hand.

1. Tell the OS (`uname`, or PowerShell for Windows)
2. Copy `mac/`, `linux/`, or `win/` to a temporary directory there, with the CLI's version written into the agent
3. Run the installer: `sudo bash …/install.sh --boot off` (the device's sudo password), or `install.ps1` on Windows
   (the ssh user must be an Administrator). Then remove the temporary directory
4. Create `~/.ssh/netcap` on this machine if missing, and add its forced-command line on the device
   ([below](#the-capped-device-decides-what-is-allowed)) unless the key is already there
5. Add the device to `hosts`, asking for its name once

To update a device, run `netcap install <name>` again. The `agent` column of `netcap get` shows each device's version.
`netcap uninstall <name>` reverses all of it (`--config-only` just forgets a device that is gone).

## Where the scripts are

`mac/`, `linux/`, and `win/` in this repository. If you installed with brew, under `$(brew --prefix)/opt/netcap/libexec/`.
Without brew, get them with clone or curl. The CLI works once `bin/netcap` is on your PATH.

```bash
# git clone
git clone https://github.com/ken-ty/netcap.git ~/.local/share/netcap

# curl (without git)
mkdir -p ~/.local/share/netcap
curl -fsSL https://github.com/ken-ty/netcap/archive/refs/tags/v0.7.0.tar.gz \
  | tar xz --strip-components 1 -C ~/.local/share/netcap

# to use the CLI
ln -s ~/.local/share/netcap/bin/netcap ~/.local/bin/netcap
```

Installed with curl, `netcap --version` prints `unknown`. curl and tar are also available on Windows out of the box.

```powershell
curl.exe -fsSL -o netcap.zip https://github.com/ken-ty/netcap/archive/refs/tags/v0.7.0.zip
tar -xf netcap.zip
cd netcap-0.7.0
python bin\netcap --version   # to use it as the CLI
```

## macOS

```bash
sudo bash mac/install.sh --boot on|off
```

| Path | Role |
| --- | --- |
| `/Library/PrivilegedHelperTools/netcap-agent` | The entry point netcap calls. Also used as the forced command |
| `/Library/PrivilegedHelperTools/netcap-netshape` | The shaper (runs as root; pf + dummynet) |
| `/usr/local/bin/netcap-check` | Measurement (only curl and ping, so no root needed) |
| `/etc/pf.anchors/netcap-netshape` | pf rules |
| `/etc/sudoers.d/netcap-netshape` | NOPASSWD for the invoking user, limited to the shaper's fixed verbs |
| `/Library/LaunchDaemons/netcap-netshape.plist` | Only with `--boot on` |

- `--boot on` applies the default cap at boot (initially 1/1; change it with `netcap set`). `off` leaves the device as is
- sudoers allows only the shaper's fixed verbs, for the user who ran `sudo`. For a different user, pass `NETCAP_USER=<user>`
- To remove: `sudo bash mac/uninstall.sh`
- The old name `ken-ty-netshape` (up to v0.5.0) is removed by running `install.sh` again. That also removes the cap, so reapply it with `netcap on`

## Linux

```bash
sudo bash linux/install.sh --boot on|off
```

| Path | Role |
| --- | --- |
| `/usr/libexec/netcap/netcap-agent` | The entry point netcap calls. Also used as the forced command |
| `/usr/libexec/netcap/netcap-netshape` | The shaper (runs as root; tc) |
| `/usr/local/bin/netcap-check` | Measurement (no root needed) |
| `/etc/sudoers.d/netcap-netshape` | NOPASSWD for the invoking user, limited to the shaper's fixed verbs |
| `/etc/systemd/system/netcap-netshape.service` | Only with `--boot on` |

- Caps the interface of the default route. Download is capped by redirecting ingress through `ifb`
- `--boot`, sudoers, and `NETCAP_USER` work as on macOS. To remove: `sudo bash linux/uninstall.sh`

## Windows

In an Administrator PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File win\install.ps1
```

Installs into `C:\ProgramData\netcap\`. To remove: `C:\ProgramData\netcap\uninstall.ps1`.

Two differences from mac: download cannot be capped (shown as `unsupported` in the table), and the `on` / `off` state survives reboots (`boot=keep`).

## The capped device decides what is allowed

**Which verbs are allowed is decided by the `authorized_keys` of the device being controlled.** netcap install creates a key
just for netcap and pins it to a forced command on the device. By hand:

```bash
# on the controlling machine (once)
ssh-keygen -t ed25519 -f ~/.ssh/netcap -C netcap@<this-machine> -N ""
```

Add one line to `~/.ssh/authorized_keys` on the controlled Mac (the public key is `~/.ssh/netcap.pub`):

```text
restrict,command="/Library/PrivilegedHelperTools/netcap-agent --allow 'status get check on off set'" ssh-ed25519 AAAA… netcap@<this-machine>
```

On a controlled Linux device, use `/usr/libexec/netcap/netcap-agent` as the agent path.

On a controlled Windows device, for an administrator's key, add to `C:\ProgramData\ssh\administrators_authorized_keys`:

```text
restrict,command="powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\netcap\netcap-agent.ps1 --allow 'status get check on off set'" ssh-ed25519 AAAA… netcap@<this-machine>
```

Put your usual ssh Host in the route column of `hosts`. netcap offers `~/.ssh/netcap` first, so a device that has the line
above only runs the agent, and one without it falls back to your own keys. It also turns off connection sharing
(`ControlPath=none`) for this: a shared `ControlMaster` connection from your own login would skip the forced command.

- Only the verbs listed in `--allow` get through. For a read-only device, use `'status get check'`
- `restrict` disables the shell, pty, and forwarding. The agent only splits arguments on whitespace and never interprets them as a shell
- Windows has no second gate like sudoers, so the forced command is the only gate
- Windows' sshd silently ignores `administrators_authorized_keys` if it is UTF-16 (what `>>` writes in Windows PowerShell 5)
  or writable by anyone but SYSTEM and Administrators. Write UTF-8, and give a new file
  `icacls <file> /inheritance:r /grant:r "*S-1-5-18:F" "*S-1-5-32-544:F"`

## Reading the table

### reach — whether the device was reached and the request went through

| reach | Meaning |
| --- | --- |
| `ok` | It worked |
| `unreachable` | ssh could not reach it (exit code 255) |
| `timeout` | No response in time |
| `no-agent` | The agent is not installed on the device |
| `no-sudo` | Not in the device's sudoers (mac, linux) |
| `denied` | The device does not allow that verb (`--allow` of the forced command) |
| `error` | Reached, but the device exited with non-zero |

### cap — whether a cap is in effect now (`status` only; read from the real state)

| cap | Meaning |
| --- | --- |
| `on` | A cap is in effect |
| `off` | No cap |
| `partial` | pf rules and dnctl pipes disagree (mac). Running `on` or `off` again brings them back in line |
| `?` | Not read, because reach is not `ok` |

### agent — the agent's version (`get` only)

Written in by `netcap install`. `-` for an agent installed before this column existed; `unknown` for one installed by hand from a clone.
If it differs from the CLI, run `netcap install <name>`.

### note — why it did not work

When reach is not `ok`, the last line of the device's output. The full output is in `raw` of `--json`.
