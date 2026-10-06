# Configuration

English · [日本語](configuration.ja.md)

Put `hosts` and `profiles` in `~/.config/netcap/` (or `$NETCAP_CONFIG_DIR`, or `$XDG_CONFIG_HOME/netcap`).
One entry per line; everything after `#` is a comment. Templates are in [examples/](../examples/).

## hosts

```text
# name   OS   route
laptop   mac  -
server   mac  server
gamepc   win  gamepc
```

| Column | Value |
| --- | --- |
| name | The name you pass to `netcap status <name>`. `all` is reserved |
| OS | One of `mac` (pf + dummynet), `linux` (tc), `win` (NetQosPolicy) |
| route | Your usual ssh destination: a Host from `~/.ssh/config`, or `user@host`. `-` for the machine running netcap itself. `netcap install` writes this line |

## profiles

```text
# name  device=value …
game    laptop=2/2  server=1/1  gamepc=off
quiet   laptop=1/1  server=1/1
none    laptop=off  server=off  gamepc=off
```

A value is `up/down` in Mbit/s, `on` (the device's own default, as `netcap on <name>` without flags), or `off`. Decimals work (`0.5/2`). `0` is an error: netcap refuses it and changes nothing (dummynet on macOS reads 0 as unlimited, so it cannot mean "cut off"). On macOS a value can go up to 2147.483647 (dummynet holds the rate as bit/s in a 32-bit integer); the device refuses more. To lift a cap, use `off`. Devices not listed are left untouched (`quiet` leaves `gamepc` as it is).

## Export and import

`netcap export` prints this machine's hosts and profiles as JSON; `netcap import` reads them back.
Use it for a backup, or to set up another controller ([operations.md](operations.md#more-than-one-controller)).

```bash
netcap export > netcap.json
netcap import netcap.json            # on the same or another machine; - reads stdin
netcap import netcap.json --replace  # overwrite existing hosts and profiles (keeps hosts.bak and profiles.bak)
```

- **Nothing secret is exported.** No keys (`~/.ssh/netcap` stays where it is) and no ssh settings: a route stays a Host name,
  resolved by the importing machine's own `~/.ssh/config`. Caps and defaults are not exported either; they live on the devices
- **This machine (route `-`) is not taken over elsewhere.** Imported on another machine, it would point at that machine,
  so it is skipped (and removed from profiles) with a message. Add it back with `netcap install <name> --ssh <dest>`
- **An export is checked before anything is written**: names, OS, routes, and profile values. A route that starts with `-`
  is refused, because ssh would read it as an option (`-oProxyCommand=…` runs a command). hosts is checked the same way
- Comments in hosts and profiles are not kept
- On a new controller, run `netcap install <name>` for each device to register that machine's own key
