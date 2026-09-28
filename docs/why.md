# Why netcap

English · [日本語](why.ja.md)

netcap is host-based QoS for a handful of computers, driven from one of them over ssh.
It fits when the router cannot help, and it is the wrong tool for several neighboring jobs. This page is for choosing.

## Choose netcap when

- **The router has no usable QoS**, or you cannot change it (an ISP-supplied router, a shared or rented line)
- **The devices to cap are computers** (macOS, Linux, Windows) you can reach over ssh
- **You want to cap whole devices from one place**, often several at once ("game mode": cap the laptop and the server, leave the gaming PC alone)
- **LAN traffic must stay fast**: only internet traffic is capped; LAN, VPN (100.64/10), ping, and DNS pass through

## Choose something else when

| Your situation | Better fit | Why |
| --- | --- | --- |
| You can run OpenWrt (or another router with good QoS) | Router SQM (cake / fq_codel) | It covers every device, phones and consoles included, and fixes bufferbloat for the whole line. Set this up first if you can |
| Phones, game consoles, TVs, or IoT devices need limits | Router QoS | netcap needs an agent on the device; those cannot run one |
| Windows computers in an Active Directory domain | Policy-based QoS through Group Policy | Built in, managed from the domain controller, per application / user / address |
| One Windows PC, per application | NetLimiter | Per-app and per-connection limits with a GUI (paid) |
| One Linux machine, one interface | wondershaper, or `tc` directly | A single script or command, no ssh or agent |
| One program on a Unix-like system | trickle | Userspace, per process (cooperative: it relies on library interposition) |
| Testing an app on a slow or lossy network | Network Link Conditioner (macOS / iOS), browser devtools throttling | Built for simulation: delay and packet loss as well as bandwidth |

## Side by side

✅ yes · ❌ no · ❓ not checked · n/a not applicable

| | netcap | Router SQM (OpenWrt) | Windows Policy-based QoS | NetLimiter | wondershaper | trickle | Network Link Conditioner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Runs on | each computer, driven from one | the router | each Windows PC, set from a domain controller | one Windows PC | one Linux machine | one process | one Mac |
| Devices covered | computers you install it on | everything behind the router | domain-joined Windows | that PC | that machine | that process | that Mac |
| OS | macOS, Linux, Windows | router firmware | Windows | Windows | Linux | Unix-like | macOS |
| Controls | per-device upload / download cap | WAN shaping and AQM, fairness between flows | outbound throttle and DSCP marking | per app / connection limits | per-interface up / down | per-process rate | bandwidth, delay, loss |
| Download cap | ✅ (Windows: upload only) | ✅ | ❌ outbound only | ✅ | ✅ | ✅ | ✅ |
| LAN left alone | ✅ | ✅ (only the WAN is shaped) | configurable by address | ❓ | ❌ whole interface | n/a | ❌ whole device |
| Many machines at once | ✅ profiles | ✅ (one router) | ✅ Group Policy | ❌ | ❌ | ❌ | ❌ |
| Needs | ssh + Python 3 | an OpenWrt router | Active Directory | a license | root | nothing | Xcode's Additional Tools |

## Where netcap stands

The closest relative is Windows Policy-based QoS: the cap is enforced on each computer, set from one place.
netcap does the same without a domain, across macOS, Linux, and Windows, with ssh as the only channel.
Each device decides what the controller may do (a forced command per key).

Compared with router QoS, netcap works from the other end. It does not prioritize traffic or manage queues on the line;
it takes bandwidth away from the computers you choose, so what is left stays free for the others.

## What netcap does not do

The full list, and what netcap should become, is in [vision.md](vision.md).

- Prioritize traffic, or fix bufferbloat on the line (use router SQM)
- Cap phones, consoles, TVs, or anything without the agent
- Cap download on Windows
- Limit per application
- Schedule by itself (call `netcap use` from cron or launchd)

Looking for packet capture? That is a different project with the same name: [dreadl0ck/netcap](https://github.com/dreadl0ck/netcap).

## References

- [OpenWrt: SQM (Smart Queue Management)](https://openwrt.org/docs/guide-user/network/traffic-shaping/sqm)
- [Microsoft Learn: Quality of Service (QoS) Policy](https://learn.microsoft.com/en-us/windows-server/networking/technologies/qos/qos-policy-top)
- [NetLimiter](https://www.netlimiter.com/)
- [magnific0/wondershaper](https://github.com/magnific0/wondershaper)
- [tc(8)](https://man7.org/linux/man-pages/man8/tc.8.html)
- [mariusae/trickle](https://github.com/mariusae/trickle)
- [NSHipster: Network Link Conditioner](https://nshipster.com/network-link-conditioner/)
