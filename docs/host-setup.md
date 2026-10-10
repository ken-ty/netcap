# Device setup

English · [日本語](host-setup.ja.md)

The CLI calls the agent on each device over ssh; the agent checks the verb and arguments and hands them to the shaper.
The shortest path is in the [README](../README.md#quick-start).

## What `netcap install` does

`netcap install` (this machine) and `netcap install --ssh DEST` (another device) do everything below, so the rest of this
page is for reference and for setting a device up by hand.

1. Tell the OS (`uname`, or PowerShell for Windows)
2. Copy the device side to a temporary directory there, with the CLI's version written into the agent: `win/` for Windows,
   or `mac/` and `linux/` together for macOS and Linux (the Linux installer takes the agent from `mac/`)
3. Run the installer: `sudo bash …/install.sh --boot off` (`--boot on` with `netcap install --boot on`; the device's
   sudo password), or `install.ps1` on Windows (`-WithDownload` / `-WithoutDownload` with `--with-download` /
   `--without-download`; the ssh user must be an Administrator). Then remove the temporary directory
4. Only for a device reached with `--ssh`: create `~/.ssh/netcap` on this machine if missing, and add its forced-command
   line on the device ([below](#the-capped-device-decides-what-is-allowed)) unless the key is already there.
   This machine needs no key: netcap runs its agent directly
5. Add the device to `hosts`. Without a name on the command line, it asks once when run from a terminal; otherwise it
   takes `me`, or the ssh destination

To update a device, run `netcap install <name>` again. That sets the boot behavior again too (`--boot off` unless given),
so add `--boot on` for a device that had it. A Windows device keeps its WinDivert choice (below) without a flag. The `agent` column of `netcap get` shows each device's version.
Which agent versions each CLI release works with: [compatibility.md](compatibility.md).
`netcap uninstall <name>` reverses what this controller added; the agent goes with the last controller
([operations.md](operations.md#more-than-one-controller)). `--config-only` just forgets a device that is gone.

## Where the scripts are

`mac/`, `linux/`, and `win/` in this repository. If you installed with brew, under `$(brew --prefix)/opt/netcap/libexec/`.
Without brew, get them with clone or curl. The CLI works once `bin/netcap` is on your PATH.

```bash
# git clone
git clone https://github.com/ken-ty/netcap.git ~/.local/share/netcap

# curl (without git)
mkdir -p ~/.local/share/netcap
curl -fsSL https://github.com/ken-ty/netcap/archive/refs/tags/v0.14.0.tar.gz \
  | tar xz --strip-components 1 -C ~/.local/share/netcap

# to use the CLI
ln -s ~/.local/share/netcap/bin/netcap ~/.local/bin/netcap
```

Installed with curl, `netcap --version` prints `unknown`. curl and tar are also available on Windows out of the box.

```powershell
curl.exe -fsSL -o netcap.zip https://github.com/ken-ty/netcap/archive/refs/tags/v0.14.0.zip
tar -xf netcap.zip
cd netcap-0.14.0
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
| `/etc/netcap-netshape.conf` | The default cap. Written by `netcap set`; without it the default is 1/1 |
| `/etc/sudoers.d/netcap-netshape` | NOPASSWD for each user who ran the installer, limited to the shaper's fixed verbs |
| `/Library/LaunchDaemons/netcap-netshape.plist` | Only with `--boot on` |
| `/Library/PrivilegedHelperTools/netcap-netshape-expire.plist` | The job `on --for` loads to lift the cap at the deadline. Not loaded at boot |

- `--boot on` applies the default cap at boot (initially 1/1; change it with `netcap set`). `off` leaves the device as is.
  The first `--boot on` also applies it now; running the installer again leaves the cap in effect, and its `--for`, as
  they are
- sudoers allows only the shaper's fixed verbs, for the user who ran `sudo`. For a different user, pass `NETCAP_USER=<user>`.
  Running it again as another user adds that user and keeps the others
- To remove: `sudo bash mac/uninstall.sh`. To remove only one user: `sudo bash mac/uninstall.sh --user`
  (everything goes with the last user)
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
| `/etc/netcap-netshape.conf` | The default cap, as on macOS |
| `/etc/sudoers.d/netcap-netshape` | NOPASSWD for each user who ran the installer, limited to the shaper's fixed verbs |
| `/etc/systemd/system/netcap-netshape.service` | Only with `--boot on` |

- Caps the interface of the IPv4 route to the internet (`ip -4 route get 1.1.1.1`). Download is capped by redirecting
  ingress through `ifb`. Needs `tc` and `ip` (iproute2)
- `--boot`, sudoers, and `NETCAP_USER` work as on macOS. `--boot on` needs systemd; without it (a container, for
  example), use `--boot off`. To remove: `sudo bash linux/uninstall.sh` (`--user` for one user)

## Windows

In an Administrator PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File win\install.ps1
```

Installs into `C:\ProgramData\netcap\`: the agent, the shaper (`netshape.ps1`), `netcap-check.ps1`, and `uninstall.ps1`.
`netcap set` writes the default cap to `netshape.conf` there. `on --for` writes its deadline to `until` there and
registers the scheduled task `\netcap\expire`, which lifts the cap at the deadline (it also runs at startup, in case the
machine was off then). To remove, in an Administrator PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\netcap\uninstall.ps1
```

Two differences from mac: download is capped only with WinDivert (below; otherwise `unsupported` in the table), and
the `on` / `off` state survives reboots (`boot=keep`).

### Download on Windows: WinDivert

Each Windows device has a choice, kept on the device and shown in the `download` column of `netcap get`:

| download | How it got there | What `netcap on` does |
| --- | --- | --- |
| `unset` | the default | From a terminal, asks whether to install WinDivert; with `--yes`, installs it. Otherwise caps upload only and names the device |
| `enabled` | `y` to that question, `on --yes`, or `netcap install <name> --with-download` | Caps download too |
| `declined` | `netcap install <name> --without-download`, which also removes WinDivert | Caps upload only, without asking or naming the device |

`use` and `protect` never ask: they cap upload only on an `unset` device and name it. `netcap install <name>` without
either flag keeps the choice. By hand: `install.ps1 -WithDownload` or `-WithoutDownload`. Installing needs x64 Windows
(ARM64 is not supported: [#111](https://github.com/ken-ty/netcap/issues/111)) and a connection to GitHub, and changes nothing when either is missing. Why it is asked for and what it costs:
[ADR 0001](adr/0001-cap-download-on-windows.md); what security software may say about it:
[SECURITY.md](../SECURITY.md#download-capping-on-windows-is-a-kernel-driver).

| Path | Role |
| --- | --- |
| `C:\ProgramData\netcap\windivert\` | `WinDivert.dll`, `WinDivert64.sys`, and `LICENSE` from the WinDivert 2.2.2 release zip, which the installer fetches and refuses unless its SHA-256 is the pinned one |
| `C:\ProgramData\netcap\netshape-down.ps1` | The download shaper. Runs as SYSTEM from the scheduled task `\netcap\download` while a cap is on (and at startup while it is on) |
| `C:\ProgramData\netcap\download.mbit` | The download rate the shaper reads. Written by `on` and `set`, removed by `off` |
| `C:\ProgramData\netcap\download.state`, `download.log` | Written by the shaper: its process and rate while it holds the WinDivert handle, and what went wrong |
| `C:\ProgramData\netcap\download.declined` | Written by `--without-download`, removed by `--with-download` |

`off` ends the shaper, so nothing is held back, but the WinDivert driver stays loaded until the next reboot:
netcap never stops its service on its own. `netcap unload-driver <name>` unloads it now when nothing uses it
([operations.md](operations.md#low-level-commands)).

`--without-download` stops the shaper and removes the `windivert` folder; `uninstall.ps1` removes it with the rest.
The driver stays loaded until the next reboot either way, unless `unload-driver` unloaded it: netcap never stops its service by itself, and
Windows removes the service, which WinDivert marks for deletion, at that reboot. A loaded driver's file cannot be deleted,
so `WinDivert64.sys` (and the folder it is in) is left to the one-time task `\netcap\cleanup`, which removes it at the next
startup. Installing again before that calls the task off.

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
restrict,command="powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\netcap\netcap-agent.ps1 --allow 'status get check on off set unload-driver'" ssh-ed25519 AAAA… netcap@<this-machine>
```

`unload-driver` is a low-level verb ([operations.md](operations.md#low-level-commands)); leave it out to refuse it.
`netcap install` adds it to a line that netcap wrote before it existed, and leaves a line changed by hand as it is.

Put your usual ssh Host in the route column of `hosts`. Once `~/.ssh/netcap` exists, netcap offers only that key
(`IdentitiesOnly=yes`), so a device that has the line above runs nothing but the agent. Without it, ssh would offer the keys
in ssh-agent first, and a device that also trusts your own key would take that one and skip the forced command.
So a device must have the netcap key: for one you added to `hosts` by hand, run `netcap install <name>`.
netcap also turns off connection sharing (`ControlPath=none`): a shared `ControlMaster` connection from your own login
would skip the forced command too.

- Only the verbs listed in `--allow` get through. For a read-only device, use `'status get check'`
- `restrict` disables the shell, pty, and forwarding. The agent only splits arguments on whitespace and never interprets them as a shell
- Windows has no second gate like sudoers, so the forced command is the only gate
- `netcap doctor` reads the file on each device reached over ssh and warns about a line for this machine's key that lacks
  `restrict` or the forced command (`unrestricted`), printing the line to put in its place. A device without the key
  shows `missing`. It exits with 0 when every device reached over ssh is `ok` (this machine shows `-`: it uses no key),
  3 when the only devices it could not check were out of reach, and 1 otherwise
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
| `partial` | Only part of the cap is in place: pf rules and dnctl pipes disagree (mac), only one of the upload and download classes is left (linux), or only some of netcap's QoS policies are left, or the download shaper is not running while its task is (win). Running `on` or `off` again brings them back in line |
| `?` | Not read, because reach is not `ok` |

### agent — the agent's version (`get` only)

Written in by `netcap install`. `-` for an agent installed before this column existed; `unknown` for one installed by hand from a clone.
If it differs from the CLI, run `netcap install <name>`.

### download — the WinDivert choice (`get` only, Windows)

`enabled`, `declined`, or `unset` ([above](#download-on-windows-windivert)). `-` on macOS and Linux, which cap download
without it.

### note — why it did not work, or when the cap ends

When reach is not `ok`, the last line of the device's output. The full output is in `raw` of `--json`.

When reach is `ok` and a cap set with `on --for` is pending, the time left (`off in 25m`), or `due, lifting soon` once the
deadline has passed and the device has yet to lift it. An agent from before `--for` refuses it; the note then says so and
how to update it (`netcap install <name>`).
