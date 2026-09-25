"""Do the values written in the docs match the contents of the device-side files?"""
import ipaddress
import re
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
    """Turn "10/8" and "10.0.0.0/8" into a set of ip_network."""
    out = set()
    for m in re.findall(r"\b(\d{1,3}(?:\.\d{1,3}){0,3})/(\d{1,2})\b", text):
        addr = ".".join((m[0].split(".") + ["0"] * 4)[:4])
        out.add(ipaddress.ip_network(f"{addr}/{m[1]}"))
    return out


class Exempt(unittest.TestCase):
    """docs/design.md: Destinations that pass through"""

    def setUp(self):
        section = read("docs/design.md").split("## Destinations that pass through")[1].split("\n## ")[0]
        self.table = nets("\n".join(l for l in section.splitlines() if l.startswith("|")))
        self.assertTrue(self.table)

    def test_mac_ranges(self):
        pf = read("mac/netcap-netshape.pf")
        self.assertEqual(nets(re.search(r"table <netcap_local>.*", pf).group()), self.table)

    def test_win_ranges(self):
        ps = read("win/netshape.ps1")
        self.assertEqual(nets(re.search(r"\$Local = .*", ps).group()), self.table)

    def test_dns_and_icmp_pass_on_mac(self):
        pf = read("mac/netcap-netshape.pf")
        rules = [l for l in pf.splitlines() if l.startswith("dummynet")]
        self.assertTrue(rules)
        for r in rules:
            self.assertIn("proto { tcp udp }", r)  # ICMP does not match
            self.assertIn("port != 53", r)

    def test_linux_ranges(self):
        sh = read("linux/netcap-netshape")
        self.assertEqual(nets(re.search(r"^LOCAL=.*", sh, re.M).group()), self.table)

    def test_dns_and_icmp_pass_on_linux(self):
        sh = read("linux/netcap-netshape")
        self.assertRegex(sh, r"ip protocol 1 0xff")  # ICMP
        self.assertRegex(sh, r"ip dport 53 0xffff")  # DNS (up)
        self.assertRegex(sh, r"ip sport 53 0xffff")  # DNS (down)

    def test_dns_passes_on_win(self):
        self.assertRegex(read("win/netshape.ps1"), r"-IPDstPortMatchCondition 53 ")


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
