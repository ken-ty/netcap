"""Follow the README and docs on a real machine. CI runs the same tests on a matrix (macOS / Linux / Windows).

Installs the device side on this machine, writes only this machine into hosts, and drives it from the CLI.
It rewrites the machine's settings and needs sudo (Administrator on Windows), so it runs only with NETCAP_E2E=1.

  NETCAP_E2E=1 python3 -m unittest -v tests/test_e2e.py
"""
import base64
import hashlib
import http.server
import importlib.machinery
import importlib.util
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import shutil
import tempfile
import threading
import time
import unittest
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OS = {"darwin": "mac", "linux": "linux", "win32": "win"}.get(sys.platform)
AGENT = {"mac": "/Library/PrivilegedHelperTools/netcap-agent",
         "linux": "/usr/libexec/netcap/netcap-agent",
         "win": r"C:\ProgramData\netcap\netcap-agent.ps1"}.get(OS)
INSTALLED = {"mac": ["/Library/PrivilegedHelperTools/netcap-netshape", "/Library/PrivilegedHelperTools/netcap-agent",
                     "/usr/local/bin/netcap-check", "/etc/pf.anchors/netcap-netshape",
                     "/etc/sudoers.d/netcap-netshape", "/Library/LaunchDaemons/netcap-netshape.plist",
                     "/Library/PrivilegedHelperTools/netcap-netshape-expire.plist"],
             "linux": ["/usr/libexec/netcap/netcap-netshape", "/usr/libexec/netcap/netcap-agent",
                       "/usr/local/bin/netcap-check", "/etc/sudoers.d/netcap-netshape",
                       "/etc/systemd/system/netcap-netshape.service"],
             "win": [r"C:\ProgramData\netcap"]}.get(OS)
# docs/design.md: Destinations that pass through
LOCAL = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "224.0.0.0/4",
         "fc00::/7", "::1/128", "fe80::/10", "ff00::/8"]
PS = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
# Windows caps download only when installed with --with-download (docs/adr/0001-cap-download-on-windows.md). These tests
# install with it; tests/test_e2e_ssh.py installs without it and checks that download stays unsupported
WIN_DIR = r"C:\ProgramData\netcap"
WD = WIN_DIR + r"\windivert"


def sh(*cmd, env=None, input=None):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, input=input)


def install(boot="off", src=ROOT, download=True):
    if OS == "win":
        return sh(*PS, str(src / "win" / "install.ps1"), *(["-WithDownload"] if download else []))
    return sh("sudo", "bash", str(src / OS / "install.sh"), "--boot", boot)


def uninstall():
    if OS == "win":
        return sh(*PS, r"C:\ProgramData\netcap\uninstall.ps1")
    return sh("sudo", "bash", str(ROOT / OS / "uninstall.sh"))


def agent(*args, env=None):
    return sh(*(PS if OS == "win" else []), AGENT, *args, env=env)


# Windows PowerShell started from the CI runner fails to load Microsoft.PowerShell.Security, where Get-Acl lives
# (CouldNotAutoloadMatchingModule), so the tests read ACLs through .NET: (Get-Item …).GetAccessControl()
def ps(script):
    enc = base64.b64encode(script.encode("utf-16-le")).decode()  # no quoting layer for the script
    return sh("powershell", "-NoProfile", "-EncodedCommand", enc)


# Bits that let a principal change a file or folder: write data, append, write attributes and extended attributes,
# delete (also children), change permissions, take ownership, and generic all / write
WIN_WRITE = 0x500D0156


def win_acl(d):
    """One line per entry under d ("entry <name>"), and one per problem: an owner other than Administrators, or a
    principal other than SYSTEM and Administrators that may write ("bad <name> …"). d itself is named ."""
    p = ps(f"""$d = '{d}'
foreach ($i in @(Get-Item -LiteralPath $d -Force) + @(Get-ChildItem -LiteralPath $d -Force -Recurse)) {{
  $name = $i.FullName.Substring($d.Length).TrimStart('\\'); if (-not $name) {{ $name = '.' }}
  "entry $name"
  $acl = $i.GetAccessControl()
  $owner = $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
  if ($owner -ne 'S-1-5-32-544') {{ "bad $name owner $owner" }}
  foreach ($r in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {{
    $sid = $r.IdentityReference.Value
    if ($r.AccessControlType -eq 'Allow' -and ([int64]$r.FileSystemRights -band {WIN_WRITE}) -and
        $sid -notin 'S-1-5-18', 'S-1-5-32-544') {{ "bad $name $sid $($r.FileSystemRights)" }}
  }}
}}
""")
    assert p.returncode == 0, p.stdout + p.stderr
    return p.stdout.splitlines()


def win_task(name):
    p = ps(f"if (Get-ScheduledTask -TaskPath '\\netcap\\' -TaskName {name} -ErrorAction SilentlyContinue) {{ 'yes' }}")
    return p.stdout.strip() == "yes"


def shaper_state():
    """download.state of the WinDivert shaper as a dict ({} when it does not hold a handle)"""
    f = Path(WIN_DIR) / "download.state"
    text = f.read_text() if f.exists() else ""
    return dict(kv.split("=", 1) for kv in text.split())


def process_alive(pid):
    return ps(f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ 'yes' }}").stdout.strip() == "yes"


def shaper_cpu():
    pid = shaper_state().get("pid")
    return float(ps(f"(Get-Process -Id {pid}).TotalProcessorTime.TotalSeconds").stdout.strip()) if pid else 0.0


def driver_state():
    """What Windows says about the WinDivert driver: the service's state, and whether it is marked for deletion"""
    return ps(r"""$s = Get-Service WinDivert -ErrorAction SilentlyContinue
$k = Get-ItemProperty HKLM:\SYSTEM\CurrentControlSet\Services\WinDivert -ErrorAction SilentlyContinue
"service=$(if ($s) { $s.Status } else { 'none' }) start=$(if ($k) { $k.Start } else { '-' }) delete_flag=$(if ($k) { $k.DeleteFlag } else { '-' })"
""").stdout.strip()


@unittest.skipUnless(os.environ.get("NETCAP_E2E") and OS, "only with NETCAP_E2E=1 (rewrites the machine's settings)")
class E2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if OS == "mac":  # upgrade from the v0.5.0 old name (docs/host-setup.md)
            old = Path(tempfile.mkdtemp())
            subprocess.run(f"git -C {ROOT} archive v0.5.0 mac | tar -x -C {old}", shell=True, check=True)
            install("on", src=old)
        # README: Quick Start. netcap install puts the agent on this machine and registers it in hosts
        cls.conf = Path(tempfile.mkdtemp())
        cls.env = {**os.environ, "NETCAP_CONFIG_DIR": str(cls.conf)}
        cls.installed = sh(sys.executable, str(ROOT / "bin" / "netcap"), "install", "self", "--boot", "off",
                           *(["--with-download"] if OS == "win" else []), env=cls.env)
        (cls.conf / "profiles").write_text("p     self=2/3\nnone  self=off\n")

    @classmethod
    def tearDownClass(cls):
        agent("off")
        uninstall()

    def netcap(self, *args):
        p = sh(sys.executable, str(ROOT / "bin" / "netcap"), *args, env=self.env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p.stdout

    def row(self, cmd="status"):
        return json.loads(self.netcap(cmd, "self", "--json"))[0]

    def assertCap(self, state, up="-", down="-"):
        r = self.row()
        self.assertEqual(r["reach"], "ok", r)
        self.assertEqual(r["state"], state, r)
        self.assertEqual(r["up_mbit"], up, r)
        self.assertEqual(r["down_mbit"], down, r)
        if OS == "win":  # WinDivert holds download back, from a process that runs only while the cap is on
            self.assertEqual(r["down_src"], "windivert", r)
            self.assertEqual(r["shaper"], {"on": "running", "off": "none"}.get(state, r["shaper"]), r)

    def assertGone(self, path):
        """path was removed. A loaded driver's file cannot be: on Windows, WinDivert64.sys alone may stay, with the task
        that removes it at the next startup (netcap never unloads the driver, basil00/WinDivert#406)"""
        left = sorted(p.name for p in Path(path).rglob("*") if p.is_file()) if Path(path).exists() else []
        if OS == "win" and left:
            self.assertEqual(left, ["WinDivert64.sys"], path)
            self.assertTrue(win_task("cleanup"))
            print(f"\n  {path}: WinDivert64.sys is left for the next startup (driver: {driver_state()})")
        else:
            self.assertFalse(Path(path).exists(), path)

    def assertDefault(self, up, down):
        r = self.row("get")
        self.assertEqual((r["default_up"], r["default_down"]), (up, down), r)

    # --- hosts: README Usage ---
    def test_00_install(self):
        self.assertEqual(self.installed.returncode, 0, self.installed.stdout + self.installed.stderr)
        self.assertEqual((self.conf / "hosts").read_text().split(), ["self", OS, "-"])
        self.assertIn("netcap off self", self.installed.stdout)
        # The agent reports the version of the CLI that installed it
        self.assertEqual("netcap " + self.row("get")["agent"], self.netcap("--version").strip())
        if OS == "mac":
            self.assertIn("removed the old name (ken-ty-netshape)", self.installed.stdout)
            self.assertFalse(Path("/Library/PrivilegedHelperTools/ken-ty-netshape").exists())

    def test_01_get(self):
        self.assertDefault("1", "1")
        self.assertEqual(self.row("get")["boot"], "keep" if OS == "win" else "off")

    def test_02_on_default(self):
        self.netcap("on", "self")
        self.assertCap("on", "1", "1")

    def test_03_on_flags_are_this_time_only(self):
        self.netcap("on", "self", "--up", "2", "--down", "3")
        self.assertCap("on", "2", "3")
        self.assertDefault("1", "1")

    def test_04_set_rewrites_default_and_reapplies(self):
        self.netcap("set", "self", "--up", "4", "--down", "5")
        self.assertDefault("4", "5")
        self.assertCap("on", "4", "5")

    def test_05_off(self):
        self.netcap("off", "self")
        self.assertCap("off")

    # #29: on --for. The device lifts the cap by itself at the deadline, with no controller involved
    def timer_loaded(self):
        if OS == "mac":
            return sh("sudo", "launchctl", "print", "system/netcap-netshape-expire").returncode == 0
        if OS == "win":
            return sh("powershell", "-NoProfile", "-Command", "if (Get-ScheduledTask -TaskPath '\\netcap\\' -TaskName expire "
                      "-ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }").returncode == 0
        return sh("systemctl", "is-active", "netcap-netshape-expire.timer").stdout.strip() == "active"

    def test_07_on_for_lifts_itself(self):
        p = agent("on", "2", "3", "--for", "60")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        r = self.row()
        self.assertEqual(r["state"], "on", r)
        self.assertTrue(0 < int(r["left"]) <= 60, r)
        self.assertTrue(self.timer_loaded())
        deadline = time.time() + 150  # macOS checks once a minute
        while time.time() < deadline and self.row()["state"] != "off":
            time.sleep(5)
        self.assertCap("off")
        self.assertEqual(self.row()["left"], "-")
        self.assertFalse(self.timer_loaded())
        if OS == "win":
            self.assertFalse(win_task("download"))

    def test_08_later_on_and_off_replace_the_timer(self):
        for undo in (("on",), ("off",)):
            with self.subTest(undo=undo[0]):
                self.assertEqual(agent("on", "--for", "600").returncode, 0)
                self.assertTrue(self.timer_loaded())
                self.assertEqual(agent(*undo).returncode, 0)
                self.assertEqual(self.row()["left"], "-")
                self.assertFalse(self.timer_loaded())
        agent("off")

    def test_09_set_keeps_the_timer(self):
        self.assertEqual(agent("on", "--for", "600").returncode, 0)
        try:
            self.assertEqual(agent("set", "4", "5").returncode, 0)  # the default test_04 left
            r = self.row()
            self.assertEqual((r["state"], r["up_mbit"]), ("on", "4"), r)
            self.assertTrue(0 < int(r["left"]) <= 600, r)
        finally:
            agent("off")

    def test_06_status_all(self):
        self.assertEqual([r["host"] for r in json.loads(self.netcap("status", "all", "--json"))], ["self"])

    # --- profiles: docs/configuration.md ---
    def test_10_profiles(self):
        out = self.netcap("profiles")
        self.assertRegex(out, r"(?m)^p\s+self=2/3$")
        self.assertRegex(out, r"(?m)^none\s+self=off$")

    def test_11_use(self):
        self.assertIn("profile: p", self.netcap("use", "p"))
        self.assertCap("on", "2", "3")
        self.netcap("use", "none")
        self.assertCap("off")

    # docs/configuration.md: decimals work. macOS dnctl read 0.5 as unlimited and 08 as 0 (#86)
    def test_12_decimal_and_zero_padded(self):
        try:
            for value, want in (("0.5", "0.5"), ("08", "8")):
                with self.subTest(value=value):
                    p = agent("on", value, value)
                    self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                    r = self.row()
                    print(f"\n  on {value} {value}: state={r['state']} up_mbit={r['up_mbit']} down_mbit={r['down_mbit']}")
                    self.assertCap("on", want, want)
            if OS == "mac":  # dummynet holds bit/s in a 32-bit int: refused before anything changes
                p = agent("on", "2148", "1")
                self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
                self.assertIn("2147.483647", p.stderr)
                self.assertCap("on", "8", "8")
        finally:
            agent("off")

    # #92: pf disabled by something else (pfctl -d) leaves the rules loaded but not in effect. status does not call that
    # on, and on enables pf again even though netcap still holds its token from before
    @unittest.skipUnless(OS == "mac", "pf is macOS")
    def test_13_pf_disabled_by_something_else(self):
        self.netcap("on", "self", "--up", "2", "--down", "3")
        try:
            p = sh("sudo", "pfctl", "-d")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertEqual(self.row()["state"], "partial")
            self.netcap("on", "self", "--up", "2", "--down", "3")
            self.assertIn("Status: Enabled", sh("sudo", "pfctl", "-s", "info").stdout)
            self.assertCap("on", "2", "3")
        finally:
            self.netcap("off", "self")

    # #92: a deadline whose first expire fails is tried again, instead of leaving the cap on for good
    @unittest.skipUnless(OS == "linux", "macOS runs expire every minute; this is the Linux timer")
    def test_14_failed_expire_is_retried(self):
        shaper = "/usr/libexec/netcap/netcap-netshape"
        failed = "/run/netcap-e2e-expire-failed"
        # The first expire fails: a wrapper in the shaper's place fails once, then runs the real one
        wrapper = (f'#!/bin/bash\nif [ "$1" = expire ] && [ ! -e {failed} ]; then touch {failed}; exit 1; fi\n'
                   f'exec {shaper}.real "$@"\n')
        self.assertEqual(sh("sudo", "cp", "-p", shaper, shaper + ".real").returncode, 0)
        try:
            self.assertEqual(sh("sudo", "tee", shaper, input=wrapper).returncode, 0)
            p = agent("on", "2", "3", "--for", "60")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            deadline = time.time() + 210  # the deadline, a failed expire, and a retry a minute later
            while time.time() < deadline and self.row()["state"] != "off":
                time.sleep(5)
            self.assertTrue(Path(failed).exists(), "the first expire did not run")
            self.assertCap("off")
        finally:
            sh("sudo", "mv", shaper + ".real", shaper)
            sh("sudo", "rm", "-f", failed)
            agent("off")

    # docs/configuration.md: Export and import (on this machine, "self" is kept)
    def test_15_export_import(self):
        out = self.netcap("export")
        other = Path(tempfile.mkdtemp())
        p = sh(sys.executable, str(ROOT / "bin" / "netcap"), "import", "-", env={**self.env, "NETCAP_CONFIG_DIR": str(other)},
               input=out)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        again = json.loads(sh(sys.executable, str(ROOT / "bin" / "netcap"), "export",
                              env={**self.env, "NETCAP_CONFIG_DIR": str(other)}).stdout)
        self.assertEqual((again["hosts"], again["profiles"]), (json.loads(out)["hosts"], json.loads(out)["profiles"]))

    # --- permissions: docs/host-setup.md ---
    def test_20_forced_command_denies(self):
        p = agent("--allow", "status get", env={**os.environ, "SSH_ORIGINAL_COMMAND": f"{AGENT} on"})
        self.assertNotEqual(p.returncode, 0)
        self.assertRegex(p.stderr, r"^netcap-agent: .*on")

    def test_21_args_are_not_shell(self):
        p = agent("--allow", "on", env={**os.environ, "SSH_ORIGINAL_COMMAND": "on $(id) 1"})
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("netcap-agent: arguments must be numbers", p.stderr)

    # docs/configuration.md: 0 is an error and changes nothing, also for a controller that skips the CLI's check
    def test_22_zero_is_refused(self):
        p = agent("--allow", "on", env={**os.environ, "SSH_ORIGINAL_COMMAND": f"{AGENT} on 0 1"})
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("netcap-agent: arguments must be greater than 0", p.stderr)

    # The forced command receives exactly what the CLI sends over ssh (on Windows, a quoted path)
    def test_23_forced_command_accepts_the_cli(self):
        spec = importlib.util.spec_from_loader("netcap", importlib.machinery.SourceFileLoader("netcap", str(ROOT / "bin" / "netcap")))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.HOSTS["dev"] = {"os": OS, "ssh": "dev"}
        p = agent("--allow", "status", env={**os.environ, "SSH_ORIGINAL_COMMAND": mod.build_cmd("dev", "status", [])[-1]})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(p.stdout.startswith("netshape "), p.stdout)

    # Windows' sshd runs the forced command through cmd.exe unless DefaultShell is set, and cmd.exe does not group
    # '…': the agent gets --allow 'status get' as two words with the quotes on them (#57)
    @unittest.skipUnless(OS == "win", "only cmd.exe leaves the quotes to the agent")
    def test_24_allow_split_by_cmd(self):
        p = agent("--allow", "'status", "get'", env={**os.environ, "SSH_ORIGINAL_COMMAND": f"{AGENT} status"})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(p.stdout.startswith("netshape "), p.stdout)
        p = agent("--allow", "'status", "get'", env={**os.environ, "SSH_ORIGINAL_COMMAND": f"{AGENT} on"})
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("netcap-agent: not allowed for this key: on", p.stderr)

    # on takes --for <seconds> only at its end, and no other verb takes it (#29)
    def test_25_for_args(self):
        for cmd in ("on --for abc", "on --for 1800 2 3", "on 2 3 --for 1 --for 2", "off --for 60", "on --for 0"):
            with self.subTest(cmd=cmd):
                p = agent("--allow", "on off", env={**os.environ, "SSH_ORIGINAL_COMMAND": f"{AGENT} {cmd}"})
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("netcap-agent: ", p.stderr)

    # A read-only key cannot make the device transfer more than 100 MB (#91). Both the agent and netcap-check refuse
    def test_26_check_bytes_limit(self):
        for cmd in ("check --bytes 100000001", "check --bytes 9999999999999999999999", "check --bytes 0"):
            with self.subTest(cmd=cmd):
                p = agent("--allow", "status get check", env={**os.environ, "SSH_ORIGINAL_COMMAND": f"{AGENT} {cmd}"})
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("netcap-agent: check accepts only --bytes", p.stderr)
        p = agent("--allow", "status get check", env={**os.environ, "SSH_ORIGINAL_COMMAND": f"{AGENT} check --bytes 1000"})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertRegex(p.stdout, r"^netcheck .*bytes=1000$")
        check = {"mac": ["/usr/local/bin/netcap-check"], "linux": ["/usr/local/bin/netcap-check"],
                 "win": [*PS, r"C:\ProgramData\netcap\netcap-check.ps1"]}[OS]
        p = sh(*check, "--bytes", "100000001")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertEqual(p.stdout, "")

    # #92: only on and set take numbers. Before, status 5 reached sudo, whose sudoers refused it as a password prompt
    def test_27_verbs_without_arguments(self):
        for cmd in (("status", "5"), ("get", "1"), ("off", "1")):
            with self.subTest(cmd=cmd):
                p = agent(*cmd)
                self.assertNotEqual(p.returncode, 0, p.stdout)
                self.assertIn(f"netcap-agent: {cmd[0]} takes no arguments", p.stderr)

    # --- docs/design.md ---
    def test_30_touches_only_its_own(self):
        self.netcap("on", "self")
        try:
            if OS == "mac":
                self.assertIn("pipe 1", sh("sudo", "pfctl", "-a", "com.apple/netcap-netshape", "-s", "dummynet").stdout)
                self.assertIn('dummynet-anchor "com.apple/*"', sh("sudo", "pfctl", "-s", "dummynet").stdout)
            elif OS == "linux":
                dev = re.search(r" dev (\S+)", sh("ip", "route", "get", "1.1.1.1").stdout).group(1)
                self.assertRegex(sh("tc", "qdisc", "show", "dev", dev).stdout, r"qdisc htb ca9: root")
                self.assertRegex(sh("tc", "qdisc", "show", "dev", "ifb-netcap").stdout, r"qdisc htb \S+ root")
                self.netcap("off", "self")
                self.assertNotIn("ca9:", sh("tc", "qdisc", "show", "dev", dev).stdout)
                self.assertNotEqual(sh("ip", "link", "show", "ifb-netcap").returncode, 0)
            else:
                ps = sh("powershell", "-NoProfile", "-Command",
                        "Get-NetQosPolicy | Where-Object Name -like 'netcap-*' | "
                        "ForEach-Object { \"$($_.Name) $($_.IPDstPrefixMatchCondition) $($_.IPDstPortStartMatchCondition)\" }").stdout
                # Windows may write a prefix its own way (::1/128 comes back as ::1), so compare the networks
                held = {ipaddress.ip_network(l.split()[1]) for l in ps.splitlines() if l.startswith("netcap-local-")}
                self.assertEqual(held, {ipaddress.ip_network(n) for n in LOCAL}, ps)
                self.assertRegex(ps, r"netcap-dns\s+53")
        finally:
            self.netcap("off", "self")

    def test_31_root_only(self):
        if OS == "win":
            acl = ps(r"(Get-Item C:\ProgramData\netcap).GetAccessControl().Access | "
                     r"Where-Object { $_.IdentityReference -match 'Users$' } | ForEach-Object { $_.FileSystemRights }")
            self.assertIn("ReadAndExecute", acl.stdout, acl.stderr)  # it was read, and Users may still read
            self.assertNotRegex(acl.stdout, r"Write|Modify|FullControl")
        else:
            body = AGENT.replace("netcap-agent", "netcap-netshape")
            st = sh("stat", "-f", "%u %Lp", body) if OS == "mac" else sh("stat", "-c", "%u %a", body)
            self.assertEqual(st.stdout.strip(), "0 755")

    # #89: Users can create C:\ProgramData\netcap before the install, so install.ps1 may find a folder someone else owns,
    # with entries of their own on it and on files in it. Afterwards only SYSTEM and Administrators may write, and
    # Administrators own the folder and everything in it
    @unittest.skipUnless(OS == "win", "C:\\ProgramData is where Users can create folders")
    def test_33_install_takes_over_an_existing_folder(self):
        d = r"C:\ProgramData\netcap"
        planted = [d + r"\netshape.ps1", d + r"\planted.ps1", d + r"\sub\planted.ps1"]
        setup = (f"$d = '{d}'; New-Item -ItemType Directory -Force \"$d\\sub\" | Out-Null\n"
                 "Set-Content -LiteralPath \"$d\\planted.ps1\" -Value x; Set-Content -LiteralPath \"$d\\sub\\planted.ps1\" -Value x\n"
                 "function run { & icacls.exe @args | Out-Null; if ($LASTEXITCODE) { throw \"icacls $($args -join ' ') failed ($LASTEXITCODE)\" } }\n"
                 # Everyone may change the folders, and the files carry only that entry (inheritance cut)
                 "foreach ($p in $d, \"$d\\sub\") { run $p /grant '*S-1-1-0:(OI)(CI)F' }\n"
                 + "".join(f"run '{p}' /inheritance:r /grant '*S-1-1-0:F'\n" for p in planted)
                 # owned by Users, a principal other than Administrators
                 + "".join(f"run '{p}' /setowner '*S-1-5-32-545'\n" for p in [d, d + r"\sub", *planted]))
        p = ps(setup)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        try:
            before = win_acl(d)
            self.assertIn(r"bad sub\planted.ps1 owner S-1-5-32-545", before)
            self.assertIn("bad . S-1-1-0 FullControl", before)
            p = install()
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            after = win_acl(d)
            self.assertIn(r"entry sub\planted.ps1", after)  # taken over, not skipped
            self.assertEqual([l for l in after if l.startswith("bad ")], [], "\n".join(after))
            self.assertEqual(self.row()["reach"], "ok")
        finally:
            ps(f"Remove-Item -Recurse -Force -LiteralPath '{d}\\sub', '{d}\\planted.ps1'")

    # A link in the folder would send the copy or the new ACL somewhere else: install refuses it and changes nothing there
    @unittest.skipUnless(OS == "win", "C:\\ProgramData is where Users can create folders")
    def test_34_install_refuses_a_link(self):
        target, link = tempfile.mkdtemp(), r"C:\ProgramData\netcap\elsewhere"
        self.assertEqual(sh("cmd", "/c", "mklink", "/J", link, target).returncode, 0)
        sddl = f"(Get-Item -LiteralPath '{target}').GetAccessControl().Sddl"
        try:
            before = ps(sddl).stdout
            self.assertIn("D:", before)
            p = install()
            self.assertNotEqual(p.returncode, 0, p.stdout)
            self.assertIn(f"{link} is a link", p.stderr)
            self.assertEqual(ps(sddl).stdout, before)
        finally:
            sh("cmd", "/c", "rmdir", link)
        p = install()
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    # The default route can be gone for a moment: systemd-networkd drops it while it restarts (#42). on waits for it
    @unittest.skipUnless(OS == "linux", "the route lookup with a wait is in the Linux shaper")
    def test_32_on_waits_for_the_default_route(self):
        route = sh("ip", "-4", "route", "show", "default").stdout.splitlines()[0].split()
        self.assertEqual(sh("sudo", "ip", "route", "del", *route).returncode, 0)
        try:
            p = subprocess.Popen([sys.executable, str(ROOT / "bin" / "netcap"), "on", "self", "--up", "2", "--down", "3"],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=self.env)
            time.sleep(0.5)
        finally:
            sh("sudo", "ip", "route", "replace", *route)
        try:
            out = p.communicate(timeout=30)[0]
            self.assertEqual(p.returncode, 0, out)
            self.assertCap("on", "2", "3")
        finally:
            self.netcap("off", "self")

    # --- measurement: does the cap really work (top of the README) ---
    def test_35_cap_really_limits(self):
        def check(n):
            r = json.loads(self.netcap("check", "self", "--bytes", str(n), "--json"))[0]
            return float(r["down_mbit"]), float(r["up_mbit"])

        free = check(4_000_000)
        if min(free) < 5:
            self.skipTest(f"this line is too slow to compare even without a cap: down {free[0]} / up {free[1]} Mbit/s")
        self.netcap("on", "self", "--up", "1", "--down", "1")
        try:
            cpu = shaper_cpu() if OS == "win" else 0
            capped = check(500_000)  # 4 seconds at 1 Mbit/s
            if OS == "win":
                print(f"\n  WinDivert shaper CPU during the check: {shaper_cpu() - cpu:.2f} s")
            # to see which path the traffic took when this fails
            diag = "" if OS != "linux" else sh("bash", "-c", "ip -br link; tc qdisc show; for d in $(ls /sys/class/net); do "
                                               "tc -s filter show dev $d parent ffff:fff2; tc -s filter show dev $d parent ffff:; "
                                               "done; tc -s class show dev ifb-netcap").stdout
        finally:
            self.netcap("off", "self")
        print(f"\n  no cap: down {free[0]} / up {free[1]}; at 1/1: down {capped[0]} / up {capped[1]} Mbit/s")
        self.assertLess(capped[1], 1.5)
        self.assertLess(capped[0], 1.5, diag)

    # docs/design.md: ping passes through. NetQosPolicy cannot match ICMP, so this is measured, not read from the rules.
    # One 1400-byte echo in flight at a time: under a 0.1 Mbit/s cap each one would wait about 110 ms more on the way out
    @unittest.skipUnless(OS == "win", "macOS and Linux exempt ICMP by rule (tests/test_files.py)")
    def test_36_icmp_passes_on_windows(self):
        script = """$p = New-Object System.Net.NetworkInformation.Ping; $buf = New-Object byte[] 1400
$rtt = @(); $lost = 0; $end = (Get-Date).AddSeconds(10)
while ((Get-Date) -lt $end) {
  $t = Get-Date
  try { $r = $p.Send('1.1.1.1', 2000, $buf) } catch { $r = $null }
  if ($r -and $r.Status -eq 'Success') { $rtt += $r.RoundtripTime } else { $lost++ }
  if ($rtt.Count -eq 0 -and $lost -ge 5) { break }
  $w = 50 - ((Get-Date) - $t).TotalMilliseconds; if ($w -gt 0) { Start-Sleep -Milliseconds $w }
}
$s = @($rtt | Sort-Object); "$($s.Count) $lost $(if ($s.Count) { $s[[int]($s.Count / 2)] } else { -1 })"
"""

        def pings():
            enc = base64.b64encode(script.encode("utf-16-le")).decode()  # no quoting layer for the script
            got, lost, med = map(int, sh("powershell", "-NoProfile", "-EncodedCommand", enc).stdout.split()[-3:])
            return got, lost / max(got + lost, 1), med

        free = pings()
        if free[0] < 20 or free[1] > 0.2:
            self.skipTest(f"ICMP to 1.1.1.1 does not get through here: {free[0]} replies, {free[1]:.0%} lost")
        self.netcap("on", "self", "--up", "0.1", "--down", "0.1")
        try:
            capped = pings()
            # The cap is on: TCP upload is held near 0.1 Mbit/s
            up = float(json.loads(self.netcap("check", "self", "--bytes", "50000", "--json"))[0]["up_mbit"])
        finally:
            self.netcap("off", "self")
        print(f"\n  ICMP 1400 B: no cap {free[0]} replies, {free[1]:.0%} lost, median {free[2]} ms; "
              f"at 0.1 Mbit/s {capped[0]} replies, {capped[1]:.0%} lost, median {capped[2]} ms; TCP up {up} Mbit/s")
        self.assertLess(up, 0.2)
        self.assertLessEqual(capped[1], free[1] + 0.05)
        self.assertLessEqual(capped[2], free[2] + 50)

    # #92: the numbers a device prints are read by machines, so they do not follow the culture (0,5 under de-DE)
    @unittest.skipUnless(OS == "win", "PowerShell's -f formats in the current culture")
    def test_37_numbers_do_not_follow_the_culture(self):
        p = agent("on", "0.5", "0.5")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        try:
            d = r"C:\ProgramData\netcap"
            p = ps("& { [Threading.Thread]::CurrentThread.CurrentCulture = 'de-DE'; [cultureinfo]::CurrentCulture = 'de-DE'\n"
                   f"  '{{0:G}}' -f 0.5; & '{d}\\netshape.ps1' status; & '{d}\\netcap-check.ps1' --bytes 1000 }}")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            lines = p.stdout.splitlines()
            if lines[0] != "0,5":
                self.skipTest(f"could not switch the culture to de-DE: {lines[0]}")
            status = next(l for l in lines if l.startswith("netshape "))
            self.assertIn(" up_mbit=0.5 ", status)
            check = next(l for l in lines if l.startswith("netcheck "))
            for k in ("down_mbit", "up_mbit", "ping_med", "ping_p95", "ping_max"):
                self.assertRegex(check, rf" {k}=([0-9]+(\.[0-9]+)?|-)( |$)")
        finally:
            agent("off")

    # #92: an empty deadline file (a write cut short) is no deadline, not an error in status
    @unittest.skipUnless(OS == "win", "Read-Until is in the Windows shaper")
    def test_38_empty_until_file(self):
        until = Path(r"C:\ProgramData\netcap\until")
        until.write_bytes(b"")
        try:
            p = agent("status")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("until=- left=-", p.stdout)
        finally:
            until.unlink(missing_ok=True)

    @unittest.skipIf(OS == "win", "Windows keeps its state across reboots (boot=keep)")
    def test_40_boot_on(self):
        install("on")
        try:
            self.assertEqual(self.row("get")["boot"], "on")
            p = (sh("sudo", "launchctl", "print", "system/netcap-netshape") if OS == "mac"
                 else sh("systemctl", "is-enabled", "netcap-netshape"))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        finally:
            install("off")
            agent("off")

    # #92: at boot, com.apple.pfctl may load /etc/pf.conf after the boot job starts. The job waits for it instead of
    # failing and leaving the device uncapped. Here the main ruleset is emptied, the job is loaded, and pf.conf comes back
    # a few seconds later
    @unittest.skipUnless(OS == "mac", "the boot job's race with com.apple.pfctl")
    def test_41_boot_job_waits_for_pf_conf(self):
        p = sh("sudo", "pfctl", "-q", "-f", "/dev/null")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        try:
            try:
                p = install("on")
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                time.sleep(3)
            finally:
                p = sh("sudo", "pfctl", "-q", "-f", "/etc/pf.conf")
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            deadline = time.time() + 60
            while time.time() < deadline and self.row()["state"] != "on":
                time.sleep(2)
            self.assertCap("on", "4", "5")  # the default test_04 left
        finally:
            install("off")
            agent("off")

    # #92: installing again with --boot on keeps the cap in effect and its --for, as on Linux. Before, macOS ran the
    # boot job at once, which put the default in place and cancelled the deadline
    @unittest.skipIf(OS == "win", "Windows has no boot job (boot=keep)")
    def test_42_reinstall_keeps_the_cap(self):
        try:
            self.assertEqual(install("on").returncode, 0)
            p = agent("on", "2", "3", "--for", "600")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            p = install("on")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            r = self.row()
            self.assertEqual((r["state"], r["up_mbit"]), ("on", "2"), r)
            self.assertTrue(0 < int(r["left"]) <= 600, r)
        finally:
            install("off")
            agent("off")

    # #92: a Linux without systemd (a container, WSL without it) installs with --boot off; --boot on says it needs
    # systemd before changing anything. /run/systemd is hidden in a mount namespace of its own
    @unittest.skipUnless(OS == "linux", "systemd")
    def test_43_install_without_systemd(self):
        def install_hidden(boot):
            return sh("sudo", "unshare", "-m", "bash", "-c", 'mount -t tmpfs tmpfs /run/systemd && exec bash "$@"', "-",
                      str(ROOT / "linux" / "install.sh"), "--boot", boot)
        try:
            p = install_hidden("off")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("installed (boot=off", p.stdout)
            p = install_hidden("on")
            self.assertNotEqual(p.returncode, 0, p.stdout)
            self.assertIn("--boot on needs systemd", p.stderr)
            self.assertFalse(Path("/etc/systemd/system/netcap-netshape.service").exists())
        finally:
            install("off")

    # docs/operations.md: More than one controller. Each controller may log in as its own user (#31)
    @unittest.skipIf(OS == "win", "Windows has no sudoers: any Administrator works")
    def test_50_more_than_one_user(self):
        users = ["netcap-e2e-a", "netcap-e2e-b"]
        for i, u in enumerate(users):
            if OS == "mac":
                for key, value in (("UniqueID", str(599 - i)), ("PrimaryGroupID", "20"), ("UserShell", "/bin/bash"),
                                   ("NFSHomeDirectory", "/var/empty")):
                    sh("sudo", "dscl", ".", "-create", f"/Users/{u}", key, value)
            else:
                sh("sudo", "useradd", "-M", "-s", "/bin/bash", u)
        try:
            for u in users:
                p = sh("sudo", "env", f"NETCAP_USER={u}", "bash", str(ROOT / OS / "install.sh"), "--boot", "off")
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn(f"sudoers for {', '.join(sorted([os.environ['USER'], *users]))}", p.stdout)
            for u in users:  # each one reaches the shaper through sudoers
                p = sh("sudo", "-u", u, AGENT, "status")
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                self.assertTrue(p.stdout.startswith("netshape "), p.stdout)
            # and nothing else
            self.assertNotEqual(sh("sudo", "-u", users[0], "sudo", "-n", "/usr/bin/true").returncode, 0)
            p = sh("sudo", "env", f"NETCAP_USER={users[0]}", "bash", str(ROOT / OS / "uninstall.sh"), "--user")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertNotEqual(sh("sudo", "-u", users[0], AGENT, "status").returncode, 0)
            self.assertEqual(sh("sudo", "-u", users[1], AGENT, "status").returncode, 0)
            self.assertEqual(self.row()["reach"], "ok")  # the one who installed first keeps it
        finally:
            for u in users:
                sh("sudo", "env", f"NETCAP_USER={u}", "bash", str(ROOT / OS / "uninstall.sh"), "--user")
                sh("sudo", "dscl", ".", "-delete", f"/Users/{u}") if OS == "mac" else sh("sudo", "userdel", u)

    # --- download on Windows: WinDivert (docs/adr/0001-cap-download-on-windows.md) ---
    # install --with-download fetched the release zip, kept only the x64 driver, its DLL, and the license, and locked them
    @unittest.skipUnless(OS == "win", "WinDivert")
    def test_60_windivert_is_pinned_and_locked(self):
        self.assertEqual(sorted(p.name for p in Path(WD).iterdir()), ["LICENSE", "WinDivert.dll", "WinDivert64.sys"])
        src = (ROOT / "win" / "install.ps1").read_text(encoding="utf-8-sig")
        pins = dict(re.findall(r"'(?:x64/)?([\w.]+)'\s+= '([0-9a-f]{64})'", src))
        self.assertEqual(sorted(pins), ["LICENSE", "WinDivert.dll", "WinDivert64.sys"])
        for name, want in pins.items():
            self.assertEqual(hashlib.sha256((Path(WD) / name).read_bytes()).hexdigest(), want, name)
        # The pin is the zip upstream publishes
        url, zip_pin = re.search(r"\$WdUrl = '([^']+)'", src).group(1), re.search(r"\$WdZip = '([0-9a-f]{64})'", src).group(1)
        self.assertTrue(url.startswith("https://github.com/basil00/WinDivert/releases/download/v2.2.2/"), url)
        with urllib.request.urlopen(url, timeout=60) as r:
            self.assertEqual(hashlib.sha256(r.read()).hexdigest(), zip_pin)
        self.assertEqual([l for l in win_acl(WD) if l.startswith("bad ")], [])

    # A zip whose SHA-256 is not the pinned one is refused before anything changes. A copy of install.ps1 with other
    # pins stands in for a changed release: its files do not match, so it fetches, and the real zip does not match either
    @unittest.skipUnless(OS == "win", "WinDivert")
    def test_61_install_refuses_another_zip(self):
        tmp = Path(tempfile.mkdtemp()) / "win"
        shutil.copytree(ROOT / "win", tmp)
        src = (tmp / "install.ps1").read_text(encoding="utf-8-sig")
        (tmp / "install.ps1").write_text(re.sub(r"'[0-9a-f]{64}'", "'" + "0" * 64 + "'", src), encoding="utf-8-sig")
        before = {f.name: f.read_bytes() for f in Path(WD).iterdir()}
        p = sh(*PS, str(tmp / "install.ps1"), "-WithDownload")
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("refused https://github.com/basil00/WinDivert/", p.stderr)
        self.assertIn("Nothing was changed", p.stderr)
        self.assertEqual({f.name: f.read_bytes() for f in Path(WD).iterdir()}, before)

    # docs/design.md: what passes through, checked against the filter the shaper opens WinDivert with. WinDivert
    # evaluates it on packets made here, so the IPv6 ranges are covered too (the runners have no IPv6 to the internet)
    @unittest.skipUnless(OS == "win", "WinDivert")
    def test_62_filter_lets_through_what_design_md_says(self):
        def v4(src, dst, proto, sport=0):
            body = (sport.to_bytes(2, "big") + (40000).to_bytes(2, "big") +
                    (bytes(8) + b"\x50\x10\xff\xff" + bytes(4) if proto == 6 else (8).to_bytes(2, "big") + bytes(2)))
            if proto == 1:
                body = b"\x00\x00\x00\x00\x00\x01\x00\x01"  # echo reply
            head = (b"\x45\x00" + (20 + len(body)).to_bytes(2, "big") + bytes(4) + b"\x40" + bytes([proto]) + bytes(2) +
                    ipaddress.ip_address(src).packed + ipaddress.ip_address(dst).packed)
            return head + body

        def v6(src, dst, proto, sport=0):
            body = (sport.to_bytes(2, "big") + (40000).to_bytes(2, "big") +
                    (bytes(8) + b"\x50\x10\xff\xff" + bytes(4) if proto == 6 else (8).to_bytes(2, "big") + bytes(2)))
            if proto == 58:
                body = b"\x81\x00\x00\x00\x00\x01\x00\x01"  # echo reply
            return (b"\x60\x00\x00\x00" + len(body).to_bytes(2, "big") + bytes([proto]) + b"\x40" +
                    ipaddress.ip_address(src).packed + ipaddress.ip_address(dst).packed + body)

        local = [ipaddress.ip_network(n) for n in LOCAL]
        here4, here6, far4, far6 = "10.1.0.5", "2001:db8::5", "8.8.4.4", "2606:4700::1111"
        cases = [  # (what, packet, outbound, capped)
            ("tcp from the internet to a private address", v4(far4, here4, 6, 443), False, True),
            ("udp (quic) from the internet", v4(far4, here4, 17, 443), False, True),
            ("tcp over ipv6 from the internet", v6(far6, here6, 6, 443), False, True),
            ("udp over ipv6 from the internet", v6(far6, here6, 17, 443), False, True),
            ("dns over udp", v4(far4, here4, 17, 53), False, False),
            ("dns over tcp", v4(far4, here4, 6, 53), False, False),
            ("dns over ipv6", v6(far6, here6, 17, 53), False, False),
            ("icmp", v4(far4, here4, 1), False, False),
            ("icmpv6", v6(far6, here6, 58), False, False),
            ("to a multicast address", v4(far4, "239.1.2.3", 17, 5000), False, False),
            ("to the broadcast address", v4(far4, "255.255.255.255", 17, 5000), False, False),
            ("to an ipv6 multicast address", v6(far6, "ff02::1", 17, 5000), False, False),
            ("outbound (upload is NetQosPolicy's)", v4(here4, far4, 6, 40000), True, False),
        ]
        for net in local:
            make, here = (v6, here6) if net.version == 6 else (v4, here4)
            for addr in (net.network_address, net.broadcast_address):
                cases.append((f"from {addr} ({net})", make(str(addr), here, 6, 443), False, False))
            for addr in (int(net.network_address) - 1, int(net.broadcast_address) + 1):
                if 0 <= addr < 2 ** net.max_prefixlen and not any(ipaddress.ip_address(addr) in n for n in local):
                    cases.append((f"from {ipaddress.ip_address(addr)} (next to {net})", make(str(ipaddress.ip_address(addr)), here, 6, 443),
                                  False, True))
        script = Path(tempfile.mkdtemp()) / "eval.ps1"
        script.write_text(f"""$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class Ev {{
  [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr LoadLibraryW(string p);
  [DllImport("WinDivert.dll", CharSet = CharSet.Ansi)] public static extern bool WinDivertHelperCompileFilter(string f, int layer, IntPtr obj, uint len, out IntPtr err, out uint pos);
  [DllImport("WinDivert.dll", CharSet = CharSet.Ansi)] public static extern bool WinDivertHelperEvalFilter(string f, byte[] p, uint n, byte[] a);
}}
'@
[void][Ev]::LoadLibraryW('{WD}\\WinDivert.dll')
$f = & '{WIN_DIR}\\netshape-down.ps1' filter
$err = [IntPtr]::Zero; $pos = 0
if (-not [Ev]::WinDivertHelperCompileFilter($f, 0, [IntPtr]::Zero, 0, [ref]$err, [ref]$pos)) {{
  "compile error at $pos`: $([Runtime.InteropServices.Marshal]::PtrToStringAnsi($err))"; $f; exit 1
}}
foreach ($line in [IO.File]::ReadAllLines('{script.with_suffix(".txt")}')) {{
  $hex, $flags = $line -split ' '
  $p = [byte[]]::new($hex.Length / 2); for ($i = 0; $i -lt $p.Length; $i++) {{ $p[$i] = [Convert]::ToByte($hex.Substring($i * 2, 2), 16) }}
  $a = [byte[]]::new(80); $a[10] = [byte][int]$flags  # Outbound 0x02, IPv6 0x10 (bits 17 and 20 of the bit fields)
  if ([Ev]::WinDivertHelperEvalFilter($f, $p, $p.Length, $a)) {{ 'capped' }} else {{ 'pass' }}
}}
""", encoding="utf-8-sig")
        script.with_suffix(".txt").write_text("".join(
            f"{pkt.hex()} {(0x02 if out else 0) | (0x10 if pkt[0] >> 4 == 6 else 0)}\n" for _, pkt, out, _ in cases))
        p = sh(*PS, str(script))
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        got = {what: v for (what, *_), v in zip(cases, p.stdout.split())}
        want = {what: "capped" if capped else "pass" for what, _, _, capped in cases}
        self.assertEqual(got, want)

    # docs/design.md: loopback, DNS, and ping pass while the download queue is full. Under a 0.5 Mbit/s cap with a
    # download running, 50 packets wait about 1.2 s: what is capped takes that long, what passes does not
    @unittest.skipUnless(OS == "win", "WinDivert")
    def test_63_what_passes_while_download_is_full(self):
        blob = os.urandom(2_000_000)

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)

            def log_message(self, *args):
                pass

        servers = []
        for family, host in ((2, "127.0.0.1"), (23, "::1")):
            cls = type("Server", (http.server.ThreadingHTTPServer,), {"address_family": family})
            srv = cls((host, 0), Handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            servers.append((f"[{host}]" if ":" in host else host, srv))

        def timed(f):
            t = time.monotonic()
            f()
            return time.monotonic() - t

        def loopback(host, srv):
            with urllib.request.urlopen(f"http://{host}:{srv.server_address[1]}/", timeout=60) as r:
                self.assertEqual(len(r.read()), len(blob))

        def dns():
            try:
                socket.getaddrinfo(f"netcap-{uuid.uuid4().hex[:12]}.example.com", 443)
            except socket.gaierror:
                pass  # NXDOMAIN is the answer we wait for

        def internet():
            sh("curl.exe", "-s", "-o", "NUL", "--max-time", "30", "https://speed.cloudflare.com/__down?bytes=1000")

        def median(xs):
            return sorted(xs)[len(xs) // 2]

        def measure():
            return {"loopback": max(timed(lambda: loopback(h, s)) for h, s in servers),
                    "dns": median([timed(dns) for _ in range(5)]),
                    "internet": median([timed(internet) for _ in range(3)])}

        free = measure()
        self.netcap("on", "self", "--up", "1", "--down", "0.5")
        load = subprocess.Popen(["curl.exe", "-s", "-o", "NUL", "--max-time", "60",
                                 "https://speed.cloudflare.com/__down?bytes=50000000"])
        try:
            time.sleep(3)
            capped = measure()
        finally:
            load.kill()
            self.netcap("off", "self")
            for _, srv in servers:
                srv.shutdown()
        print("\n  seconds without a cap / at 0.5 Mbit/s down with a download running: " +
              ", ".join(f"{k} {free[k]:.3f} / {capped[k]:.3f}" for k in free))
        self.assertGreater(capped["internet"], 0.5)  # the queue was full: this is what capped looks like
        self.assertLess(capped["loopback"], 2.0)  # 2 MB, about 32 s if it were capped
        self.assertLess(capped["dns"], 0.5)

    # off closes the handle by ending the shaper, and removes its task. netcap never stops the WinDivert service
    # (basil00/WinDivert#406): what Windows does with the driver afterwards is recorded here, not asserted
    @unittest.skipUnless(OS == "win", "WinDivert")
    def test_64_off_ends_the_shaper(self):
        self.netcap("on", "self", "--up", "2", "--down", "3")
        pid = shaper_state()["pid"]
        self.assertTrue(process_alive(pid))
        while_on = driver_state()
        self.netcap("off", "self")
        self.assertFalse(process_alive(pid))
        self.assertFalse(win_task("download"))
        self.assertEqual(shaper_state(), {})
        after = driver_state()
        time.sleep(10)
        print(f"\n  WinDivert driver: while on {while_on}; right after off {after}; 10 s later {driver_state()}")

    # on and set change the rate of the running shaper: the handle stays open, and no second driver load races the first
    # (basil00/WinDivert#408)
    @unittest.skipUnless(OS == "win", "WinDivert")
    def test_65_rate_changes_keep_the_handle(self):
        self.netcap("on", "self", "--up", "2", "--down", "3")
        try:
            pid = shaper_state()["pid"]
            self.netcap("on", "self", "--up", "2", "--down", "5")
            self.assertCap("on", "2", "5")
            self.assertEqual(shaper_state()["pid"], pid)
        finally:
            self.netcap("off", "self")

    # A shaper that is gone while its task is registered is partial. Starting the task, as Windows does at startup,
    # brings the cap back from download.mbit
    @unittest.skipUnless(OS == "win", "WinDivert")
    def test_66_shaper_gone_is_partial_and_the_task_brings_it_back(self):
        self.netcap("on", "self", "--up", "2", "--down", "3")
        try:
            pid = shaper_state()["pid"]
            ps(f"Stop-Process -Id {pid} -Force")
            r = self.row()
            self.assertEqual((r["state"], r["shaper"], r["down_mbit"]), ("partial", "stopped", "-"), r)
            ps("Start-ScheduledTask -TaskPath '\\netcap\\' -TaskName download")
            deadline = time.time() + 60
            while time.time() < deadline and self.row()["shaper"] != "running":
                time.sleep(2)
            self.assertCap("on", "2", "3")
        finally:
            self.netcap("off", "self")

    # Installed again without --with-download, the device is back to upload only and WinDivert is gone
    @unittest.skipUnless(OS == "win", "WinDivert")
    def test_67_install_without_the_flag_removes_windivert(self):
        self.netcap("on", "self", "--up", "2", "--down", "3")
        try:
            p = install(download=False)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            self.assertIn("removed WinDivert", p.stdout)
            self.assertFalse((Path(WD) / "WinDivert.dll").exists())
            self.assertGone(WD)
            self.assertFalse(win_task("download"))
            r = self.row()
            self.assertEqual((r["state"], r["up_mbit"], r["down_src"]), ("on", "2", "unsupported"), r)
            self.assertNotIn("shaper", r)
        finally:
            self.netcap("off", "self")
            p = install()
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(self.row()["down_src"], "windivert")
        self.assertFalse(win_task("cleanup"))  # what is installed again stays

    # Windows PowerShell 5.1's Remove-Item -Recurse follows a junction and deletes what it points to. uninstall.ps1
    # removes the link, and leaves the folder it points to as it was
    @unittest.skipUnless(OS == "win", "junctions")
    def test_97_uninstall_leaves_what_a_link_points_to(self):
        d = r"C:\ProgramData\netcap"
        links = {"junction": ("/J", d + r"\elsewhere"), "symlink": ("/D", d + r"\sub\elsewhere")}  # sub: one level down
        targets = {}
        os.makedirs(d + r"\sub", exist_ok=True)
        for kind, (flag, link) in links.items():
            targets[kind] = Path(tempfile.mkdtemp())
            (targets[kind] / "keep.txt").write_text("x")
            p = sh("cmd", "/c", "mklink", flag, link, str(targets[kind]))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        try:
            p = uninstall()
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            for kind, target in targets.items():
                self.assertTrue((target / "keep.txt").exists(), f"uninstall.ps1 deleted what the {kind} points to")
            self.assertGone(d)
        finally:
            for _, link in links.values():
                sh("cmd", "/c", "rmdir", link)
            p = install()
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_99_uninstall(self):
        self.netcap("uninstall", "self")
        if OS == "win":
            print(f"\n  WinDivert driver after uninstall: {driver_state()}")
            self.assertFalse(win_task("download"))
        for p in INSTALLED:
            self.assertGone(p)
        self.assertNotIn("self", (self.conf / "hosts").read_text())
        install("off")  # tearDownClass removes it again


# docs/design.md: Destinations that pass through, measured instead of read from the rules. The runners have no IPv6 to
# the internet, so two network namespaces joined by a veth pair stand in for this machine and the line: documentation
# prefixes play the internet (198.51.100.0/24, 2001:db8::/64). The shaper runs from the repository inside the first one
LAB = {"dev": "netcap-lab-dev", "net": "netcap-lab-net"}
LAB_ADDRS = {  # kind: (address of this machine, address across the line)
    "ipv4 lan": ("192.168.233.1/24", "192.168.233.2"),
    "ipv4 internet": ("198.51.100.1/24", "198.51.100.2"),
    "ipv6 ula": ("fd00:ca9::1/64", "fd00:ca9::2"),
    "ipv6 internet": ("2001:db8::1/64", "2001:db8::2"),
}
# Only internet traffic is capped, and DNS and ping pass even toward the internet, over IPv4 and IPv6 alike (#28)
PASSES = {
    "ipv4 lan": {"tcp": "pass", "udp53": "pass", "ping": "pass"},
    "ipv4 internet": {"tcp": "capped", "udp53": "pass", "ping": "pass"},
    "ipv6 ula": {"tcp": "pass", "udp53": "pass", "ping": "pass"},
    "ipv6 internet": {"tcp": "capped", "udp53": "pass", "ping": "pass"},
}


@unittest.skipUnless(os.environ.get("NETCAP_E2E") and OS == "linux", "only with NETCAP_E2E=1, on Linux (network namespaces)")
class PassThrough(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dev, net = LAB["dev"], LAB["net"]
        cls.ns(None, "ip", "netns", "add", dev)
        cls.ns(None, "ip", "netns", "add", net)
        cls.ns(None, "ip", "link", "add", "lab0", "netns", dev, "type", "veth", "peer", "name", "lab1", "netns", net)
        for ns, link, me in ((dev, "lab0", 0), (net, "lab1", 1)):
            for addr, peer in LAB_ADDRS.values():
                mine = addr if me == 0 else peer + addr[addr.index("/"):]
                cls.ns(ns, "ip", "addr", "add", mine, "dev", link, *(["nodad"] if ":" in mine else []))
            cls.ns(ns, "ip", "link", "set", "lo", "up")
            cls.ns(ns, "ip", "link", "set", link, "up")
        cls.ns(dev, "ip", "route", "add", "default", "via", LAB_ADDRS["ipv4 internet"][1])
        cls.server = subprocess.Popen(["sudo", "ip", "netns", "exec", net, sys.executable, str(ROOT / "tests" / "lab_echo.py"),
                                       "serve"], stdout=subprocess.PIPE, text=True)
        assert cls.server.stdout.readline().strip() == "ready"

    @classmethod
    def tearDownClass(cls):
        sh("sudo", "ip", "netns", "exec", LAB["dev"], "bash", str(ROOT / "linux" / "netcap-netshape"), "off")
        sh("sudo", "pkill", "-f", "lab_echo.py serve")
        for ns in LAB.values():
            sh("sudo", "ip", "netns", "del", ns)

    @staticmethod
    def ns(ns, *cmd):
        p = sh("sudo", *(["ip", "netns", "exec", ns] if ns else []), *cmd)
        assert p.returncode == 0, f"{' '.join(cmd)}: {p.stdout}{p.stderr}"
        return p.stdout

    def measure(self, kind, addr):
        """pass or capped, from how long the traffic took (lab_echo.py; ping)"""
        if kind == "ping":
            # 200 echoes of 1400 bytes, 5 ms apart: about 2.3 Mbit/s, so under a 1 Mbit/s cap the queue grows to
            # hundreds of ms. Small enough not to be fragmented: a fragmented ICMPv6 echo is not recognized (design.md)
            out = sh("sudo", "ip", "netns", "exec", LAB["dev"], "ping", "-q", "-c", "200", "-i", "0.005", "-s", "1400",
                     addr).stdout
            m = re.search(r"= [\d.]+/([\d.]+)/", out)
            ms = float(m.group(1)) if m else float("inf")  # nothing came back: held in the queue or dropped
            return ms, "pass" if ms < 50 else "capped" if ms > 200 else "?"
        sec = float(self.ns(LAB["dev"], sys.executable, str(ROOT / "tests" / "lab_echo.py"), kind, addr))
        return sec, "pass" if sec < 0.3 else "capped" if sec > 0.6 else "?"

    def test_what_passes_through(self):
        self.ns(LAB["dev"], "bash", str(ROOT / "linux" / "netcap-netshape"), "on", "1", "1")
        got, raw = {}, {}
        for name, (_, addr) in LAB_ADDRS.items():
            got[name] = {}
            for kind in ("tcp", "udp53", "ping"):
                value, got[name][kind] = self.measure(kind, addr)
                raw[f"{name} {kind}"] = value
        print("\n" + "\n".join(f"  {k}: {v:.3f}" for k, v in raw.items()))
        self.assertEqual(got, PASSES)


if __name__ == "__main__":
    unittest.main()
