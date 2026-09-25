# This repository is its own tap. See Quick Start in the README for installation.
class Netcap < Formula
  desc "Cap the internet bandwidth of devices on your network from one device"
  homepage "https://github.com/ken-ty/netcap"
  url "https://github.com/ken-ty/netcap.git",
      tag:      "v0.7.0",
      revision: "d88c2bffa69905a3e180cd27c72867649bd142f6"
  head "https://github.com/ken-ty/netcap.git", branch: "main"

  license "MIT"

  depends_on "python@3.13"

  def install
    # bin/netcap points to ../examples relative to itself, and mac/ and linux/ get installed on devices, so put the whole tree in libexec
    libexec.install Dir["*"] - ["Formula"]
    inreplace libexec/"bin/netcap", %r{\A#!/usr/bin/env python3$},
              "#!#{Formula["python@3.13"].opt_bin}/python3.13"
    # The tag is the source of truth for the version. Fill in what netcap --version prints
    inreplace libexec/"bin/netcap", '"@VERSION@"', "\"#{version}\""
    bin.install_symlink libexec/"bin/netcap"
  end

  def caveats
    <<~EOS
      Set up this machine (asks for your password once, and for a name; Enter gives "me"):
        netcap install
      Then try it, and undo it:
        netcap on me --up 2 --down 2
        netcap off me
      Add another device you can ssh into:
        netcap install --ssh <host>
    EOS
  end

  test do
    assert_match "usage: netcap", shell_output("LC_ALL=C #{bin}/netcap --help")
    assert_equal "netcap #{version}", shell_output("#{bin}/netcap --version").strip
  end
end
