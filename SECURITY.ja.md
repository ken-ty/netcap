# セキュリティ

[English](SECURITY.md) · 日本語

> この文書は [SECURITY.md](SECURITY.md) の翻訳です。英語版と食い違うときは英語版が正です。

## 脆弱性の報告

非公開で報告してください。GitHub の **Security** タブ → **Report a vulnerability** から送れます。
それが使えないときは、詳細を書かずに「非公開の連絡先がほしい」とだけ issue を立ててください。

修正は最新のリリースに入ります。更新は `brew upgrade netcap` のあと、端末ごとに `netcap install <名前>`
(入れ直すと起動時の挙動も設定し直されるので、`--boot on` だった端末には `--boot on` を付ける)。

## 脅威モデル

netcap は 1 台から複数台のネットワーク設定を変えるので、信頼がどこにあるかを知っておく価値がある。

### 管理する側 (コントローラ) が信頼の起点

CLI を動かす機械は `~/.ssh/netcap` を持つ。`netcap install` が全端末に登録する鍵である。
無人で (cron などから) 動かせるよう、パスフレーズは付けていない。**このファイルを読める者は、登録済みの全端末で
netcap の動詞を実行できる。** 自分だけが読める状態に保ち (`ssh-keygen` はそう作る)、他の全機器に届く機械として
コントローラを守ること。

### netcap の鍵が漏れたときにできること

鍵は各端末で agent に固定されている (`restrict,command="… netcap-agent --allow '…'"`) ので、
`--allow` にある動詞しか動かない。シェルも pty も転送も無い。既定の動詞なら、鍵を持つ者は次ができる。

- 各端末の状態と設定を読む (`status`、`get`)、測定する (`check`)。`check --bytes N` は測定で転送する量を決め、
  agent は 100 MB を超える量を拒む (`N` は 1 から 100000000)
- 上限を変える・外す (`on`、`off`、`set`)
- Windows では WinDivert のドライバを外す (`unload-driver`)。何かが使っている間は端末が断る

**端末を遮断はできない。** `0` はどの OS でも拒否する。ただし `0.01/0.01` のような
ごく小さい上限はかけられ、誰かが `netcap off` するまでその端末の回線は使い物にならない。

### 各端末の関門

| OS | 1 つ目の関門 | 2 つ目の関門 |
| --- | --- | --- |
| macOS、Linux | forced command: `--allow` の動詞だけ、引数は数値だけ (ほかに通すのは `on` の末尾の `--for <秒>` と、`check` の 1 から 100000000 の `--bytes`) | sudoers: shaper の決まった動詞だけをパスワードなしで |
| Windows | forced command (検査は同じ) | 無し。管理者の ssh セッションは昇格して動く |

Windows では forced command が唯一の関門なので、`restrict,command="…"` の無い netcap の鍵の行を手で足すと、
昇格したシェルを渡すことになる。行は `netcap install` が書く。手で編集するより、そちらを使うこと。

root で動くファイルは、root だけが書けるディレクトリにしか置かない
(`/Library/PrivilegedHelperTools`、`/usr/libexec/netcap`、Windows では継承を切り所有者を Administrators にした `C:\ProgramData\netcap`)。
shaper は設定を数値として読み、スクリプトとしては実行しない。[docs/design.ja.md](docs/design.ja.md) を参照。

### Windows の下りを絞るのはカーネルドライバ

サードパーティのカーネルドライバ WinDivert 2.2.2 が Windows の端末に入るのは、同意したときだけ: 端末から打った
`netcap on` の問いに `y`、`netcap on --yes`、または `netcap install <名前> --with-download`。netcap の鍵が漏れても入れられ
ない。入れるのは forced command ではなく、あなた自身の ssh ログインを通すため。`netcap install <名前> --without-download`
は外して、問いもやめる。なぜこれを選び、何を受け入れたか:
[docs/adr/0001-cap-download-on-windows.ja.md](docs/adr/0001-cap-download-on-windows.ja.md)。

- netcap は同梱しない。インストーラが GitHub から公式のリリース zip を HTTPS で取ってきて、SHA-256 が `win/install.ps1` に
  固定した値でなければ断る。中から x64 のドライバと DLL とライセンスだけを `C:\ProgramData\netcap\windivert` に置き、
  ほかと同じ ACL をかける (書けるのは SYSTEM と Administrators だけ)
- ドライバを読み込むのは下りの shaper で、上限がかかっている間 SYSTEM として動く。`off` のあともドライバは次の再起動まで
  読み込まれたまま。netcap は自分からそのサービスを止めない。開いたハンドルの下で止めると以後のオープンが壊れるため
  ([basil00/WinDivert#406](https://github.com/basil00/WinDivert/issues/406))。`netcap unload-driver <名前>` は、何も使って
  いなければ外す
- [LOLDrivers](https://www.loldrivers.io/) は WinDivert 2.2 を悪性として載せている。攻撃者がセキュリティ製品を黙らせる
  ために持ち込むため。セキュリティソフトが報告・隔離することがあり (Malwarebytes と Bitdefender の例がある)、隔離されると
  `on` が失敗し、理由が `C:\ProgramData\netcap\download.log` に残る
- 署名の証明書は 2023 年に切れている。署名にタイムスタンプがあるので Windows はまだ読み込むが、ブロックするセキュリティソフトもある
- WinDivert はこの機械のどのパケットも捕まえて書き換えられる。そのファイルを差し替えられる者も同じことができる。だから
  フォルダは SYSTEM と Administrators しか書けず、入れ直すときにファイルを固定した値と照らす
- x64 のみ。WinDivert には署名済みの ARM64 ドライバが無い

### 対象外

- 端末自身の利用者。netcap は端末の持ち主の求めで上限をかけるもので、その端末の管理者権限を持つ者が
  上限を外すのを止めるためのものではない
- ssh の設定そのもの (ホスト鍵、sshd の設定、他に誰がログインできるか)。netcap はそれに依存する
