# セキュリティ

[English](SECURITY.md) · 日本語

> この文書は [SECURITY.md](SECURITY.md) の翻訳です。英語版と食い違うときは英語版が正です。

## 脆弱性の報告

非公開で報告してください。GitHub の **Security** タブ → **Report a vulnerability** から送れます。
それが使えないときは、詳細を書かずに「非公開の連絡先がほしい」とだけ issue を立ててください。

修正は最新のリリースに入ります。更新は `brew upgrade netcap` のあと、端末ごとに `netcap install <名前>`。

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

- 各端末の状態と設定を読む (`status`、`get`)、測定する (`check`)
- 上限を変える・外す (`on`、`off`、`set`)

**端末を遮断はできない。** `0` はどの OS でも拒否する。ただし `0.01/0.01` のような
ごく小さい上限はかけられ、誰かが `netcap off` するまでその端末の回線は使い物にならない。

### 各端末の関門

| OS | 1 つ目の関門 | 2 つ目の関門 |
| --- | --- | --- |
| macOS、Linux | forced command: `--allow` の動詞だけ、引数は数値だけ (`on` の末尾の `--for <秒>` を除く) | sudoers: shaper の決まった動詞だけをパスワードなしで |
| Windows | forced command | 無し。管理者の ssh セッションは昇格して動く |

Windows では forced command が唯一の関門なので、`restrict,command="…"` の無い netcap の鍵の行を手で足すと、
昇格したシェルを渡すことになる。行は `netcap install` が書く。手で編集するより、そちらを使うこと。

root で動くファイルは、root だけが書けるディレクトリにしか置かない
(`/Library/PrivilegedHelperTools`、`/usr/libexec/netcap`、Windows では継承を切り所有者を Administrators にした `C:\ProgramData\netcap`)。
shaper は設定を数値として読み、スクリプトとしては実行しない。[docs/design.ja.md](docs/design.ja.md) を参照。

### 対象外

- 端末自身の利用者。netcap は端末の持ち主の求めで上限をかけるもので、その端末の管理者権限を持つ者が
  上限を外すのを止めるためのものではない
- ssh の設定そのもの (ホスト鍵、sshd の設定、他に誰がログインできるか)。netcap はそれに依存する
