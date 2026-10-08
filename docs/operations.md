# Operations

English · [日本語](operations.ja.md)

What happens on reboots and power loss, and when more than one machine runs netcap.

## Where the state lives

**The cap lives on each device.** The machine running netcap (the controller) keeps only its settings:
`~/.config/netcap/` (hosts, profiles) and the key `~/.ssh/netcap`. Nothing runs on the controller between commands.
On a device, the OS runs netcap's shaper on its own only at boot with `boot=on`, and to lift an `on --for` cap at its deadline
(`use --for` and `protect --for` send each device `on --for` too).
So the controller being on or off does not change any device.

One exception: while `netcap protect` is in effect, the controller keeps how each device was before, in
`protect.json` under `$NETCAP_STATE_DIR`, or `$XDG_STATE_HOME/netcap` (`~/.local/state/netcap` if unset), for
`netcap protect --off`. A device out of reach when `protect` runs is left alone. A device that refuses or fails the
cap is reported, makes `protect` exit non-zero, and is not recorded as capped. A device changed since, by hand,
a reboot, or another controller, is left as it is. A device with an `on --for` deadline gets the time still left
back; if the deadline passed meanwhile, `--off` leaves it uncapped. A device `--off` could not put back (out of
reach, or the device failed) stays in the file, and `--off` exits non-zero: run `netcap protect --off` again when
it is back. Until then, `netcap rename` and `netcap uninstall` refuse the devices in the file. If the file cannot be
read, netcap says so instead of guessing: check each device with `netcap status`, put back by hand what protect
capped, then delete the file. The same goes for a device that is gone for good.

With `protect --for`, each device protect capped gets the deadline itself, and the file keeps it too. Before it,
`--off` works as above. After it, each device has lifted protect's cap by itself, so `--off` takes a device it finds
uncapped as expected, not as changed: it puts back the cap the device had before, with the time still left of that
cap's own `on --for`, and leaves the device uncapped if that deadline has passed as well. A device that still shows
protect's cap (`due, lifting soon`) is put back the same way. The file stays until `--off` runs, so run
`netcap protect --off` after the deadline as well; until then, another `netcap protect` refuses to start.

## Power loss and reboots

| What happens | Result |
| --- | --- |
| The controller shuts down, sleeps, or leaves the network | Nothing changes on the devices. A cap stays until someone runs `off`, or until its `--for` runs out: the device lifts that one by itself |
| A macOS / Linux device reboots, `boot=off` (the default) | It starts without a cap |
| A macOS / Linux device reboots, `boot=on` | It starts capped at its default (the `default` column of `netcap get`) |
| A Windows device reboots (`boot=keep`) | It keeps what it had: capped stays capped, uncapped stays uncapped |
| A device is off or unreachable when you run a command | It shows `unreachable` or `timeout`; the other devices are still changed. Nothing is queued: when it is back, run the command (or `netcap use`) again |

The controller can also be a capped device (`me`); the same rows apply to it.

To be sure a machine always comes back with its full line (a server, for example), keep `boot=off`.
Reinstalling sets `boot` again: `netcap install <name>` uses `--boot off` unless you pass `--boot on`.

## More than one controller

Any machine with the CLI can be a controller, and several can manage the same devices.
Since the state lives on the devices, every controller reads the same `status`. The last command wins.
There is no locking, so avoid sending commands to the same device from two controllers at the same moment.

Each controller has its own settings and its own key:

- **Names are per controller.** `me` on the Mac mini is the Mac mini itself. The same device can have different names on different controllers
- **Profiles are per controller.** Copy `profiles` if you want the same recipes, and adjust the names
- **Each controller registers its own key** on each device. The device keeps one agent and one `authorized_keys` line per controller

To add a controller, install the CLI there, bring the settings over with `netcap export` / `netcap import`
([configuration.md](configuration.md#export-and-import)), and run `netcap install` from it: `netcap install` for itself,
`netcap install <name>` for each imported device. The device's installer runs again, which is harmless, with two things to keep in mind:

- **Each controller may log in as its own ssh user.** The installer adds the user who runs it to the device's sudoers and
  keeps the users already there (macOS / Linux). netcap 0.10.0 and earlier replaced them instead, so update the CLI on
  every controller before using more than one user
- **Pass the same `--boot`.** Reinstalling sets it again (above). A Windows device's WinDivert choice is kept on the
  device, so it needs no flag

To stop managing a device from one controller, run `netcap uninstall <name>` there. It takes back only what that controller
added: its key, and on macOS / Linux its ssh user in the device's sudoers. The agent stays while another controller's key is
on the device for the same login, and goes with the last one. To remove everything at once, run `sudo bash mac/uninstall.sh`
(Linux: `linux/uninstall.sh`; Windows: `C:\ProgramData\netcap\uninstall.ps1`) on the device ([host-setup.md](host-setup.md)).

On Windows, the CLI runs day-to-day commands and `netcap install --ssh` (CI runs both there, the latter to a Windows device).

## Low-level commands

`netcap help --all` lists, after the usual commands, the ones most people never need. `netcap -h` and completion leave
them out, as `git help` leaves out git's plumbing.

- `netcap unload-driver <host>|all` (Windows): unload the WinDivert driver now. netcap otherwise leaves it loaded until the
  next reboot, while `off` already stops it from holding anything back
  ([ADR 0001](adr/0001-cap-download-on-windows.md)). The device refuses while a download cap is on or another program
  has WinDivert loaded: stopping the driver under an open handle breaks later opens until reboot
  ([basil00/WinDivert#406](https://github.com/basil00/WinDivert/issues/406)). It needs an agent that knows it, and over
  ssh a key line that allows it; `netcap install <name>` gives both, and the table says which is missing

## Exit codes

`netcap help exit-codes` prints the same list.

| Code | Meaning |
| --- | --- |
| 0 | Success: every device answered and did what was asked |
| 1 | Failure: a device refused or failed, or a host or setting is wrong |
| 2 | Usage error: a bad command, flag, or argument. Nothing was sent |
| 3 | The only failures were devices out of reach (ssh could not connect, or timed out). Try again later |

With several devices, the other devices are still changed when one fails; the code says the worst that happened.
`use` and `protect` judge each device by the change itself: one that refused it (`denied`, `no-sudo`) or failed
counts as failed even though its status still reads. Flags, arguments, and every value of the profile `use` applies
are checked before anything is sent: a bad one is 2 (or 1 for a value in profiles, which is a setting) and changes
nothing.
