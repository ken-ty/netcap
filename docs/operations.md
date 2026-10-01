# Operations

English · [日本語](operations.ja.md)

What happens on reboots and power loss, and when more than one machine runs netcap.

## Where the state lives

**The cap lives on each device.** The machine running netcap (the controller) keeps only its settings:
`~/.config/netcap/` (hosts, profiles) and the key `~/.ssh/netcap`. Nothing runs between commands, on either side.
So the controller being on or off does not change any device.

## Power loss and reboots

| What happens | Result |
| --- | --- |
| The controller shuts down, sleeps, or leaves the network | Nothing changes on the devices. A cap stays until someone runs `off`; there is no timer that lifts it |
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

- **Use the same ssh user on a device from every controller.** The device's sudoers allows only the user who ran the
  installer last (macOS / Linux). A controller that logs in as another user gets `no-sudo`
- **Pass the same `--boot`.** Reinstalling sets it again (above)

To stop managing a device from one controller only, do not run `netcap uninstall <name>`: that removes the agent for every controller.
Instead run `netcap uninstall <name> --config-only`, then delete that controller's line (ending in `netcap@<controller>`)
from the device's `~/.ssh/authorized_keys` (Windows: `C:\ProgramData\ssh\administrators_authorized_keys`).

On Windows, the CLI runs day-to-day commands and `netcap install --ssh` (CI runs both there, the latter to a Windows device).
