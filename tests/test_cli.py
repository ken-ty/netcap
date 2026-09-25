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
        scp = self.tmp / "bin" / "scp"
        scp.write_text("#!/bin/sh\necho \"scp $*\" >> \"$FAKE_SSH_LOG\"\n")
        scp.chmod(0o755)
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
        # uninstall takes both back
        self.assertEqual(self.netcap("uninstall", "box", env=env).returncode, 0)
        self.assertIn("/mac/uninstall.sh", self.log.read_text())
        self.assertEqual(self.remote_keys(), [])
        self.assertNotIn("box", (self.conf / "hosts").read_text())

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
