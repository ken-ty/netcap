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
| route | Your usual ssh destination (a Host from `~/.ssh/config`). `-` for the machine running netcap itself. `netcap install` writes this line |

## profiles

```text
# name  device=value …
game    laptop=2/2  server=1/1  gamepc=off
quiet   laptop=1/1  server=1/1
none    laptop=off  server=off  gamepc=off
```

A value is `up/down` (positive Mbit/s; 0 is refused, since dummynet on macOS reads it as unlimited) or `off`. Devices not listed are left untouched (`quiet` leaves `gamepc` as it is).
