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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NETCAP = ROOT / "bin" / "netcap"

# A fake ssh. The Host name decides the answer; each called Host is written to the log
FAKE_SSH = textwrap.dedent("""\
    #!/usr/bin/env python3
    import os, sys, time
    host, cmd = sys.argv[-2], sys.argv[-1]
    with open(os.environ["FAKE_SSH_LOG"], "a") as f:
        f.write(f"{host} {cmd}\\n")
    ok = "netshape state={s} up_mbit={u} down_mbit={u} down_src=applied pipes=2 rules=2"
    if host == "h-off":
        print(ok.format(s="off", u="-"))
    elif host == "h-on":
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
        self.log = self.tmp / "ssh.log"
        self.log.touch()
        self.conf = self.tmp / "conf"
        self.conf.mkdir()
        # LC_ALL=C: the assertions read English messages, whatever the locale of the machine running the tests
        self.env = {**os.environ, "PATH": f"{self.tmp / 'bin'}{os.pathsep}{os.environ['PATH']}",
                    "FAKE_SSH_LOG": str(self.log), "NETCAP_CONFIG_DIR": str(self.conf), "LC_ALL": "C"}

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
                     ["--version"], ["-v"]):
            with self.subTest(args=args):
                p = self.netcap(*args)
                self.assertNotIn("unrecognized arguments", p.stderr)
                self.assertNotIn("invalid choice", p.stderr)
                self.assertEqual(p.returncode, 0, p.stderr)

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

    # docs/host-setup.md: Reading the table, cap and note
    def test_cap_and_note(self):
        self.hosts("off", "on", "partial", "error")
        lines = {l.split()[0]: l for l in self.netcap("status", "all").stdout.splitlines()[2:] if l.strip()}
        self.assertRegex(lines["off"], r"^off\s+ok\s+off\s")
        self.assertRegex(lines["on"], r"^on\s+ok\s+on\s+2 Mbit/s\s+2 Mbit/s\*\s*$")
        self.assertRegex(lines["partial"], r"^partial\s+ok\s+partial\s")
        self.assertRegex(lines["error"], r"^error\s+error\s+\?\s.*last line of error$")

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


def load_netcap():
    spec = importlib.util.spec_from_loader("netcap", importlib.machinery.SourceFileLoader("netcap", str(NETCAP)))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


if __name__ == "__main__":
    unittest.main()
