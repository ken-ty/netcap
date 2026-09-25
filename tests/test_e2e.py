"""Follow the README and docs on a real machine. CI runs the same tests on a matrix (macOS / Linux / Windows).

Installs the device side on this machine, writes only this machine into hosts, and drives it from the CLI.
It rewrites the machine's settings and needs sudo (Administrator on Windows), so it runs only with NETCAP_E2E=1.

  NETCAP_E2E=1 python3 -m unittest -v tests/test_e2e.py
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OS = {"darwin": "mac", "linux": "linux", "win32": "win"}.get(sys.platform)
AGENT = {"mac": "/Library/PrivilegedHelperTools/netcap-agent",
         "linux": "/usr/libexec/netcap/netcap-agent",
         "win": r"C:\ProgramData\netcap\netcap-agent.ps1"}.get(OS)
INSTALLED = {"mac": ["/Library/PrivilegedHelperTools/netcap-netshape", "/Library/PrivilegedHelperTools/netcap-agent",
                     "/usr/local/bin/netcap-check", "/etc/pf.anchors/netcap-netshape",
                     "/etc/sudoers.d/netcap-netshape", "/Library/LaunchDaemons/netcap-netshape.plist"],
             "linux": ["/usr/libexec/netcap/netcap-netshape", "/usr/libexec/netcap/netcap-agent",
                       "/usr/local/bin/netcap-check", "/etc/sudoers.d/netcap-netshape",
                       "/etc/systemd/system/netcap-netshape.service"],
             "win": [r"C:\ProgramData\netcap"]}.get(OS)
# docs/design.md: Destinations that pass through
LOCAL = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "224.0.0.0/4"]
PS = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]


def sh(*cmd, env=None):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)


def install(boot="off", src=ROOT):
    if OS == "win":
        return sh(*PS, str(src / "win" / "install.ps1"))
    return sh("sudo", "bash", str(src / OS / "install.sh"), "--boot", boot)


def uninstall():
    if OS == "win":
        return sh(*PS, r"C:\ProgramData\netcap\uninstall.ps1")
    return sh("sudo", "bash", str(ROOT / OS / "uninstall.sh"))


def agent(*args, env=None):
    return sh(*(PS if OS == "win" else []), AGENT, *args, env=env)


@unittest.skipUnless(os.environ.get("NETCAP_E2E") and OS, "only with NETCAP_E2E=1 (rewrites the machine's settings)")
class E2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if OS == "mac":  # upgrade from the v0.5.0 old name (docs/host-setup.md)
            old = Path(tempfile.mkdtemp())
            subprocess.run(f"git -C {ROOT} archive v0.5.0 mac | tar -x -C {old}", shell=True, check=True)
            install("on", src=old)
        cls.installed = install("off")
        conf = Path(tempfile.mkdtemp())
        (conf / "hosts").write_text(f"self {OS} -\n")
        (conf / "profiles").write_text("p     self=2/3\nnone  self=off\n")
        cls.env = {**os.environ, "NETCAP_CONFIG_DIR": str(conf)}

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
        if OS == "win":  # download cannot be capped (README: Supported platforms)
            self.assertEqual(r["down_src"], "unsupported", r)
        else:
            self.assertEqual(r["down_mbit"], down, r)

    def assertDefault(self, up, down):
        r = self.row("get")
        self.assertEqual((r["default_up"], r["default_down"]), (up, down), r)

    # --- hosts: README Usage ---
    def test_00_install(self):
        self.assertEqual(self.installed.returncode, 0, self.installed.stdout + self.installed.stderr)
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

    # --- permissions: docs/host-setup.md ---
    def test_20_forced_command_denies(self):
        p = agent("--allow", "status get", env={**os.environ, "SSH_ORIGINAL_COMMAND": f"{AGENT} on"})
        self.assertNotEqual(p.returncode, 0)
        self.assertRegex(p.stderr, r"^netcap-agent: .*on")

    def test_21_args_are_not_shell(self):
        p = agent("--allow", "on", env={**os.environ, "SSH_ORIGINAL_COMMAND": "on $(id) 1"})
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("netcap-agent: arguments must be numbers", p.stderr)

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
                for n in LOCAL:
                    self.assertIn(f" {n} ", ps)
                self.assertRegex(ps, r"netcap-dns\s+53")
        finally:
            self.netcap("off", "self")

    def test_31_root_only(self):
        if OS == "win":
            acl = sh("powershell", "-NoProfile", "-Command",
                     r"(Get-Acl C:\ProgramData\netcap).Access | Where-Object { $_.IdentityReference -match 'Users$' } | "
                     "ForEach-Object { $_.FileSystemRights }").stdout
            self.assertNotRegex(acl, r"Write|Modify|FullControl")
        else:
            body = AGENT.replace("netcap-agent", "netcap-netshape")
            st = sh("stat", "-f", "%u %Lp", body) if OS == "mac" else sh("stat", "-c", "%u %a", body)
            self.assertEqual(st.stdout.strip(), "0 755")

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
            capped = check(500_000)  # 4 seconds at 1 Mbit/s
            # to see which path the traffic took when this fails
            diag = "" if OS != "linux" else sh("bash", "-c", "ip -br link; tc qdisc show; for d in $(ls /sys/class/net); do "
                                               "tc -s filter show dev $d parent ffff:fff2; tc -s filter show dev $d parent ffff:; "
                                               "done; tc -s class show dev ifb-netcap").stdout
        finally:
            self.netcap("off", "self")
        print(f"\n  no cap: down {free[0]} / up {free[1]}; at 1/1: down {capped[0]} / up {capped[1]} Mbit/s")
        self.assertLess(capped[1], 1.5)
        if OS != "win":  # Windows cannot cap download
            self.assertLess(capped[0], 1.5, diag)

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

    def test_99_uninstall(self):
        uninstall()
        for p in INSTALLED:
            self.assertFalse(Path(p).exists(), p)
        install("off")  # tearDownClass removes it again


if __name__ == "__main__":
    unittest.main()
