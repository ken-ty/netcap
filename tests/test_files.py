"""Do the values written in the docs match the contents of the device-side files?"""
import ipaddress
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(p):
    return (ROOT / p).read_text(encoding="utf-8-sig")


def with_translations(p):
    """docs/host-setup.md and its translations (docs/host-setup.<lang>.md)."""
    p = Path(p)
    return [p] + sorted(q.relative_to(ROOT) for q in (ROOT / p.parent).glob(f"{p.stem}.*{p.suffix}"))


def nets(text):
    """Turn "10/8", "10.0.0.0/8" and "fc00::/7" into a set of ip_network."""
    out = set()
    for m in re.findall(r"\b(\d{1,3}(?:\.\d{1,3}){0,3})/(\d{1,2})\b", text):
        addr = ".".join((m[0].split(".") + ["0"] * 4)[:4])
        out.add(ipaddress.ip_network(f"{addr}/{m[1]}"))
    for m in re.findall(r"(?<![\w:])([0-9a-fA-F]{0,4}(?::[0-9a-fA-F]{0,4}){2,7})/(\d{1,3})\b", text):
        out.add(ipaddress.ip_network(f"{m[0]}/{m[1]}"))
    return out


class Exempt(unittest.TestCase):
    """docs/design.md: Destinations that pass through"""

    def setUp(self):
        section = read("docs/design.md").split("## Destinations that pass through")[1].split("\n## ")[0]
        self.table = nets("\n".join(l for l in section.splitlines() if l.startswith("|")))
        self.assertTrue(self.table)
        self.assertTrue(any(n.version == 6 for n in self.table), "the table lists IPv6 ranges too (#28)")

    def test_mac_ranges(self):
        pf = read("mac/netcap-netshape.pf")
        self.assertEqual(nets(re.search(r"table <netcap_local>[^}]*", pf).group()), self.table)

    def test_win_ranges(self):
        ps = read("win/netshape.ps1")
        # A line ending in a comma goes on to the next
        self.assertEqual(nets(re.search(r"\$Local = (?:.*,\n)*.*", ps).group()), self.table)

    def test_dns_and_icmp_pass_on_mac(self):
        pf = read("mac/netcap-netshape.pf")
        rules = [l for l in pf.splitlines() if l.startswith("dummynet")]
        self.assertTrue(rules)
        for r in rules:
            self.assertIn("proto { tcp udp }", r)  # ICMP does not match
            self.assertIn("port != 53", r)

    def test_linux_ranges(self):
        sh = read("linux/netcap-netshape")
        self.assertEqual(nets("\n".join(re.findall(r"^LOCAL6?=.*", sh, re.M))), self.table)

    def test_dns_and_icmp_pass_on_linux(self):
        sh = read("linux/netcap-netshape")
        self.assertRegex(sh, r"ip protocol 1 0xff")  # ICMP
        self.assertRegex(sh, r"ip dport 53 0xffff")  # DNS (up)
        self.assertRegex(sh, r"ip sport 53 0xffff")  # DNS (down)
        # IPv6 has its own filters, in a prio of their own: tc keeps one protocol per prio (#28)
        self.assertRegex(sh, r"protocol ipv6 prio 2 u32 match ip6 protocol 58 0xff")  # ICMPv6
        self.assertRegex(sh, r"ip6 dport 53 0xffff")
        self.assertRegex(sh, r"ip6 sport 53 0xffff")

    def test_dns_passes_on_win(self):
        self.assertRegex(read("win/netshape.ps1"), r"-IPDstPortMatchCondition 53 ")


class Sudoers(unittest.TestCase):
    """mac/netcap-sudoers builds /etc/sudoers.d/netcap-netshape: the template's verbs, and one line per user (#31)"""
    LINE = "{} ALL=(root) NOPASSWD: NETSHAPE"

    def build(self, existing, action, user, os_="mac"):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "existing"
            f.write_text(existing)
            return subprocess.run(["bash", str(ROOT / "mac" / "netcap-sudoers"), str(ROOT / os_ / "sudoers.d" / "netcap-netshape"),
                                   str(f), action, user], capture_output=True, text=True)

    def users(self, text):
        return [l.split()[0] for l in text.splitlines() if l.endswith("NOPASSWD: NETSHAPE")]

    def template(self, os_="mac"):
        return [l for l in read(f"{os_}/sudoers.d/netcap-netshape").splitlines() if not l.startswith("__USER__")]

    def test_adds_a_user_and_keeps_the_others(self):
        for os_ in ("mac", "linux"):
            one = self.build("", "add", "alice", os_).stdout
            self.assertEqual(self.users(one), ["alice"])
            two = self.build(one, "add", "first.last", os_)
            self.assertEqual(two.returncode, 0, two.stderr)
            self.assertEqual(self.users(two.stdout), ["alice", "first.last"])
            # Everything but the user lines comes from the template: the verbs never widen
            self.assertEqual([l for l in two.stdout.splitlines() if not l.endswith("NOPASSWD: NETSHAPE")], self.template(os_))

    def test_add_again_and_remove(self):
        two = self.build(self.LINE.format("alice") + "\n" + self.LINE.format("bob") + "\n", "add", "alice").stdout
        self.assertEqual(self.users(two), ["alice", "bob"])
        self.assertEqual(self.users(self.build(two, "remove", "alice").stdout), ["bob"])
        self.assertEqual(self.build(self.LINE.format("bob") + "\n", "remove", "bob").stdout, "")  # nobody left

    def test_carries_over_only_its_own_lines(self):
        hand = "alice ALL=(ALL) ALL\n" + self.LINE.format("bob") + "\nCmnd_Alias X = /bin/sh\n"
        out = self.build(hand, "add", "carol").stdout
        self.assertEqual(self.users(out), ["bob", "carol"])
        self.assertNotIn("(ALL) ALL", out)
        self.assertNotIn("/bin/sh", out)

    def test_refuses_a_name_sudoers_would_read_otherwise(self):
        for bad in ("Alice", "a b", "a,b", "%admin", ""):
            with self.subTest(bad=bad):
                self.assertNotEqual(self.build("", "add", bad).returncode, 0)

    @unittest.skipUnless(shutil.which("visudo"), "visudo checks the syntax")
    def test_visudo_accepts_it(self):
        out = self.build(self.LINE.format("alice") + "\n", "add", "first.last").stdout
        with tempfile.NamedTemporaryFile("w", suffix=".sudoers") as f:
            f.write(out)
            f.flush()
            p = subprocess.run(["visudo", "-cf", f.name], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


class HostSetup(unittest.TestCase):
    """install.sh places, and uninstall.sh removes, the paths in the tables of docs/host-setup.md (and translations)"""

    def test_paths(self):
        for md in with_translations("docs/host-setup.md"):
            for section, d in (("macOS", "mac"), ("Linux", "linux")):
                doc = read(md).split(f"## {section}\n")[1].split("\n## ")[0]
                paths = re.findall(r"^\| `(/[^`]+)`", doc, re.M)
                self.assertTrue(paths)
                install, uninstall = read(f"{d}/install.sh"), read(f"{d}/uninstall.sh")
                for p in paths:
                    with self.subTest(doc=str(md), os=d, path=p):
                        self.assertIn(p, install)
                        self.assertIn(p, uninstall)


class Release(unittest.TestCase):
    """CONTRIBUTING.md Release: the Formula tag matches the version in the curl / zip examples of the docs"""

    def test_formula_replaces_only_the_version(self):
        """The formula's inreplace hits every quoted placeholder in bin/netcap; only VERSION may have one"""
        target = re.search(r"inreplace libexec/\"bin/netcap\", '([^']+)'", read("Formula/netcap.rb")).group(1)
        self.assertEqual(read("bin/netcap").count(target), 1)

    def test_versions_match(self):
        tag = re.search(r'tag:\s+"v([\d.]+)"', read("Formula/netcap.rb")).group(1)
        for md in with_translations("docs/host-setup.md"):
            with self.subTest(doc=str(md)):
                doc = read(md)
                self.assertEqual(set(re.findall(r"refs/tags/v([\d.]+)\.", doc)), {tag})
                self.assertEqual(set(re.findall(r"netcap-([\d.]+)\b", doc)), {tag})

    def test_changelog_has_the_release(self):
        """CONTRIBUTING.md Release: the version in the formula has its section, and Unreleased stays on top.
        Not "the second section": between the changelog PR and the formula bump, main is one version ahead"""
        tag = re.search(r'tag:\s+"v([\d.]+)"', read("Formula/netcap.rb")).group(1)
        log = read("CHANGELOG.md")
        heads = re.findall(r"^## \[([^\]]+)\]", log, re.M)
        self.assertEqual(heads[0], "Unreleased")
        self.assertIn(tag, heads)
        self.assertEqual(set(re.findall(r"^\[([^\]]+)\]: https://", log, re.M)), set(heads))


class Readme(unittest.TestCase):
    """README.md and its translations list the same commands (CONTRIBUTING.md)"""

    def commands(self, p):
        return re.findall(r"^netcap [^\n]*?(?=\s{2,}|$)", read(p), re.M)

    def test_same_commands(self):
        translations = with_translations("README.md")[1:]
        self.assertTrue(translations)
        for md in translations:
            with self.subTest(doc=str(md)):
                self.assertEqual(self.commands("README.md"), self.commands(md))


if __name__ == "__main__":
    unittest.main()
