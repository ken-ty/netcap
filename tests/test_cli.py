"""The CLI behavior promised by the README and docs. A fake ssh answers for the devices.

  python3 -m unittest discover tests
"""
import argparse
import ast
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NETCAP = ROOT / "bin" / "netcap"

# A fake ssh. The Host name decides the answer; each called Host is written to the log
FAKE_SSH = textwrap.dedent("""\
    #!/usr/bin/env python3
    import os, sys, time
    host, cmd = sys.argv[-2], sys.argv[-1]
    if "-EncodedCommand" in cmd:  # log and match the PowerShell script, not its base64
        import base64
        cmd = "powershell " + base64.b64decode(cmd.split()[-1]).decode("utf-16-le")
    with open(os.environ["FAKE_SSH_LOG"], "a") as f:
        f.write(f"{host} {cmd}\\n")
    # What netcap install asks a new device (h-new, a Mac). authorized_keys lives under FAKE_REMOTE_HOME
    if cmd == "uname -s":
        print("Darwin"); sys.exit(0)
    if cmd.startswith("mktemp -d"):
        print("/tmp/netcap.abc123"); sys.exit(0)
    if cmd == "sh -s":
        import subprocess
        sys.exit(subprocess.run(["sh", "-s"], env={**os.environ, "HOME": os.environ["FAKE_REMOTE_HOME"]}).returncode)
    if "sudo bash" in cmd:
        sys.exit(0)
    # What netcap doctor reads: the device's keys file, served from FAKE_REMOTE_HOME
    if host != "h-unreachable" and cmd.startswith("cat ~/.ssh/authorized_keys"):
        import subprocess
        sys.exit(subprocess.run(["sh", "-c", cmd], env={**os.environ, "HOME": os.environ["FAKE_REMOTE_HOME"]}).returncode)
    if cmd.startswith("powershell "):
        if "NewGuid" in cmd and host != "h-notemp":
            print("C:\\\\Temp\\\\netcap-1"); sys.exit(0)
        if "administrators_authorized_keys" in cmd:
            f = os.path.join(os.environ["FAKE_REMOTE_HOME"], "administrators_authorized_keys")
            if os.path.exists(f):
                print(open(f).read(), end="")
            sys.exit(0)
    ok = "netshape state={s} up_mbit={u} down_mbit={u} down_src=applied pipes=2 rules=2"
    # Devices that keep their state in $FAKE_STATE/<host> ("off" or "on UP DOWN"). check pings 40 ms when every
    # other such device is capped, 400 ms otherwise. <host>.gone makes the device unreachable
    if host.startswith("h-s-"):
        state_dir = os.environ["FAKE_STATE"]
        st = os.path.join(state_dir, host)
        if os.path.exists(st + ".gone"):
            print(f"ssh: connect to host {host}: Operation timed out", file=sys.stderr); sys.exit(255)
        words = cmd.split()
        verb, args = (words[1], words[2:]) if len(words) > 1 else ("", [])
        if verb == "on":
            open(st, "w").write("on " + (" ".join(args) or "1 1"))
        elif verb == "off":
            open(st, "w").write("off")
        elif verb == "status":
            s = open(st).read().split() if os.path.exists(st) else ["off"]
            if s[0] == "on":
                print(f"netshape state=on up_mbit={s[1]} down_mbit={s[2]} down_src=applied")
            else:
                print("netshape state=off up_mbit=- down_mbit=- down_src=applied")
        elif verb == "check":
            others = [f for f in os.listdir(state_dir) if f.startswith("h-s-") and "." not in f and f != host]
            capped = all(open(os.path.join(state_dir, f)).read().startswith("on") for f in others)
            ms = 40 if capped else 400
            print(f"netcheck down_mbit=10.00 up_mbit=5.00 ping_med={ms} ping_p95={ms} ping_max={ms} ping_n=10 bytes=1000000")
        sys.exit(0)
    if host == "h-off":
        print(ok.format(s="off", u="-"))
    elif host == "h-on":
        print(ok.format(s="on", u="2"))
    elif host == "h-timed":  # on --for 1800, 29 minutes left
        print(ok.format(s="on", u="2") + " until=1900000000 left=1740")
    elif host == "h-due":  # the deadline has passed; the device's scheduler lifts it on its next run
        print(ok.format(s="on", u="2") + " until=1700000000 left=0")
    elif host == "h-oldfor":  # an agent from before --for
        if "--for" in cmd:
            print("netcap-agent: arguments must be numbers: --for", file=sys.stderr); sys.exit(77)
        print(ok.format(s="on", u="2"))
    elif host == "h-partial":
        print(ok.format(s="partial", u="-"))
    elif host == "h-unreachable":
        print("ssh: Could not resolve hostname h-unreachable", file=sys.stderr); sys.exit(255)
    elif host == "h-nosudo":
        print("sudo: a password is required", file=sys.stderr); sys.exit(1)
    elif host == "h-denied":
        print("netcap-agent: not allowed for this key: on", file=sys.stderr); sys.exit(77)
    elif host == "h-noagent":
        print("bash: line 1: /Library/PrivilegedHelperTools/netcap-agent: No such file or directory", file=sys.stderr); sys.exit(127)
    elif host == "h-error":
        print("line one\\nlast line of error", file=sys.stderr); sys.exit(3)
    elif host == "h-slow":
        time.sleep(5)
    """)


class CLI(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        (self.tmp / "bin").mkdir()
        ssh = self.tmp / "bin" / "ssh"
        ssh.write_text(FAKE_SSH)
        ssh.chmod(0o755)
        scp = self.tmp / "bin" / "scp"
        # Copying to h-scpfail fails
        scp.write_text("#!/bin/sh\necho \"scp $*\" >> \"$FAKE_SSH_LOG\"\ncase \"$*\" in *h-scpfail:*) exit 1;; esac\n")
        scp.chmod(0o755)
        self.log = self.tmp / "ssh.log"
        self.log.touch()
        self.conf = self.tmp / "conf"
        self.conf.mkdir()
        # LC_ALL=C: the assertions read English messages, whatever the locale of the machine running the tests
        self.state = self.tmp / "devices"
        self.state.mkdir()
        self.env = {**os.environ, "PATH": f"{self.tmp / 'bin'}{os.pathsep}{os.environ['PATH']}",
                    "FAKE_SSH_LOG": str(self.log), "NETCAP_CONFIG_DIR": str(self.conf), "LC_ALL": "C",
                    "FAKE_STATE": str(self.state), "NETCAP_STATE_DIR": str(self.tmp / "netcap-state")}

    def hosts(self, *names, profiles=""):
        (self.conf / "hosts").write_text("".join(f"{n} mac h-{n}\n" for n in names))
        (self.conf / "profiles").write_text(profiles)

    def netcap(self, *args, env=None):
        return subprocess.run([sys.executable, str(NETCAP), *args], capture_output=True, text=True,
                              env=env or self.env, timeout=30)

    def status_row(self, name):
        p = self.netcap("status", name, "--json")
        self.assertEqual(p.stderr, "", p.stderr)
        return json.loads(p.stdout)[0]

    # README: the forms listed under Usage work as written
    def test_usage_forms_in_readme(self):
        self.hosts("off", profiles="p  off=off\n")
        for args in (["status", "off", "--json"], ["status", "all", "--json"], ["get", "off", "--json"],
                     ["on", "off", "--up", "1", "--down", "2"], ["off", "off"],
                     ["set", "off", "--up", "1", "--down", "2"], ["use", "p"], ["profiles"],
                     ["status", "off", "-v"], ["--version"], ["-V"], ["protect", "--off"]):
            with self.subTest(args=args):
                p = self.netcap(*args)
                self.assertNotIn("unrecognized arguments", p.stderr)
                self.assertNotIn("invalid choice", p.stderr)
                self.assertEqual(p.returncode, 0, p.stderr)

    # README: -v adds what the table leaves out; -vv also the raw output from the device
    def test_verbose(self):
        (self.conf / "hosts").write_text("off mac h-off\nerr mac h-error\n")
        (self.conf / "profiles").write_text("")
        plain = self.netcap("status", "off").stdout
        self.assertNotIn("=== off", plain)
        for args in (["status", "off", "-v"], ["-v", "status", "off"], ["status", "off", "--verbose"]):
            with self.subTest(args=args):
                p = self.netcap(*args)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertTrue(p.stdout.startswith(plain), "the table comes first, unchanged")
                self.assertIn("\n=== off\n", p.stdout)
                self.assertRegex(p.stdout, r"(?m)^  route +h-off$")
                self.assertRegex(p.stdout, r"(?m)^  pipes +2$")
                self.assertNotIn("netshape state=", p.stdout)  # the raw output is -vv
        for args in (["status", "off", "-vv"], ["-v", "status", "off", "-v"]):
            with self.subTest(args=args):
                self.assertIn("netshape state=off", self.netcap(*args).stdout)
        # A device that failed shows its whole output at -v, not only the last line the note has
        p = self.netcap("status", "err", "-v")
        self.assertIn("line one", p.stdout)
        self.assertNotIn("line one", self.netcap("status", "err").stdout)
        # --json is the same with or without -v
        self.assertEqual(self.netcap("status", "off", "--json", "-v").stdout, self.netcap("status", "off", "--json").stdout)

    # -v is --verbose now; the version is -V, and --raw became -vv
    def test_version_is_capital_v(self):
        self.hosts("off")
        self.assertRegex(self.netcap("-V").stdout, r"^netcap \S+\n$")
        self.assertNotEqual(self.netcap("-v").returncode, 0)  # a command is required
        self.assertIn("unrecognized arguments: --raw", self.netcap("status", "off", "--raw").stderr)

    # docs/host-setup.md: Reading the table, reach
    def test_reach(self):
        self.hosts("off", "unreachable", "nosudo", "denied", "noagent", "error")
        rows = {r["host"]: r["reach"] for r in json.loads(self.netcap("status", "all", "--json").stdout)}
        self.assertEqual(rows, {"off": "ok", "unreachable": "unreachable", "nosudo": "no-sudo",
                                "denied": "denied", "noagent": "no-agent", "error": "error"})

    def test_reach_timeout(self):
        mod = load_netcap()
        mod.HOSTS["slow"] = {"os": "mac", "ssh": "h-slow"}
        mod.TIMEOUT["status"] = 1
        os.environ.update(PATH=self.env["PATH"], FAKE_SSH_LOG=str(self.log))
        self.assertEqual(mod.run("slow", "status")["reach"], "timeout")

    # docs/host-setup.md: with the netcap key, it is the only key offered, so ssh-agent's keys cannot skip the forced command
    def test_only_the_netcap_key_is_offered(self):
        mod = load_netcap()
        mod.HOSTS["box"] = {"os": "mac", "ssh": "h-box"}
        mod.KEY = self.tmp / "netcap"
        self.assertNotIn("IdentitiesOnly=yes", mod.build_cmd("box", "status", []))  # no key yet: the user's own keys
        mod.KEY.write_text("key")
        cmd = mod.build_cmd("box", "status", [])
        i = cmd.index("-i")
        self.assertEqual(cmd[i + 1], str(mod.KEY))
        self.assertIn("IdentitiesOnly=yes", cmd[:cmd.index("h-box")])
        self.assertIn("ControlPath=none", cmd[:cmd.index("h-box")])

    # docs/host-setup.md: Reading the table, cap and note
    def test_cap_and_note(self):
        self.hosts("off", "on", "partial", "error")
        lines = {l.split()[0]: l for l in self.netcap("status", "all").stdout.splitlines()[2:] if l.strip()}
        self.assertRegex(lines["off"], r"^off\s+ok\s+off\s")
        self.assertRegex(lines["on"], r"^on\s+ok\s+on\s+2 Mbit/s\s+2 Mbit/s\*\s*$")
        self.assertRegex(lines["partial"], r"^partial\s+ok\s+partial\s")
        self.assertRegex(lines["error"], r"^error\s+error\s+\?\s.*last line of error$")

    # #30: netcap protect. Cap every other device, measure the protected one before and after, undo with --off
    def devices(self, **states):
        (self.conf / "hosts").write_text("".join(f"{n} mac h-s-{n}\n" for n in states))
        for n, s in states.items():
            (self.state / f"h-s-{n}").write_text(s)

    def device(self, name):
        return (self.state / f"h-s-{name}").read_text()

    def test_protect_caps_the_others_and_measures(self):
        self.devices(game="off", laptop="off", server="on 3 3")
        p = self.netcap("protect", "game", "--up", "2", "--down", "2")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((self.device("laptop"), self.device("server"), self.device("game")), ("on 2 2", "on 2 2", "off"))
        self.assertRegex(p.stdout, r"(?m)^before\s+ok\s+10.00 Mbit/s\s+5.00 Mbit/s\s+400/400/400")
        self.assertRegex(p.stdout, r"(?m)^after\s+ok\s+10.00 Mbit/s\s+5.00 Mbit/s\s+40/40/40")
        self.assertIn("to undo: netcap protect --off", p.stdout)
        log = [l for l in self.log.read_text().splitlines() if l.startswith("h-s-game")]
        self.assertEqual([l.split()[2] for l in log], ["status", "check", "check"])  # never capped or uncapped
        # --off puts each device back as it was
        p = self.netcap("protect", "--off")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((self.device("laptop"), self.device("server"), self.device("game")), ("off", "on 3 3", "off"))
        self.assertIn("nothing to undo", self.netcap("protect", "--off").stdout)

    def test_protect_json(self):
        self.devices(game="off", laptop="off")
        out = json.loads(self.netcap("protect", "game", "--json").stdout)
        self.assertEqual(out["protected"], "game")
        self.assertEqual((out["before"]["ping_med"], out["after"]["ping_med"]), ("400", "40"))
        self.assertEqual([r["host"] for r in out["devices"]], ["laptop"])
        self.assertEqual(self.device("laptop"), "on 1 1")  # the device's default without --up / --down

    def test_protect_off_leaves_a_device_someone_changed(self):
        self.devices(game="off", laptop="off", server="off")
        self.netcap("protect", "game")
        (self.state / "h-s-server").write_text("on 5 5")  # changed by hand in the meantime
        p = self.netcap("protect", "--off")
        self.assertEqual((self.device("laptop"), self.device("server")), ("off", "on 5 5"))
        self.assertIn("server changed since protect; left as is. To undo: netcap off server", p.stdout)

    def test_protect_off_keeps_an_unreachable_device_for_later(self):
        self.devices(game="off", laptop="off")
        self.netcap("protect", "game")
        (self.state / "h-s-laptop.gone").touch()
        p = self.netcap("protect", "--off")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("run netcap protect --off again", p.stdout)
        (self.state / "h-s-laptop.gone").unlink()
        self.assertEqual(self.netcap("protect", "--off").returncode, 0)
        self.assertEqual(self.device("laptop"), "off")

    def test_protect_refuses(self):
        self.devices(game="off", laptop="off")
        for args, msg in ((["protect"], "netcap protect <host>"), (["protect", "all"], "one device"),
                          (["protect", "game", "--up", "2"], "--up and --down together"),
                          (["protect", "game", "--up", "0", "--down", "1"], "positive numbers")):
            with self.subTest(args=args):
                p = self.netcap(*args)
                self.assertNotEqual(p.returncode, 0)
                self.assertIn(msg, p.stderr)
        self.assertEqual(self.netcap("protect", "game").returncode, 0)
        p = self.netcap("protect", "laptop")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("already protecting game", p.stderr)

    def test_protect_stops_when_the_protected_device_is_unreachable(self):
        self.devices(game="off", laptop="off")
        (self.state / "h-s-game.gone").touch()
        p = self.netcap("protect", "game")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("changed nothing", p.stderr)
        self.assertEqual(self.device("laptop"), "off")

    # #74: --load keeps the line busy from the other devices while the protected one is measured, before and after
    def test_protect_under_load(self):
        self.devices(game="off", laptop="off", server="off")
        p = self.netcap("protect", "game", "--load", "5")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        log = self.log.read_text().splitlines()
        for h in ("laptop", "server"):
            self.assertEqual(sum(l.startswith(f"h-s-{h} ") and " check --bytes 5000000" in l for l in log), 2, h)
        self.assertIn("latency on game: improved (median 400 -> 40 ms)", p.stdout)
        self.assertIn("about 40 MB", p.stdout)  # 5 MB x 2 devices x up and down x before and after
        out = json.loads(self.netcap("protect", "--off") and self.netcap("protect", "game", "--load", "1", "--json").stdout)
        self.assertEqual(out["verdict"], "improved")

    def test_protect_without_load_measures_only_the_protected_device(self):
        self.devices(game="off", laptop="off")
        self.netcap("protect", "game")
        self.assertNotIn("h-s-laptop /Library/PrivilegedHelperTools/netcap-agent check", self.log.read_text())

    def test_protect_load_range(self):
        self.devices(game="off", laptop="off")
        for bad in ("0", "51", "x"):
            with self.subTest(bad=bad):
                p = self.netcap("protect", "game", "--load", bad)
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("--load", p.stderr)
        self.assertEqual(self.device("laptop"), "off")

    def test_latency_verdict(self):
        verdict = load_netcap().latency_verdict
        for before, after, want in (("400", "40", "improved"), ("40", "400", "worse"), ("40", "35", "no clear change"),
                                    ("100", "85", "no clear change"), ("-", "40", "unknown")):
            with self.subTest(before=before, after=after):
                self.assertEqual(verdict({"ping_med": before}, {"ping_med": after}), want)

    def test_protect_needs_another_device(self):
        self.devices(game="off")
        p = self.netcap("protect", "game")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("no other device", p.stderr)

    # #29: on --for. The duration goes to the device in seconds, at the end of on
    def test_on_for(self):
        self.hosts("on")
        for flags, sent in ((["--up", "2", "--down", "3", "--for", "30m"], "on 2 3 --for 1800"),
                            (["--for", "2h"], "on --for 7200"), (["--for", "1h30m"], "on --for 5400")):
            with self.subTest(flags=flags):
                self.log.write_text("")
                p = self.netcap("on", "on", *flags)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn(f"/Library/PrivilegedHelperTools/netcap-agent {sent}", self.log.read_text())
        self.log.write_text("")
        self.netcap("on", "on")
        self.assertNotIn("--for", self.log.read_text())

    def test_on_for_refuses_a_bad_duration(self):
        self.hosts("on")
        for bad in ("0m", "30", "1.5h", "25h", "30s", "m", ""):
            with self.subTest(bad=bad):
                p = self.netcap("on", "on", "--for", bad)
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("--for", p.stderr)
        self.assertNotIn("netcap-agent on", self.log.read_text())

    def test_status_shows_the_time_left(self):
        self.hosts("timed")
        line = self.netcap("status", "timed").stdout.splitlines()[2]
        self.assertRegex(line, r"^timed\s+ok\s+on\s+2 Mbit/s\s+2 Mbit/s\*\s+off in 29m$")
        self.assertEqual(self.status_row("timed")["left"], "1740")
        # Past the deadline, macOS lifts it within a minute and Windows when the task runs: "off in 0m" read as a mistake
        self.hosts("due")
        self.assertRegex(self.netcap("status", "due").stdout.splitlines()[2], r"\s+due, lifting soon$")

    def test_on_for_with_an_old_agent(self):
        self.hosts("oldfor")
        p = self.netcap("on", "oldfor", "--for", "30m")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("this agent does not know --for (nothing changed). Update it: netcap install oldfor", p.stdout)

    # docs/configuration.md: devices not listed are left untouched
    def test_use_leaves_unlisted_hosts(self):
        self.hosts("off", "on", profiles="quiet  off=1/1\n")
        self.assertEqual(self.netcap("use", "quiet").returncode, 0)
        called = {l.split()[0] for l in self.log.read_text().splitlines()}
        self.assertEqual(called, {"h-off"})

    # docs/configuration.md: a value is up/down or off
    def test_profile_values(self):
        self.hosts("off", profiles="a  off=2/3\nb  off=off\n")
        self.assertEqual(self.netcap("use", "a").returncode, 0)
        self.assertEqual(self.netcap("use", "b").returncode, 0)
        log = self.log.read_text()
        self.assertIn("netcap-agent on 2 3", log)
        self.assertIn("netcap-agent off", log)

    # docs/configuration.md: a cap is a positive number. 0 would mean unlimited to dummynet on macOS
    def test_zero_is_refused(self):
        self.hosts("off", profiles="z  off=0/2\n")
        for args in (["on", "off", "--up", "0", "--down", "2"], ["set", "off", "--up", "1", "--down", "0.0"], ["use", "z"]):
            with self.subTest(args=args):
                p = self.netcap(*args)
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("positive", p.stderr)
        self.assertFalse(self.log.exists() and "netcap-agent on" in self.log.read_text())

    # README: Quick Start. on tells how to undo it, right where it is needed
    def test_on_prints_undo(self):
        self.hosts("off")
        self.assertIn("to undo: netcap off off", self.netcap("on", "off").stdout)
        self.assertNotIn("to undo", self.netcap("on", "off", "--json").stdout)
        self.assertNotIn("to undo", self.netcap("off", "off").stdout)

    # docs/configuration.md: OS is mac / linux / win. docs/host-setup.md: where the Linux agent lives
    def test_linux_host(self):
        (self.conf / "hosts").write_text("box linux h-off\n")
        self.assertEqual(self.netcap("status", "box").returncode, 0)
        self.assertIn("/usr/libexec/netcap/netcap-agent status", self.log.read_text())

    # docs/configuration.md: the location is $NETCAP_CONFIG_DIR or $XDG_CONFIG_HOME/netcap
    def test_config_dir(self):
        self.hosts("off")
        xdg = self.tmp / "xdg"
        shutil.copytree(self.conf, xdg / "netcap")
        env = {k: v for k, v in self.env.items() if k != "NETCAP_CONFIG_DIR"}
        self.assertEqual(self.netcap("status", "off", env={**env, "XDG_CONFIG_HOME": str(xdg)}).returncode, 0)

    # README: a copy of examples/ is read as is
    def test_examples_parse(self):
        shutil.copy(ROOT / "examples" / "hosts", self.conf)
        shutil.copy(ROOT / "examples" / "profiles", self.conf)
        self.assertEqual(self.netcap("profiles").returncode, 0)

    # docs/host-setup.md: installed with curl, --version is unknown
    def test_version_without_git(self):
        copy = self.tmp / "tree" / "bin"
        copy.mkdir(parents=True)
        shutil.copy(NETCAP, copy)
        p = subprocess.run([sys.executable, str(copy / "netcap"), "--version"], capture_output=True, text=True,
                           env={**self.env, "GIT_CEILING_DIRECTORIES": str(self.tmp)})
        self.assertEqual(p.stdout.strip(), "netcap unknown")

    def install_env(self):
        (self.tmp / "home").mkdir(exist_ok=True)
        (self.tmp / "remote").mkdir(exist_ok=True)
        return {**self.env, "HOME": str(self.tmp / "home"), "FAKE_REMOTE_HOME": str(self.tmp / "remote")}

    def remote_keys(self):
        return (self.tmp / "remote" / ".ssh" / "authorized_keys").read_text().splitlines()

    # README: Quick Start. install copies the device side, runs its installer, pins the netcap key, and adds hosts
    def test_install_remote(self):
        env = self.install_env()
        p = self.netcap("install", "box", "--ssh", "h-new", env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("box      mac   h-new", (self.conf / "hosts").read_text())
        self.assertTrue((self.tmp / "home" / ".ssh" / "netcap").exists())
        log = self.log.read_text()
        self.assertIn("scp -q -r", log)
        self.assertIn("sudo bash /tmp/netcap.abc123/mac/install.sh --boot off", log)
        pub = (self.tmp / "home" / ".ssh" / "netcap.pub").read_text().strip()
        want = f"restrict,command=\"/Library/PrivilegedHelperTools/netcap-agent --allow 'status get check on off set'\" {pub}"
        self.assertEqual(self.remote_keys(), [want])
        # Running it again (an update) neither duplicates the key nor the hosts line
        self.assertEqual(self.netcap("install", "box", env=env).returncode, 0)
        self.assertEqual(self.remote_keys(), [want])
        self.assertEqual((self.conf / "hosts").read_text().count("box"), 1)
        # uninstall takes both back: this controller's key, and this ssh user in the device's sudoers (#31)
        self.assertEqual(self.netcap("uninstall", "box", env=env).returncode, 0)
        self.assertIn("/mac/uninstall.sh --user", self.log.read_text())
        self.assertEqual(self.remote_keys(), [])
        self.assertNotIn("box", (self.conf / "hosts").read_text())

    # docs/operations.md: More than one controller. uninstall from one controller leaves the others working (#31)
    def test_uninstall_keeps_the_agent_for_other_controllers(self):
        env = self.install_env()
        self.assertEqual(self.netcap("install", "box", "--ssh", "h-new", env=env).returncode, 0)
        other = ("restrict,command=\"/Library/PrivilegedHelperTools/netcap-agent --allow 'status get check on off set'\" "
                 "ssh-ed25519 AAAAother netcap@other")
        with open(self.tmp / "remote" / ".ssh" / "authorized_keys", "a") as f:
            f.write(other + "\n")
        self.log.write_text("")
        p = self.netcap("uninstall", "box", env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertNotIn("uninstall.sh", self.log.read_text())
        self.assertEqual(self.remote_keys(), [other])
        self.assertIn("another controller still uses the agent on h-new", p.stdout)
        self.assertNotIn("box", (self.conf / "hosts").read_text())

    # A failed copy still removes the temporary directory made on the device
    def test_failed_copy_removes_the_device_temp_dir(self):
        mod = load_netcap()
        for os_, script, rm in (("mac", "install.sh", "rm -rf /tmp/netcap.abc123"),
                                ("win", "install.ps1", "Remove-Item -Recurse -Force 'C:\\Temp\\netcap-1'")):
            with self.subTest(os=os_), mock.patch.dict(os.environ, PATH=self.env["PATH"], FAKE_SSH_LOG=str(self.log)):
                self.log.write_text("")
                self.assertNotEqual(mod.run_device_script("h-scpfail", os_, script), 0)
                log = self.log.read_text()
                self.assertIn("scp -q -r", log)
                self.assertIn(rm, log)

    def test_install_keeps_other_keys(self):
        env = self.install_env()
        (self.tmp / "remote" / ".ssh").mkdir()
        (self.tmp / "remote" / ".ssh" / "authorized_keys").write_text("ssh-ed25519 AAAAmine me@laptop")  # no newline at the end
        self.assertEqual(self.netcap("install", "box", "--ssh", "h-new", env=env).returncode, 0)
        keys = self.remote_keys()
        self.assertEqual(keys[0], "ssh-ed25519 AAAAmine me@laptop")
        self.assertEqual(len(keys), 2)
        self.netcap("uninstall", "box", env=env)
        self.assertEqual(self.remote_keys(), ["ssh-ed25519 AAAAmine me@laptop"])

    def test_install_name_taken(self):
        self.hosts("off")
        p = self.netcap("install", "off", "--ssh", "h-new", env=self.install_env())
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("netcap rename off", p.stderr)

    # A Windows device that prints no temporary directory gets the same error as macOS / Linux, not a traceback
    def test_win_temp_dir_not_made(self):
        mod = load_netcap()
        os.environ.update(PATH=self.env["PATH"], FAKE_SSH_LOG=str(self.log), LC_ALL="C")
        with self.assertRaises(SystemExit) as e:
            mod.run_device_script("h-notemp", "win", "install.ps1")  # the fake ssh prints nothing for this host
        self.assertEqual(str(e.exception), "could not make a temporary directory on h-notemp")
        self.assertNotIn("scp", self.log.read_text())

    # docs/host-setup.md: netcap doctor finds a netcap key line without its forced command
    PUB = "ssh-ed25519 AAAAnetcap netcap@test"

    def doctor_env(self, hosts):
        env = self.install_env()
        (self.tmp / "home" / ".ssh").mkdir(exist_ok=True)
        (self.tmp / "home" / ".ssh" / "netcap.pub").write_text(self.PUB + "\n")
        (self.tmp / "remote" / ".ssh").mkdir(exist_ok=True)
        (self.conf / "hosts").write_text(hosts)
        return env

    def test_key_state(self):
        mod = load_netcap()
        # Whatever install writes passes, on every OS
        for os_ in ("mac", "linux", "win"):
            with self.subTest(os=os_):
                self.assertEqual(mod.key_state(mod.key_line(os_, self.PUB), "AAAAnetcap"), "ok")
        good = mod.key_line("mac", self.PUB)
        cases = {
            "ssh-ed25519 AAAAmine me@laptop\n" + good: "ok",
            self.PUB: "unrestricted",  # added by hand, no options
            "restrict " + self.PUB: "unrestricted",  # restrict alone still runs any command
            'command="/Library/PrivilegedHelperTools/netcap-agent" ' + self.PUB: "unrestricted",  # no restrict
            'restrict,command="/bin/sh" ' + self.PUB: "unrestricted",  # not the agent
            good + "\n" + self.PUB: "unrestricted",  # one bad line is enough
            "ssh-ed25519 AAAAmine me@laptop": "missing",
            "": "missing",
        }
        for text, want in cases.items():
            with self.subTest(text=text[:60]):
                self.assertEqual(mod.key_state(text, "AAAAnetcap"), want)

    def test_doctor(self):
        env = self.doctor_env("me mac -\nbox mac h-box\n")
        keys = self.tmp / "remote" / ".ssh" / "authorized_keys"
        good = load_netcap().key_line("mac", self.PUB)
        keys.write_text("ssh-ed25519 AAAAmine me@laptop\n" + good + "\n")
        p = self.netcap("doctor", env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertRegex(p.stdout, r"(?m)^box\s+ok\s+ok\s*$")
        self.assertRegex(p.stdout, r"(?m)^me\s+-\s+-\s+this machine")
        # -v shows the file it read and the options on the netcap key's line, then this controller
        p = self.netcap("doctor", "-v", env=env)
        self.assertIn("\n=== box\n", p.stdout)
        self.assertRegex(p.stdout, r"(?m)^  file +~/.ssh/authorized_keys$")
        self.assertIn(good.rsplit(" ", 3)[0], p.stdout)  # restrict,command="…"
        self.assertIn("\n=== this controller\n", p.stdout)
        self.assertRegex(p.stdout, r"(?m)^  config +" + re.escape(str(self.conf)) + "$")
        # A line added by hand without the forced command
        keys.write_text(self.PUB + "\n")
        p = self.netcap("doctor", "box", env=env)
        self.assertEqual(p.returncode, 1)
        self.assertRegex(p.stdout, r"(?m)^box\s+ok\s+unrestricted\s+~/.ssh/authorized_keys$")
        self.assertIn("WARNING: box", p.stdout)
        self.assertIn("\n  " + good + "\n", p.stdout)
        # Not registered
        keys.write_text("ssh-ed25519 AAAAmine me@laptop\n")
        p = self.netcap("doctor", "box", env=env)
        self.assertEqual(p.returncode, 1)
        self.assertIn("Run: netcap install box", p.stdout)
        self.assertEqual(json.loads(self.netcap("doctor", "box", "--json", env=env).stdout)[0]["key"], "missing")

    def test_doctor_windows_and_unreachable(self):
        env = self.doctor_env("gpc win h-gpc\ndown mac h-unreachable\n")
        (self.tmp / "remote" / "administrators_authorized_keys").write_text(
            load_netcap().key_line("win", self.PUB) + "\r\n")
        p = self.netcap("doctor", env=env)
        self.assertEqual(p.returncode, 1)  # one device could not be checked
        self.assertRegex(p.stdout, r"(?m)^gpc\s+ok\s+ok\s*$")
        self.assertRegex(p.stdout, r"(?m)^down\s+unreachable\s+\?\s")

    def test_doctor_without_a_key(self):
        self.hosts("off")
        p = self.netcap("doctor", env=self.install_env())
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("netcap install", p.stderr)

    # README: the name can be changed later
    def test_rename(self):
        self.hosts("off", "on", profiles="p  off=1/1  on=off  # off=2/2 stays in the comment\n")
        self.assertEqual(self.netcap("rename", "off", "zz").returncode, 0)
        self.assertEqual((self.conf / "hosts").read_text().split()[:3], ["zz", "mac", "h-off"])
        self.assertEqual((self.conf / "profiles").read_text(), "p  zz=1/1  on=off  # off=2/2 stays in the comment\n")
        self.assertNotEqual(self.netcap("rename", "zz", "on").returncode, 0)
        self.assertNotEqual(self.netcap("rename", "zz", "all").returncode, 0)

    def test_uninstall_config_only(self):
        self.hosts("off", "on", profiles="p  off=1/1\nq  off=off  on=off\n")
        p = self.netcap("uninstall", "off", "--config-only")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("off", (self.conf / "hosts").read_text())
        self.assertEqual((self.conf / "profiles").read_text(), "q  on=off\n")
        self.assertEqual(self.log.read_text(), "")

    # docs/configuration.md: Export and import
    def export(self, **edit):
        p = self.netcap("export")
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads(p.stdout)
        data.update(edit)
        f = self.tmp / "export.json"
        f.write_text(json.dumps(data))
        return data, f

    def import_into(self, f, *args):
        other = self.tmp / "other"
        other.mkdir(exist_ok=True)
        return self.netcap("import", str(f), *args, env={**self.env, "NETCAP_CONFIG_DIR": str(other)}), other

    def test_export_import_round_trip(self):
        self.hosts("off", "on", profiles="p  off=1/1  on=off\nq  on=0.5/2\n")
        (self.conf / "hosts").write_text((self.conf / "hosts").read_text() + "me mac -\n")
        data, f = self.export()
        self.assertEqual(data["hosts"][2], {"name": "me", "os": "mac", "route": None})
        self.assertEqual(data["profiles"], {"p": {"off": "1/1", "on": "off"}, "q": {"on": "0.5/2"}})
        p, other = self.import_into(f)
        self.assertEqual(p.returncode, 0, p.stderr)
        again = json.loads(self.netcap("export", env={**self.env, "NETCAP_CONFIG_DIR": str(other)}).stdout)
        self.assertEqual((again["hosts"], again["profiles"]), (data["hosts"], data["profiles"]))

    def test_export_has_no_keys(self):
        self.hosts("off")
        env = self.install_env()
        (self.tmp / "home" / ".ssh").mkdir()
        (self.tmp / "home" / ".ssh" / "netcap").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nsecret\n")
        out = self.netcap("export", env=env).stdout
        self.assertNotIn("PRIVATE", out)
        self.assertNotIn("secret", out)
        self.assertEqual(set(json.loads(out)), {"netcap", "exported_from", "hosts", "profiles"})

    # "This machine" (route -) of another machine is not taken over as this machine
    def test_import_skips_the_exporting_machine(self):
        self.hosts("off", profiles="p  me=1/1  off=off\nq  me=off\n")
        (self.conf / "hosts").write_text((self.conf / "hosts").read_text() + "me mac -\n")
        data, f = self.export(exported_from="somewhere-else")
        p, other = self.import_into(f)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("skipped me", p.stdout)
        self.assertEqual([l.split()[0] for l in (other / "hosts").read_text().splitlines() if not l.startswith("#")], ["off"])
        self.assertEqual([l for l in (other / "profiles").read_text().splitlines() if not l.startswith("#")], ["p  off=off"])

    def test_import_refuses_what_it_cannot_trust(self):
        self.hosts("off", profiles="p  off=1/1\n")
        data, f = self.export()
        bad = {
            "option as route": {"hosts": [{"name": "x", "os": "mac", "route": "-oProxyCommand=touch /tmp/pwned"}]},
            "space in route": {"hosts": [{"name": "x", "os": "mac", "route": "a b"}]},
            "bad os": {"hosts": [{"name": "x", "os": "dos", "route": "x"}]},
            "bad name": {"hosts": [{"name": "a b", "os": "mac", "route": "x"}]},
            "zero": {"profiles": {"p": {"off": "0/1"}}},
            "unknown device": {"profiles": {"p": {"nope": "off"}}},
            "not an export": {"hosts": "x"},
        }
        for why, edit in bad.items():
            with self.subTest(why=why):
                f.write_text(json.dumps({**data, **edit}))
                p, other = self.import_into(f)
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("cannot import", p.stderr)
                self.assertFalse((other / "hosts").exists())

    def test_hosts_refuses_an_option_as_route(self):
        (self.conf / "hosts").write_text("x mac -oProxyCommand=sh\n")
        p = self.netcap("status", "x")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("must not start with -", p.stderr)
        self.assertEqual(self.log.read_text(), "")

    def test_import_keeps_existing_config_unless_replace(self):
        self.hosts("off", profiles="p  off=1/1\n")
        data, f = self.export()
        other = self.tmp / "other"
        other.mkdir()
        (other / "hosts").write_text("mine mac -\n")
        p, _ = self.import_into(f)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("--replace", p.stderr)
        self.assertEqual((other / "hosts").read_text(), "mine mac -\n")
        p, _ = self.import_into(f, "--replace")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual((other / "hosts.bak").read_text(), "mine mac -\n")
        self.assertIn("off", (other / "hosts").read_text())

    # CONTRIBUTING.md: Language. Messages for people follow LC_ALL, LC_MESSAGES, LANG in that order
    def test_japanese_messages(self):
        self.hosts("off")
        env = {k: v for k, v in self.env.items() if k not in ("LC_ALL", "LC_MESSAGES")}
        ja = self.netcap("-h", env={**env, "LANG": "ja_JP.UTF-8"})
        self.assertIn("使い方:", ja.stdout)
        self.assertIn("上限を外す", ja.stdout)
        self.assertIn("知らない機器: nope", self.netcap("on", "nope", env={**env, "LANG": "ja_JP.UTF-8"}).stderr)
        self.assertIn("unknown host: nope", self.netcap("on", "nope", env={**env, "LANG": "ja_JP.UTF-8", "LC_ALL": "C"}).stderr)
        self.assertIn("show this help", self.netcap("-h", env={**env, "LANG": "en_US.UTF-8"}).stdout)

    # CONTRIBUTING.md: Language. What a machine reads is never translated
    def test_json_is_not_translated(self):
        self.hosts("off")
        env = {**self.env, "LC_ALL": "ja_JP.UTF-8"}
        self.assertEqual(self.netcap("status", "off", "--json", env=env).stdout,
                         self.netcap("status", "off", "--json").stdout)

    # CONTRIBUTING.md: Language. Every translation belongs to a message that still exists, with the same placeholders
    def test_translations_match_messages(self):
        mod = load_netcap()
        messages = {v for v in vars(mod).values() if isinstance(v, str)}
        for path in (NETCAP, Path(argparse.__file__)):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_" and node.args
                        and isinstance(node.args[0], ast.Constant)):
                    messages.add(node.args[0].value)
        placeholders = lambda s: sorted(re.findall(r"\{[^}]*\}|%\(\w+\)\w|%s", s))
        for en, ja in mod.JA.items():
            with self.subTest(en=en[:40]):
                self.assertIn(en, messages, "the English message is gone; remove or update its translation")
                self.assertEqual(placeholders(ja), placeholders(en))


class Stage(unittest.TestCase):
    # A git clone on Windows has CRLF (core.autocrlf=true), and bash on the device reads "set -eu\r" (#64)
    def test_macos_and_linux_files_go_out_with_lf(self):
        mod = load_netcap()
        src = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, src)
        for d in ("mac", "linux", "win"):
            shutil.copytree(ROOT / d, src / d)
        for f in src.rglob("*"):
            if f.is_file():
                f.write_bytes(f.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        with mock.patch.object(mod, "ROOT", src), mock.patch.object(mod, "version", lambda: "9.9.9"):
            out = mod.stage()
        self.addCleanup(shutil.rmtree, out)
        for d in ("mac", "linux"):
            for f in (out / d).rglob("*"):
                if f.is_file():
                    self.assertNotIn(b"\r", f.read_bytes(), f)
        self.assertIn(b"9.9.9", (out / "mac" / "netcap-agent").read_bytes())


def load_netcap():
    spec = importlib.util.spec_from_loader("netcap", importlib.machinery.SourceFileLoader("netcap", str(NETCAP)))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    unittest.main()
