"""Set up and drive a device over real ssh, the way a controller does (docs/platforms.md: install --ssh).

test_e2e.py runs the agent on this machine without ssh. This one goes through sshd, scp, sudo on the device, and the
forced command in authorized_keys. It looks at the device only through the CLI and ssh, so the same test runs in CI
(ssh to the runner itself) and against a real device on another OS.

  NETCAP_E2E_SSH=<ssh Host> python3 -m unittest -v tests/test_e2e_ssh.py

The Host must accept your own key (BatchMode). The test installs netcap there with ~/.ssh/netcap, which it creates if
needed, and removes netcap from the device and the key from its authorized_keys at the end.
Do not point it at a device you manage with that key.
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = os.environ.get("NETCAP_E2E_SSH")
KEY = Path.home() / ".ssh" / "netcap"


def sh(*cmd, env=None):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)


def netcap_key_ssh(*cmd):
    """ssh with the netcap key only, as the CLI sends a request"""
    return sh("ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-i", str(KEY), "-o", "IdentitiesOnly=yes",
              "-o", "ControlPath=none", DEST, *cmd)


@unittest.skipUnless(DEST, "only with NETCAP_E2E_SSH=<ssh Host> (installs netcap on that device)")
class OverSsh(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conf = Path(tempfile.mkdtemp())
        cls.env = {**os.environ, "NETCAP_CONFIG_DIR": str(cls.conf)}
        # README: Manage other devices. Output goes to the terminal: sudo on the device may ask for a password
        cls.installed = subprocess.run([sys.executable, str(ROOT / "bin" / "netcap"), "install", "dev", "--ssh", DEST,
                                        "--boot", "off"], env=cls.env)

    @classmethod
    def tearDownClass(cls):
        hosts = cls.conf / "hosts"
        if hosts.exists() and "dev" in hosts.read_text().split():  # a test stopped before test_99
            sh(sys.executable, str(ROOT / "bin" / "netcap"), "off", "dev", env=cls.env)
            sh(sys.executable, str(ROOT / "bin" / "netcap"), "uninstall", "dev", env=cls.env)

    def netcap(self, *args, rc=0):
        p = sh(sys.executable, str(ROOT / "bin" / "netcap"), *args, env=self.env)
        if rc is not None:
            self.assertEqual(p.returncode, rc, p.stdout + p.stderr)
        return p.stdout

    def row(self, cmd="status"):
        return json.loads(self.netcap(cmd, "dev", "--json"))[0]

    def os_(self):
        return (self.conf / "hosts").read_text().split()[1]

    def assertCap(self, state, up="-", down="-"):
        r = self.row()
        self.assertEqual(r["reach"], "ok", r)
        self.assertEqual(r["state"], state, r)
        self.assertEqual(r["up_mbit"], up, r)
        if self.os_() == "win":  # download cannot be capped (docs/platforms.md)
            self.assertEqual(r["down_src"], "unsupported", r)
        else:
            self.assertEqual(r["down_mbit"], down, r)

    def test_00_install(self):
        self.assertEqual(self.installed.returncode, 0)
        name, os_, route = (self.conf / "hosts").read_text().split()
        self.assertEqual((name, route), ("dev", DEST))
        self.assertIn(os_, ("mac", "linux", "win"))
        # The agent on the device reports the version of the CLI that installed it
        r = self.row("get")
        self.assertEqual(r["reach"], "ok", r)
        self.assertEqual("netcap " + r["agent"], self.netcap("--version").strip())

    # docs/host-setup.md: the netcap key gets only the agent, and the device keeps trusting your own key
    def test_01_key_runs_only_the_agent(self):
        p = netcap_key_ssh("id")
        self.assertNotEqual(p.returncode, 0, p.stdout)
        self.assertIn("netcap-agent: ", p.stderr)
        own = sh("ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", DEST, "echo", "own-key-ok")
        self.assertEqual(own.returncode, 0, own.stderr)
        self.assertIn("own-key-ok", own.stdout)

    def test_02_doctor(self):
        r = json.loads(self.netcap("doctor", "dev", "--json"))[0]
        self.assertEqual((r["reach"], r["key"]), ("ok", "ok"), r)

    # Through the forced command and, on macOS / Linux, sudoers
    def test_03_on_and_off(self):
        self.netcap("on", "dev", "--up", "2", "--down", "3")
        try:
            self.assertCap("on", "2", "3")
        finally:
            self.netcap("off", "dev")
        self.assertCap("off")

    def test_99_uninstall(self):
        os_ = self.os_()
        # Output goes to the terminal, as in setUpClass: sudo on the device may ask for a password
        p = subprocess.run([sys.executable, str(ROOT / "bin" / "netcap"), "uninstall", "dev"], env=self.env)
        self.assertEqual(p.returncode, 0)
        self.assertNotIn("dev", (self.conf / "hosts").read_text().split())
        # The netcap key is gone from the device. Read the file with your own key: a request with the netcap key
        # proves nothing, since ssh falls back to an IdentityFile from ~/.ssh/config once that key is refused
        if os_ == "win":
            script = r"Get-Content -Raw (Join-Path $env:ProgramData 'ssh\administrators_authorized_keys')"
            cmd = "powershell -NoProfile -EncodedCommand " + base64.b64encode(script.encode("utf-16-le")).decode()
        else:
            cmd = "cat ~/.ssh/authorized_keys 2>/dev/null || true"
        keys = sh("ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", DEST, cmd)
        self.assertEqual(keys.returncode, 0, keys.stderr)
        self.assertNotIn(KEY.with_suffix(".pub").read_text().split()[1], keys.stdout)


if __name__ == "__main__":
    unittest.main()
