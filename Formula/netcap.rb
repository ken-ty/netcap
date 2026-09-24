# このリポジトリ自体を tap にしている。入れ方は README の「CLI を入れる」。
class Netcap < Formula
  desc "Ken の常用機 3 台の WAN 帯域上限を 1 本の CLI で on / off する"
  homepage "https://github.com/ken-ty/netcap"
  url "https://github.com/ken-ty/netcap.git",
      tag:      "v0.3.0",
      revision: "d19c4bc3df0b1d6ad9f94073c2bb6e725fd33c86"
  head "https://github.com/ken-ty/netcap.git", branch: "main"

  depends_on :macos
  depends_on "python@3.13"

  def install
    # bin/netcap は自分の位置から ../examples を案内し、mac/ は端末側に入れるので、木ごと libexec に置く
    libexec.install Dir["*"] - ["Formula"]
    inreplace libexec/"bin/netcap", %r{\A#!/usr/bin/env python3$},
              "#!#{Formula["python@3.13"].opt_bin}/python3.13"
    bin.install_symlink libexec/"bin/netcap"
  end

  def caveats
    <<~EOS
      管理する端末とプロファイルは ~/.config/netcap/ に書きます (例は #{opt_libexec}/examples):
        mkdir -p ~/.config/netcap && cp #{opt_libexec}/examples/* ~/.config/netcap/

      brew が入れるのは CLI だけです。端末側の netshape と netcap-agent は root が要るので別に入れます:
        sudo bash #{opt_libexec}/mac/install.sh --boot off
    EOS
  end

  test do
    assert_match "usage: netcap", shell_output("#{bin}/netcap --help")
  end
end
