"""docs に書いた値と、端末側のファイルの中身が食い違っていないか。"""
import ipaddress
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(p):
    return (ROOT / p).read_text(encoding="utf-8-sig")


def nets(text):
    """"10/8" や "10.0.0.0/8" を ip_network の集合にする。"""
    out = set()
    for m in re.findall(r"\b(\d{1,3}(?:\.\d{1,3}){0,3})/(\d{1,2})\b", text):
        addr = ".".join((m[0].split(".") + ["0"] * 4)[:4])
        out.add(ipaddress.ip_network(f"{addr}/{m[1]}"))
    return out


class Exempt(unittest.TestCase):
    """docs/design.md「素通しにする宛先」"""

    def setUp(self):
        section = read("docs/design.md").split("## 素通しにする宛先")[1].split("\n## ")[0]
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
            self.assertIn("proto { tcp udp }", r)  # ICMP は当たらない
            self.assertIn("port != 53", r)

    def test_dns_passes_on_win(self):
        self.assertRegex(read("win/netshape.ps1"), r"-IPDstPortMatchCondition 53 ")


class HostSetup(unittest.TestCase):
    """docs/host-setup.md の macOS の表にあるパスを、install.sh が置き uninstall.sh が消す"""

    def test_paths(self):
        doc = read("docs/host-setup.md").split("## macOS")[1].split("\n## ")[0]
        paths = re.findall(r"^\| `(/[^`]+)`", doc, re.M)
        self.assertTrue(paths)
        install, uninstall = read("mac/install.sh"), read("mac/uninstall.sh")
        for p in paths:
            with self.subTest(path=p):
                self.assertIn(p, install)
                self.assertIn(p, uninstall)


class Release(unittest.TestCase):
    """CONTRIBUTING.md のリリース手順: Formula のタグと docs の curl / zip の版が揃っている"""

    def test_versions_match(self):
        tag = re.search(r'tag:\s+"v([\d.]+)"', read("Formula/netcap.rb")).group(1)
        doc = read("docs/host-setup.md")
        self.assertEqual(set(re.findall(r"refs/tags/v([\d.]+)\.", doc)), {tag})
        self.assertEqual(set(re.findall(r"netcap-([\d.]+)\b", doc)), {tag})


class Readme(unittest.TestCase):
    """README.md と README.ja.md は同じコマンドを載せる (CONTRIBUTING.md)"""

    def commands(self, p):
        return re.findall(r"^netcap [^\n]*?(?=\s{2,}|$)", read(p), re.M)

    def test_same_commands(self):
        self.assertEqual(self.commands("README.md"), self.commands("README.ja.md"))


if __name__ == "__main__":
    unittest.main()
