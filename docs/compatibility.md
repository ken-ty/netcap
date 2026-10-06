# Compatibility

English · [日本語](compatibility.ja.md)

The CLI on the controller and the agent on each device come from the same release but are updated separately:
`netcap install <name>` writes the CLI's version into the agent, one device at a time. This page records which agents
each CLI release works with.

## The rule

- Before 1.0, a minor release (0.x.0) may need a newer agent. A patch release (0.x.y) does not
- When a release needs a newer agent, it raises the minimum in the table below and says so in its tag message.
  Update each device with `netcap install <name>`
- The `agent` column of `netcap get` shows each device's version. A release CLI (a plain `x.y.z` version) also points out
  agents that differ from it; a CLI run from a clone does not, since its version carries a git suffix

Raise the minimum when a release changes any of these:

- The verbs the agent accepts, their arguments, or the `key=value` line it prints
- The forced-command line in the device's keys file ([host-setup.md](host-setup.md#the-capped-device-decides-what-is-allowed)):
  a line written by an older CLI may not allow a new verb
- What the installer puts on the device, and where ([host-setup.md](host-setup.md#where-the-scripts-are))

## Oldest agent each CLI works with

| CLI | Oldest agent | Notes |
| --- | --- | --- |
| 0.13.0 | 0.11.0 | The CLI sends nothing an 0.11.0 agent refuses: `protect --for` and `use --for` send `on --for`. The device side has fixes (macOS decimal caps, Windows install ACL, the `check --bytes` limit, and the 0.12.0 review); an older agent keeps those bugs. Update with `netcap install <name>` |
| 0.12.0 | 0.11.0 | The device side is unchanged since 0.11.0 |
| 0.11.0 | 0.11.0 | `on --for`, the `until=` / `left=` fields, and the installer changed. An older agent still answers `status` `get` `on` `off` `set` `check`, refuses `--for` without changing anything, and keeps the IPv6 and cmd.exe bugs. Update with `netcap install <name>` |
| 0.10.0 | 0.9.0 | The device side is unchanged since 0.9.0. `netcap get` points out these agents as different from the CLI; that is expected |
| 0.9.1 | 0.9.0 | The device side is unchanged since 0.9.0 |

Releases before 0.9.1 did not record this. A device with an agent older than 0.9.0 should be updated with
`netcap install <name>`.
