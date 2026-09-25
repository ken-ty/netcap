# This repository is its own tap. See Quick Start in the README for installation.
class Netcap < Formula
  desc "Cap the internet bandwidth of devices on your network from one device"
  homepage "https://github.com/ken-ty/netcap"
  url "https://github.com/ken-ty/netcap.git",
      tag:      "v0.6.0",
      revision: "8291374258eef4b53f3214a4fb075b7763b21faf"
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
      Define your devices and profiles in ~/.config/netcap/ (examples are in #{opt_libexec}/examples):
        mkdir -p ~/.config/netcap && cp #{opt_libexec}/examples/* ~/.config/netcap/

      brew installs only the CLI. netshape and netcap-agent on each device need root, so install them separately:
        sudo bash #{opt_libexec}/mac/install.sh --boot off     # macOS
        sudo bash #{opt_libexec}/linux/install.sh --boot off   # Linux
    EOS
  end

  test do
    assert_match "usage: netcap", shell_output("#{bin}/netcap --help")
    assert_equal "netcap #{version}", shell_output("#{bin}/netcap --version").strip
  end
end
