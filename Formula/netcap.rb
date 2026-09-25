# このリポジトリ自体を tap にしている。入れ方は README の Quick Start。
class Netcap < Formula
  desc "Cap the internet bandwidth of devices on your network from one device"
  homepage "https://github.com/ken-ty/netcap"
  url "https://github.com/ken-ty/netcap.git",
      tag:      "v0.5.0",
      revision: "0ba5920bffa74080957792502e63941acdd2ca34"
  head "https://github.com/ken-ty/netcap.git", branch: "main"

  license "MIT"

  depends_on "python@3.13"

  def install
    # bin/netcap は自分の位置から ../examples を案内し、mac/ と linux/ は端末側に入れるので、木ごと libexec に置く
    libexec.install Dir["*"] - ["Formula"]
    inreplace libexec/"bin/netcap", %r{\A#!/usr/bin/env python3$},
              "#!#{Formula["python@3.13"].opt_bin}/python3.13"
    # 版の正本はタグ。netcap --version が出す値をここで埋める
    inreplace libexec/"bin/netcap", '"@VERSION@"', "\"#{version}\""
    bin.install_symlink libexec/"bin/netcap"
  end

  def caveats
    <<~EOS
      管理する端末とプロファイルは ~/.config/netcap/ に書きます (例は #{opt_libexec}/examples):
        mkdir -p ~/.config/netcap && cp #{opt_libexec}/examples/* ~/.config/netcap/

      brew が入れるのは CLI だけです。端末側の netshape と netcap-agent は root が要るので別に入れます:
        sudo bash #{opt_libexec}/mac/install.sh --boot off     # macOS
        sudo bash #{opt_libexec}/linux/install.sh --boot off   # Linux
    EOS
  end

  test do
    assert_match "usage: netcap", shell_output("#{bin}/netcap --help")
    assert_equal "netcap #{version}", shell_output("#{bin}/netcap --version").strip
  end
end
