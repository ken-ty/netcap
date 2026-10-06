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
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
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
    if host == "h-unreachable":
        print("ssh: Could not resolve hostname h-unreachable", file=sys.stderr); sys.exit(255)
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
    # What netcap doctor reads: the device's keys file, served from FAKE_REMOTE_HOME. h-keysfail cannot read it
    if host == "h-keysfail" and "cat ~/.ssh/authorized_keys" in cmd:
        print("cat: /home/x/.ssh/authorized_keys: Permission denied", file=sys.stderr); sys.exit(1)
    if host != "h-unreachable" and "~/.ssh/authorized_keys" in cmd:
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
    # Devices that keep their state in $FAKE_STATE/<host> ("off", "on UP DOWN", or "on UP DOWN left=SECONDS" for a
    # pending --for). check pings 40 ms when every other such device is capped, 400 ms otherwise. <host>.gone makes
    # the device unreachable, <host>.fail makes on and off fail, <host>.deny makes the agent refuse on and off (a key
    # allowed only status get check), and <host>.slow makes check take 3 seconds
    if host.startswith("h-s-"):
        state_dir = os.environ["FAKE_STATE"]
        st = os.path.join(state_dir, host)
        if os.path.exists(st + ".gone"):
            print(f"ssh: connect to host {host}: Operation timed out", file=sys.stderr); sys.exit(255)
        words = cmd.split()
        verb, args = (words[1], words[2:]) if len(words) > 1 else ("", [])
        if verb in ("on", "off") and os.path.exists(st + ".fail"):
            print("netshape: could not change the cap", file=sys.stderr); sys.exit(1)
        if verb in ("on", "off") and os.path.exists(st + ".deny"):
            print(f"netcap-agent: not allowed for this key: {verb}", file=sys.stderr); sys.exit(77)
        if verb == "on":
            left = ""
            if "--for" in args:
                left = " left=" + args[args.index("--for") + 1]
                args = args[:args.index("--for")]
            open(st, "w").write("on " + (" ".join(args) or "1 1") + left)
        elif verb == "off":
            open(st, "w").write("off")
        elif verb == "status":
            s = open(st).read().split() if os.path.exists(st) else ["off"]
            if s[0] == "on":
                timer = " until=1900000000 " + s[3] if len(s) > 3 else " until=- left=-"
                print(f"netshape state=on up_mbit={s[1]} down_mbit={s[2]} down_src=applied" + timer)
            else:
                print("netshape state=off up_mbit=- down_mbit=- down_src=applied until=- left=-")
        elif verb == "check":
            if os.path.exists(st + ".slow"):
                time.sleep(3)
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
        # No terminal on stdin, whoever runs the tests: install asks for a name only on a terminal
        return subprocess.run([sys.executable, str(NETCAP), *args], capture_output=True, text=True,
                              env=env or self.env, timeout=30, stdin=subprocess.DEVNULL)

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
                     ["status", "off", "-v"], ["--version"], ["-V"], ["protect", "--off"], ["help"], ["help", "on"],
                     ["help", "exit-codes"], ["version"], ["completion", "bash"], ["status", "off", "-q"]):
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
        self.assertIn("run netcap protect --off again", p.stderr)
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
                self.assertEqual(p.returncode, 2)
                self.assertIn(msg, p.stderr)
        self.assertEqual(self.netcap("protect", "game").returncode, 0)
        p = self.netcap("protect", "laptop")
        self.assertEqual(p.returncode, 1)
        self.assertIn("already protecting game", p.stderr)

    # docs/operations.md: Exit codes. Out of reach is 3, so a script can try again later
    def test_protect_stops_when_the_protected_device_is_unreachable(self):
        self.devices(game="off", laptop="off")
        (self.state / "h-s-game.gone").touch()
        p = self.netcap("protect", "game")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
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
                self.assertEqual(p.returncode, 2)
                self.assertIn("--load", p.stderr)
        self.assertEqual(self.device("laptop"), "off")

    # #91: check --bytes is capped at 100 MB, and a bad value is refused before anything is sent
    def test_check_bytes_range(self):
        self.devices(game="off")
        for bad in ("0", "100000001", "1e9", "-5", "x"):
            with self.subTest(bad=bad):
                p = self.netcap("check", "game", f"--bytes={bad}")
                self.assertEqual(p.returncode, 2)
                self.assertIn("--bytes", p.stderr)
        self.assertNotIn("check", self.log.read_text())
        self.assertEqual(self.netcap("check", "game", "--bytes", "100000000").returncode, 0)
        self.assertIn("check --bytes 100000000", self.log.read_text())

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

    # #88: what protect writes down is kept until every device is back, and never lost or overwritten
    def protect_state(self):
        return self.tmp / "netcap-state" / "protect.json"

    def test_protect_off_keeps_a_device_it_could_not_put_back(self):
        self.devices(game="off", laptop="off", server="off")
        self.assertEqual(self.netcap("protect", "game").returncode, 0)
        (self.state / "h-s-laptop.fail").touch()
        p = self.netcap("protect", "--off")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertEqual((self.device("laptop"), self.device("server")), ("on 1 1", "off"))
        self.assertIn("could not put laptop back", p.stderr)
        self.assertEqual(list(json.loads(self.protect_state().read_text())["before"]), ["laptop"])
        (self.state / "h-s-laptop.fail").unlink()
        p = self.netcap("protect", "--off")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.device("laptop"), "off")
        self.assertFalse(self.protect_state().exists())

    def test_protect_off_exits_3_when_only_unreachable_devices_are_left(self):
        self.devices(game="off", laptop="off", server="off")
        self.netcap("protect", "game")
        (self.state / "h-s-laptop.gone").touch()
        self.assertEqual(self.netcap("protect", "--off").returncode, 3)
        self.assertEqual(self.device("server"), "off")

    def test_protect_with_nothing_to_cap(self):
        self.devices(game="off", laptop="off", server="off")
        for n in ("laptop", "server"):
            (self.state / f"h-s-{n}.gone").touch()
        p = self.netcap("protect", "game")
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertNotIn("Traceback", p.stderr)
        self.assertIn("no other device can be capped", p.stderr)
        self.assertFalse(self.protect_state().exists())
        self.assertNotIn(" check", self.log.read_text())  # nothing measured either

    def test_rename_and_uninstall_refuse_a_device_protect_has_capped(self):
        self.devices(game="off", laptop="off")
        self.netcap("protect", "game")
        for args in (["rename", "laptop", "lap"], ["uninstall", "laptop", "--config-only"]):
            with self.subTest(args=args):
                p = self.netcap(*args)
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("First: netcap protect --off", p.stderr)
        self.assertIn("laptop", (self.conf / "hosts").read_text())
        self.netcap("protect", "--off")
        self.assertEqual(self.netcap("rename", "laptop", "lap").returncode, 0)

    def test_protect_off_keeps_a_device_no_longer_in_hosts(self):
        self.devices(game="off", laptop="off", server="off")
        self.netcap("protect", "game")
        hosts = self.conf / "hosts"
        hosts.write_text(hosts.read_text().replace("laptop ", "lap "))  # renamed by hand
        p = self.netcap("protect", "--off")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("laptop", p.stderr)
        self.assertEqual((self.device("laptop"), self.device("server")), ("on 1 1", "off"))
        self.assertEqual(list(json.loads(self.protect_state().read_text())["before"]), ["laptop"])
        hosts.write_text(hosts.read_text().replace("lap ", "laptop "))
        self.assertEqual(self.netcap("protect", "--off").returncode, 0)
        self.assertEqual(self.device("laptop"), "off")

    def test_protect_claims_the_state_before_it_measures(self):
        self.devices(game="off", laptop="off")
        (self.state / "h-s-game.slow").touch()
        first = subprocess.Popen([sys.executable, str(NETCAP), "protect", "game"], env=self.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(first.wait)
        for _ in range(40):
            if self.protect_state().exists():
                break
            time.sleep(0.05)
        self.assertTrue(self.protect_state().exists(), "no state while the first protect measures")
        self.assertIsNone(first.poll())
        self.assertEqual(self.device("laptop"), "off")  # still measuring before
        p = self.netcap("protect", "laptop")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("already protecting game", p.stderr)
        out, err = first.communicate(timeout=30)
        self.assertEqual(first.returncode, 0, out + err)
        self.assertEqual(json.loads(self.protect_state().read_text())["protected"], "game")
        self.assertEqual([f.name for f in self.protect_state().parent.iterdir()], ["protect.json"])  # no temp files

    def test_protect_stopped_before_capping_leaves_no_state(self):
        self.devices(game="off", laptop="off")
        (self.state / "h-s-game.slow").touch()
        first = subprocess.Popen([sys.executable, str(NETCAP), "protect", "game"], env=self.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for _ in range(40):
            if self.protect_state().exists():
                break
            time.sleep(0.05)
        first.send_signal(signal.SIGINT)
        first.communicate(timeout=30)
        self.assertNotEqual(first.returncode, 0)
        self.assertFalse(self.protect_state().exists())
        self.assertEqual(self.device("laptop"), "off")

    def test_protect_off_brings_back_the_time_left(self):
        self.devices(game="off", laptop="on 2 2 left=1740", server="on 3 3 left=0")
        self.netcap("protect", "game", "--up", "1", "--down", "1")
        self.assertEqual((self.device("laptop"), self.device("server")), ("on 1 1", "on 1 1"))
        p = self.netcap("protect", "--off")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertRegex(self.device("laptop"), r"^on 2 2 left=17[0-4][0-9]$")
        self.assertEqual(self.device("server"), "off")  # its deadline passed meanwhile: left lifted

    def test_protect_reports_a_corrupt_state(self):
        self.devices(game="off", laptop="off")
        self.protect_state().parent.mkdir(parents=True)
        for text in (b"{not json", b"[]", b'{"protected": "game"}', b"\xff\xfe"):
            self.protect_state().write_bytes(text)
            for args in (["protect", "game"], ["protect", "--off"]):
                with self.subTest(text=text, args=args):
                    p = self.netcap(*args)
                    self.assertEqual(p.returncode, 1)
                    self.assertNotIn("Traceback", p.stderr)
                    self.assertIn(str(self.protect_state()), p.stderr)
                    self.assertIn("netcap status", p.stderr)
        self.assertEqual(self.device("laptop"), "off")

    def test_protect_json_prints_only_json(self):
        self.devices(game="on 5 5", laptop="off", server="off")
        p = self.netcap("protect", "game", "--json")
        self.assertEqual(json.loads(p.stdout)["protected"], "game")
        self.assertIn("game itself is capped", p.stderr)
        (self.state / "h-s-server").write_text("on 5 5")  # changed by hand: --off says so
        p = self.netcap("protect", "--off", "--json")
        self.assertEqual([r["host"] for r in json.loads(p.stdout)], ["laptop"])
        self.assertIn("server changed since protect", p.stderr)
        p = self.netcap("protect", "--off", "--json")
        self.assertEqual(json.loads(p.stdout), [])
        self.assertIn("nothing to undo", p.stderr)

    # #69: help and version are subcommands too, like -h and --version
    def test_help_and_version_subcommands(self):
        self.hosts("on")
        p = self.netcap("help")
        self.assertEqual((p.returncode, p.stdout), (0, self.netcap("-h").stdout))
        p = self.netcap("help", "on")
        self.assertEqual(p.returncode, 0)
        self.assertIn("--for", p.stdout)
        self.assertEqual(self.netcap("help", "nosuch").returncode, 2)
        self.assertEqual(self.netcap("version").stdout, self.netcap("--version").stdout)
        p = self.netcap("help", "exit-codes")
        self.assertEqual(p.returncode, 0)
        for code in ("0", "1", "2", "3"):
            self.assertRegex(p.stdout, rf"(?m)^{code} ")

    # #69: -q drops hints and notes, before or after the subcommand; the table and errors stay
    def test_quiet(self):
        self.hosts("on")
        self.assertIn("to undo: netcap off on", self.netcap("on", "on").stdout)
        for args in (["-q", "on", "on"], ["on", "on", "-q"], ["on", "on", "--quiet"]):
            with self.subTest(args=args):
                out = self.netcap(*args).stdout
                self.assertNotIn("to undo", out)
                self.assertNotIn("* download is", out)
                self.assertRegex(out, r"(?m)^on\s+ok\s+on\s")

    # #69: docs/operations.md: Exit codes. 3 when every failure is a device out of reach, so a script can retry
    def test_exit_codes(self):
        for names, rc in ((["on"], 0), (["on", "unreachable"], 3), (["unreachable", "nosudo"], 1), (["denied"], 1)):
            with self.subTest(names=names):
                self.hosts(*names)
                self.assertEqual(self.netcap("status", "all").returncode, rc)
        self.assertEqual(self.netcap("status", "--bad").returncode, 2)
        self.assertEqual(self.netcap("on", "nosuchhost").returncode, 1)

    # #90: docs/operations.md: Exit codes. 2 is a bad command, flag, or argument, and nothing was sent
    def test_usage_errors_exit_2_and_send_nothing(self):
        self.hosts("on", "off", profiles="p  on=1/1\n")
        for args in (["on", "on", "--up", "2"], ["on", "on", "--up", "0", "--down", "1"], ["on", "on", "--for", "30s"],
                     ["set", "on"], ["set", "on", "--up", "1"], ["on", "on", "2", "2"], ["set", "on", "2", "2"],
                     ["protect"], ["protect", "all"], ["protect", "on", "--load", "99"], ["protect", "on", "--up", "2"],
                     ["protect", "on", "--up", "x", "--down", "1"], ["check", "on", "--bytes", "0"],
                     ["uninstall", "all"], ["rename", "on", "x y"], ["rename", "on", "all"], ["install", "a b"]):
            with self.subTest(args=args):
                p = self.netcap(*args)
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertNotIn("Traceback", p.stderr)
                self.assertEqual(self.log.read_text(), "")
        self.assertEqual((self.conf / "hosts").read_text(), "on mac h-on\noff mac h-off\n")
        # Found before the config is read: a missing hosts file does not turn them into 1
        (self.conf / "hosts").unlink()
        for args in (["on", "x", "--up", "2"], ["protect", "all"], ["uninstall", "all"], ["rename", "a", "x y"]):
            with self.subTest(args=args, hosts="none"):
                self.assertEqual(self.netcap(*args).returncode, 2)

    # #90: a wrong host, profile, or setting, and a refusal, stay 1
    def test_failures_that_are_not_usage_errors_exit_1(self):
        self.hosts("on", "off", profiles="p  on=1/1\nq  nope=1/1\n")
        for args in (["on", "nosuch"], ["use", "nosuch"], ["use", "q"], ["rename", "nosuch", "x"], ["rename", "on", "off"],
                     ["uninstall", "nosuch"], ["protect", "nosuch"]):
            with self.subTest(args=args):
                p = self.netcap(*args)
                self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
                self.assertNotIn("Traceback", p.stderr)
        self.assertEqual(self.log.read_text(), "")
        (self.conf / "hosts").unlink()
        self.assertEqual(self.netcap("status", "all").returncode, 1)

    # #90: use reports what on and off did on each device, not only the state read afterwards
    def test_use_reports_a_device_that_refuses(self):
        self.devices(game="off", laptop="off", server="off")
        (self.conf / "profiles").write_text("p  game=2/2  laptop=3/3  server=off\n")
        (self.state / "h-s-laptop.deny").touch()
        p = self.netcap("use", "p")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertRegex(p.stdout, r"(?m)^laptop\s+denied\s+\?\s.*not allowed for this key: on$")
        self.assertRegex(p.stdout, r"(?m)^game\s+ok\s+on\s+2 Mbit/s")
        self.assertEqual((self.device("game"), self.device("laptop")), ("on 2 2", "off"))
        rows = {r["host"]: r["reach"] for r in json.loads(self.netcap("use", "p", "--json").stdout)}
        self.assertEqual(rows, {"game": "ok", "laptop": "denied", "server": "ok"})
        (self.state / "h-s-laptop.deny").unlink()
        (self.state / "h-s-laptop.fail").touch()
        self.assertEqual(self.netcap("use", "p").returncode, 1)
        # Out of reach and nothing else: 3
        (self.state / "h-s-laptop.fail").unlink()
        (self.state / "h-s-laptop.gone").touch()
        self.assertEqual(self.netcap("use", "p").returncode, 3)

    # #90: docs/configuration.md: a bad value changes nothing. Every value is checked before anything is sent
    def test_use_checks_every_value_before_sending(self):
        self.devices(a="off", b="off")
        for profile in ("p  a=2/2  b=0/2\n", "p  b=0/2  a=2/2\n", "p  a=2/2  b=fast\n", "p  a=2/2  nope=1/1\n"):
            with self.subTest(profile=profile):
                self.log.write_text("")
                (self.state / "h-s-a").write_text("off")
                (self.conf / "profiles").write_text(profile)
                p = self.netcap("use", "p")
                self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
                self.assertEqual(self.log.read_text(), "")
                self.assertEqual(self.device("a"), "off")

    # #90: protect reports a device that refused the cap, and does not record it as capped
    def test_protect_reports_a_device_that_refuses(self):
        self.devices(game="off", laptop="off", server="off")
        (self.state / "h-s-laptop.deny").touch()
        p = self.netcap("protect", "game", "--up", "2", "--down", "2")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertRegex(p.stdout, r"(?m)^laptop\s+denied\s+\?\s.*not allowed for this key: on$")
        self.assertRegex(p.stdout, r"(?m)^server\s+ok\s+on\s")
        self.assertIn("could not cap laptop", p.stderr)
        self.assertEqual((self.device("laptop"), self.device("server")), ("off", "on 2 2"))
        self.assertEqual(json.loads(self.protect_state().read_text())["applied"], {"server": "2/2"})
        # --off puts back what protect capped; laptop was never capped, so there is nothing to put back
        (self.state / "h-s-laptop.deny").unlink()
        self.log.write_text("")
        p = self.netcap("protect", "--off")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((self.device("laptop"), self.device("server")), ("off", "off"))
        self.assertEqual([l.split()[2:] for l in self.log.read_text().splitlines() if l.startswith("h-s-laptop ")],
                         [["status"]])
        self.assertFalse(self.protect_state().exists())

    def test_protect_json_reports_a_device_that_failed(self):
        self.devices(game="off", laptop="off", server="off")
        (self.state / "h-s-laptop.fail").touch()
        p = self.netcap("protect", "game", "--json")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        rows = {r["host"]: r["reach"] for r in json.loads(p.stdout)["devices"]}
        self.assertEqual(rows, {"laptop": "error", "server": "ok"})
        # laptop was never capped: --off leaves it alone, even while it still fails
        p = self.netcap("protect", "--off")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((self.device("laptop"), self.device("server")), ("off", "off"))
        self.assertFalse(self.protect_state().exists())

    # #69: completion scripts for bash and zsh, with the subcommands and the names in hosts
    def test_completion(self):
        self.hosts("gamepc", "laptop")
        for shell in ("bash", "zsh"):
            with self.subTest(shell=shell):
                p = self.netcap("completion", shell)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn("complete -F _netcap netcap", p.stdout)
                for word in ("status", "protect", "--json", "--quiet", "exit-codes"):
                    self.assertIn(word, p.stdout)
                if shell == "zsh":
                    self.assertIn("bashcompinit", p.stdout)
        script = self.netcap("completion", "bash").stdout
        # The host names come from hosts when completing, not when the script was printed
        out = subprocess.run(["bash", "-c", script + '\nCOMP_WORDS=(netcap on ""); COMP_CWORD=2; _netcap; echo "${COMPREPLY[*]}"'],
                             capture_output=True, text=True, env=self.env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(sorted(out.stdout.split()), ["all", "gamepc", "laptop"])

    # #87: a name in hosts is never run as shell code when completing, whoever wrote the line.
    # /bin/bash is 3.2 on macOS; compgen -W expands the words it is given
    def test_completion_does_not_run_names(self):
        pwned = self.tmp / "pwned"
        (self.conf / "hosts").write_text(
            "laptop mac h-laptop\n"
            "$(echo${IFS}RAN-ON-TAB>&2) mac h-x\n"
            f"$(touch${{IFS}}{pwned}) mac h-y\n"
            "`touch${IFS}" + str(pwned) + "` mac h-z\n"
            "* mac h-glob\n")
        script = self.tmp / "completion.bash"
        script.write_text(self.netcap("completion", "bash").stdout
                          + 'COMP_WORDS=(netcap status ""); COMP_CWORD=2; _netcap; echo "${COMPREPLY[*]}"\n')
        bash = "/bin/bash" if os.path.exists("/bin/bash") else shutil.which("bash")
        out = subprocess.run([bash, str(script)], capture_output=True, text=True, env=self.env, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertNotIn("RAN-ON-TAB", out.stderr)
        self.assertFalse(pwned.exists())
        self.assertEqual(sorted(out.stdout.split()), ["all", "laptop"])

    def complete(self, script, *words):
        """What the bash completion offers for netcap <words>, the last one being the word under the cursor."""
        line = " ".join(shlex.quote(w) for w in ("netcap", *words))
        out = subprocess.run(["bash", "-c", script + f'\nCOMP_WORDS=({line}); COMP_CWORD={len(words)}; _netcap; '
                              'echo "${COMPREPLY[*]}"'],
                             capture_output=True, text=True, env=self.env)
        self.assertEqual(out.returncode, 0, out.stderr)
        return sorted(out.stdout.split())

    # #92: global options before the command, profile names for use, and all only where the command takes it
    def test_completion_words(self):
        self.hosts("gamepc", "laptop", profiles="# a comment\ngame  gamepc=off\nwork  laptop=2/2\n")
        script = self.netcap("completion", "bash").stdout
        hosts, every = ["gamepc", "laptop"], ["all", "gamepc", "laptop"]
        for words, want in ((["-q", "on", ""], every), (["--json", "status", ""], every), (["-v", "-q", "off", ""], every),
                            (["on", ""], every), (["doctor", ""], every),
                            (["protect", ""], hosts), (["uninstall", ""], hosts), (["rename", ""], hosts),
                            (["use", ""], ["game", "work"]), (["-q", "use", "w"], ["work"])):
            with self.subTest(words=words):
                self.assertEqual(self.complete(script, *words), want)
        self.assertIn("status", self.complete(script, "-q", ""))
        self.assertIn("--up", self.complete(script, "-q", "on", "--"))

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
                self.assertEqual(p.returncode, 2)
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
        # A flag is a usage error (2); a value in profiles is a setting (1)
        for args, rc in ((["on", "off", "--up", "0", "--down", "2"], 2), (["set", "off", "--up", "1", "--down", "0.0"], 2),
                         (["use", "z"], 1)):
            with self.subTest(args=args):
                p = self.netcap(*args)
                self.assertEqual(p.returncode, rc)
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

    # #90: a device out of reach is 3, so a script can try again later
    def test_install_out_of_reach(self):
        p = self.netcap("install", "box", "--ssh", "h-unreachable", env=self.install_env())
        self.assertEqual(p.returncode, 3, p.stdout + p.stderr)
        self.assertIn("cannot reach h-unreachable over ssh", p.stderr)
        self.assertFalse((self.conf / "hosts").exists())

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
        self.assertEqual(p.returncode, 3)  # the only device not checked was out of reach: try again later
        self.assertRegex(p.stdout, r"(?m)^gpc\s+ok\s+ok\s*$")
        self.assertRegex(p.stdout, r"(?m)^down\s+unreachable\s+\?\s")
        # A device without the key is a failure whatever else is out of reach
        (self.tmp / "remote" / "administrators_authorized_keys").write_text("")
        self.assertEqual(self.netcap("doctor", env=env).returncode, 1)

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

    # #87: exported_from went into a comment line of hosts and profiles unchecked; a newline in it added a line
    def test_import_refuses_a_bad_exported_from(self):
        self.hosts("off", profiles="p  off=1/1\n")
        data, f = self.export()
        for bad in (3, None, ["laptop"]):
            with self.subTest(bad=bad):
                f.write_text(json.dumps({**data, "exported_from": bad}))
                p, other = self.import_into(f, "--replace")
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("cannot import", p.stderr)
                self.assertFalse((other / "hosts").exists())

    # A machine's own name may break the name rule (a Japanese Windows host name): import it, but never write it
    def test_import_keeps_an_odd_exported_from_out_of_the_files(self):
        self.hosts("off", profiles="p  off=1/1\n")
        data, f = self.export()
        for odd in ("laptop\n$(echo${IFS}RAN-ON-TAB>&2) mac h-x-b", "戸倉のPC", "a b", ""):
            with self.subTest(odd=odd):
                f.write_text(json.dumps({**data, "exported_from": odd}))
                p, other = self.import_into(f, "--replace")
                self.assertEqual(p.returncode, 0, p.stderr)
                for name in ("hosts", "profiles"):
                    text = (other / name).read_text()
                    self.assertEqual(text.splitlines()[0], "# written by netcap import")
                    self.assertNotIn("RAN-ON-TAB", text)

    def test_import_writes_only_checked_lines(self):
        self.hosts("off", profiles="p  off=1/1\n")
        data, f = self.export(exported_from="laptop")
        p, other = self.import_into(f)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual((other / "hosts").read_text().splitlines()[0], "# written by netcap import from laptop")
        f.write_text(json.dumps({k: v for k, v in data.items() if k != "exported_from"}))
        p, other = self.import_into(f, "--replace")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual((other / "hosts").read_text().splitlines()[0], "# written by netcap import")

    # #87: hosts and profiles follow the same name rule as install, rename, and import, wherever the line came from
    def test_hosts_refuses_a_bad_name(self):
        for line in ("$(echo${IFS}X>&2) mac h-x", "-x mac h-x", "a/b mac h-x", "*  mac h-x"):
            with self.subTest(line=line):
                (self.conf / "hosts").write_text("off mac h-off\n" + line + "\n")
                p = self.netcap("status", "all")
                self.assertNotEqual(p.returncode, 0)
                self.assertIn(f"{self.conf / 'hosts'}:2:", p.stderr)
                self.assertIn("as a name", p.stderr)
                self.assertEqual(self.log.read_text(), "")

    def test_profiles_refuses_a_bad_name(self):
        for line in ("$(x)  off=1/1", "p  $(x)=1/1", "-p  off=off"):
            with self.subTest(line=line):
                self.hosts("off", profiles="ok  off=off\n" + line + "\n")
                p = self.netcap("profiles")
                self.assertNotEqual(p.returncode, 0)
                self.assertIn(f"{self.conf / 'profiles'}:2:", p.stderr)
                self.assertIn("as a name", p.stderr)

    def test_example_config_still_loads(self):
        shutil.copy(ROOT / "examples" / "hosts", self.conf / "hosts")
        shutil.copy(ROOT / "examples" / "profiles", self.conf / "profiles")
        p = self.netcap("profiles")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("game", p.stdout)

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

    # #92: install --ssh takes only a route hosts accepts. Before, ssh://h-new:2222 was installed and registered, and then
    # every command stopped on that hosts line, uninstall included
    def test_install_refuses_a_route_hosts_would_refuse(self):
        env = self.install_env()
        for dest in ("ssh://h-new:2222", "-", "h new"):
            with self.subTest(dest=dest):
                p = self.netcap("install", "box", f"--ssh={dest}", env=env)
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn("as a route", p.stderr)
                self.assertEqual(self.log.read_text(), "")
                self.assertFalse((self.conf / "hosts").exists())

    # #92: without a terminal, the name defaults to the host part of user@host, which follows the name rule
    def test_install_without_a_terminal_names_it_after_the_host(self):
        p = self.netcap("install", "--ssh", "me@h-new", env=self.install_env())
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual((self.conf / "hosts").read_text().split(), ["h-new", "mac", "me@h-new"])

    # #92: Windows PowerShell 5.1 writes a UTF-8 BOM (Set-Content -Encoding utf8). hosts, profiles, and an export read
    # the same with one
    def test_config_with_a_bom(self):
        bom = "﻿"
        (self.conf / "hosts").write_text(bom + "off mac h-off\non mac h-on\n", encoding="utf-8")
        (self.conf / "profiles").write_text(bom + "p  off=1/1\n", encoding="utf-8")
        p = self.netcap("status", "off", "--json")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)[0]["host"], "off")
        self.assertRegex(self.netcap("profiles").stdout, r"(?m)^p +off=1/1$")
        self.assertEqual(self.netcap("rename", "off", "zz").returncode, 0)
        self.assertEqual((self.conf / "hosts").read_text(encoding="utf-8").split()[:3], ["zz", "mac", "h-off"])
        self.assertIn("zz=1/1", (self.conf / "profiles").read_text(encoding="utf-8"))
        data, f = self.export()
        f.write_text(bom + json.dumps(data), encoding="utf-8")
        p, other = self.import_into(f)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("zz", (other / "hosts").read_text())
        # and the completion script reads the first name too
        script = self.netcap("completion", "bash").stdout
        (self.conf / "hosts").write_text(bom + "off mac h-off\n", encoding="utf-8")
        self.assertEqual(self.complete(script, "status", ""), ["all", "off"])

    # #92: a profile name twice is refused, as a host name twice is; netcap profiles shows every entry
    def test_profiles_refuses_a_name_twice_and_shows_every_entry(self):
        self.hosts("off", profiles="p  off=1/1\nq  off=off\np  off=2/2\n")
        p = self.netcap("profiles")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn(f"{self.conf / 'profiles'}:3: p appears twice", p.stderr)
        self.hosts("off", profiles="p  gone=1/1  off=off\n")
        p = self.netcap("profiles")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertRegex(p.stdout, r"(?m)^p +off=off  gone=1/1$")
        self.assertIn("not in hosts: gone", p.stdout)
        self.assertNotIn("not in hosts", self.netcap("profiles", "-q").stdout)

    # #92: when the keys file on the device cannot be read, uninstall does not guess that no other controller is left
    def test_uninstall_keeps_the_agent_when_the_keys_cannot_be_read(self):
        env = self.install_env()
        (self.conf / "hosts").write_text("box mac h-keysfail\n")
        p = self.netcap("uninstall", "box", env=env)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("could not read the keys on h-keysfail", p.stderr)
        self.assertIn("netcap uninstall box --config-only", p.stderr)
        self.assertNotIn("uninstall.sh", self.log.read_text())
        self.assertIn("box", (self.conf / "hosts").read_text())

    # #92: on Windows, administrators_authorized_keys cannot be read without Administrator. That is an error, not a
    # traceback, and not "no other controller"
    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root reads any file")
    def test_others_use_the_agent_when_the_local_keys_cannot_be_read(self):
        mod = load_netcap()
        keys = self.tmp / "ProgramData" / "ssh" / "administrators_authorized_keys"
        keys.parent.mkdir(parents=True)
        keys.write_text("restrict,command=\"powershell … netcap-agent.ps1\" ssh-ed25519 AAAAother netcap@other\n")
        keys.chmod(0)
        self.addCleanup(keys.chmod, 0o600)
        with mock.patch.dict(os.environ, ProgramData=str(self.tmp / "ProgramData")):
            self.assertIsNone(mod.others_use_the_agent(None, "win"))
            keys.chmod(0o600)
            self.assertTrue(mod.others_use_the_agent(None, "win"))

    # #92: running from a clone, the version is git describe without the v (no str.removeprefix: Python 3.8)
    def test_version_from_git(self):
        mod = load_netcap()
        done = subprocess.CompletedProcess([], 0, stdout="v0.12.0-3-gabc1234\n", stderr="")
        with mock.patch.object(mod.subprocess, "run", return_value=done):
            self.assertEqual(mod.version(), "0.12.0-3-gabc1234")
        self.assertNotIn(".removeprefix(", NETCAP.read_text(encoding="utf-8"))

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
