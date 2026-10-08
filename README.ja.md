<p align="center">
  <img src="docs/logo.svg" alt="netcap" height="72">
</p>

<p align="center">
  <a href="https://github.com/ken-ty/netcap/tags"><img alt="version" src="https://img.shields.io/github/v/tag/ken-ty/netcap?label=version&sort=semver"></a>
  <a href="LICENSE"><img alt="license" src="https://img.shields.io/github/license/ken-ty/netcap"></a>
  <img alt="platform" src="https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey">
  <img alt="python" src="https://img.shields.io/badge/python-3-blue">
</p>

<p align="center">
  <a href="README.md">English</a> · 日本語
</p>

> この文書は [README.md](README.md) の翻訳です。英語版と食い違うときは英語版が正です。

**ホストベースの QoS。QoS 対応ルーターは要らない。** 同じ回線を使う複数の端末の WAN 向け帯域を、1 台の端末から 1 コマンドで絞る (throttle) / 戻す CLI。
各端末が自分で上限をかけるので、ルーターは今あるもの (プロバイダー支給のものでも) で構わない。

<p align="center">
  <img src="docs/overview.svg" alt="netcap use game で laptop と server を絞り、gamepc には回線を丸ごと残す" width="760">
</p>

- 絞るのはインターネットとの通信だけ。同じ LAN の機器どうしの通信は絞らない
- 例外として、インターネット宛てでも ping (ICMP) と DNS は絞らない。遅延の測定を歪めないため
- 端末へは ssh で頼み、許可は操作される側の `authorized_keys` が決める
- ルーターの QoS と違い、通信に優先度は付けない。選んだ端末に上限をかけて、回線の残りを空けておく
- macOS の pf + dummynet、Linux の `tc`、Windows の NetQosPolicy を、どの OS でも同じ動詞で扱う
- 端末に常駐するものは無い。`netcap install` が置くのは、netcap が呼んだときだけ動く小さなスクリプト。
  OS のスケジューラーがそれを動かすのは、`--for` の期限に上限を外すときと、`--boot on` での起動時だけ

## Quick Start

### 1. インストール

```bash
brew tap ken-ty/netcap https://github.com/ken-ty/netcap
brew trust ken-ty/netcap   # Homebrew 7 以降は信頼した tap の formula しか読まない
brew install netcap
netcap install          # この端末を使える状態にする。名前を聞かれる (Enter で "me")
```

`netcap install` はパスワードを 1 回聞く (sudo。Windows は管理者として実行する)。要るのは Python 3 だけ。
Homebrew 7 より前には `brew trust` が無く、要りもしない。その行は飛ばす。
brew を使わないときは [docs/host-setup.ja.md](docs/host-setup.ja.md) を見る。

### 2. 自分の回線で試す

```bash
netcap on me --up 2 --down 2 --for 10m   # この端末を上り下り 2 Mbit/s に 10 分だけ絞る。過ぎたら自分で外れる
netcap status                            # 実際にかかっている上限と、いつ外れるかを読む
netcap off me                            # 今すぐ外す
```

> **困ったら `netcap off me` で戻る。** 手元で動くので、回線が細くて何も読み込めないときでも効く。
> netcap 自体が動かないときは、端末側を直接叩く:
>
> ```bash
> sudo /Library/PrivilegedHelperTools/netcap-netshape off          # macOS
> sudo /usr/libexec/netcap/netcap-netshape off                      # Linux
> ```
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File C:\ProgramData\netcap\netshape.ps1 off   # Windows (管理者として)
> ```
>
> macOS と Linux は再起動でも上限が外れる。ただし `--boot on` で入れた端末では既定の上限がかかり直す。
> Windows は再起動しても残る。

### 3. 他の端末を管理する

`ssh` で入れる端末なら足せる。ssh の宛先 (`~/.ssh/config` の Host でよい) を渡す:

```bash
netcap install --ssh gamepc     # 向こうに agent を入れる。名前を聞かれる (Enter で "gamepc")
netcap status all
netcap on gamepc --up 5 --down 5
```

端末側のファイルを送ってインストーラを流し (向こうの sudo パスワード、Windows は管理者アカウント)、
向こうでは netcap の動詞しか実行できない netcap 専用の ssh 鍵を登録する。

複数の端末をまとめて動かすなら、レシピ (profiles) を `~/.config/netcap/profiles` に書く:

```text
# 名前  端末=上り/下り (Mbit/s) か off
game    me=2/2  gamepc=off
none    me=off  gamepc=off
```

```bash
netcap use game      # レシピを適用する
netcap use game --for 2h   # 同じ。絞った各端末が 2 時間後に自分で外す
netcap use none      # 全部外す
```

守る端末だけを名指ししてもよい。netcap がほかの全端末を絞り、その端末を前後で測る。

```bash
netcap protect gamepc --up 2 --down 2             # gamepc 以外を全部絞り、gamepc の check を前後で見せる
netcap protect gamepc --up 2 --down 2 --load 5    # その間ほかの端末も 5 MB ずつ転送し、遅延が良くなったかを言う
netcap protect gamepc --up 2 --down 2 --for 1h    # ほかの端末は 1 時間後に自分で上限を外す
netcap protect --off                              # 各端末を元の状態に戻す
```

`--load` が無いと、測定に差が出るのは、そのときほかの端末がたまたま回線を使っていた場合だけ。`--load` はその通信を
作るので通信量を使う: 約 4 × MB × ほかの端末の数 (最初に表示する)。
守る端末自身はどちらでも 4 MB ほど送受信する (前後それぞれで上り 1 MB と下り 1 MB)。
ほかの端末のうち Windows のものは、`--with-download` で入れていなければ上りしか絞れない。

名前は `netcap rename me laptop` で変えられる。外すときは `netcap uninstall gamepc`。
ファイルの書式は [docs/configuration.ja.md](docs/configuration.ja.md)、install が端末に何を置くかは [docs/host-setup.ja.md](docs/host-setup.ja.md)。

## 対応 OS

| 役割 | macOS | Linux | Windows |
| --- | --- | --- | --- |
| 操作する側 (CLI) | ✅ | ✅ | ✅ |
| 操作される側 | ✅ 上り・下り (pf + dummynet) | ✅ 上り・下り (tc) | ⚠️ 上り (NetQosPolicy)。下りは `netcap install <name> --with-download` で入れたときだけ (WinDivert、x64) |

機能ごとの一覧は [docs/platforms.ja.md](docs/platforms.ja.md)。

## ユースケース

- **遅延を守る** — ゲームやビデオ会議の間、他の端末の大きなダウンロードで回線が詰まらないようにする
- **バックグラウンドの通信を抑える** — OS の更新、クラウド同期、バックアップが回線を使い切るのを防ぐ
- **容量に上限がある回線で使いすぎを防ぐ** — モバイル回線やテザリングで、端末ごとに上限をかける
- **細い回線を再現して試す** — アプリや配信が遅い回線でどう動くかを、実機で確かめる
- **時間帯で切り替える** — cron や launchd から `netcap use` を呼び、夜間だけ絞るといった運用にする

## 使い方

```text
netcap status [<host>|all] [--json]         実際にかかっている上限を読む
netcap get    [<host>|all] [--json]         設定 (既定値・起動時の挙動) を読む
netcap on     <host>|all [--up N --down N] [--for 30m]  上限をかける (flag は今回だけ。--for はその時間で外れる)
netcap off    <host>|all                    上限を外す (boot=on なら再起動で既定の上限がかかり直す)
netcap set    <host>|all --up N --down N    既定を書き換える
netcap check  [<host>|all] [--bytes N] [--json]  実測 (curl の上下 + ping。--bytes: 転送する量。100 MB まで)
netcap use    <profile> [--for 30m]         プロファイルを適用 (--for: 絞った各端末がその時間で外す)
netcap profiles                             プロファイル一覧
netcap protect <host> [--up N --down N] [--load MB] [--for 30m]  ほかの全端末を絞り、<host> の check を前後で見せる
netcap protect --off                        各端末を元の状態に戻す
netcap install [<name>] [--ssh DEST] [--boot on|off]  端末に agent を入れて登録する (--boot on: 起動時に絞る)
netcap uninstall <host> [--config-only]     この管理する側の鍵と登録を外す (agent は最後の 1 つと一緒に外れる)
netcap rename <old> <new>                   端末の名前を変える
netcap export                               hosts と profiles を JSON で出す (鍵は含まない)
netcap import <file|->                      それを読み戻す (--replace で上書き)
netcap doctor [<host>|all] [--json]         各端末の netcap の鍵が forced command に固定されているか確かめる
netcap <command> -v                         表に出ない項目も表示する (-vv: 機器の生の出力も)
netcap <command> -q                         結果だけを出す。進み具合・ヒント・注記は出さない
netcap help [<command>|exit-codes]          -h と同じヘルプ。exit-codes は終了コードの意味の一覧
netcap completion bash|zsh                  補完スクリプトを出す。例: eval "$(netcap completion zsh)"
netcap --version                            -V、netcap version でも可
```

値は Mbit/s で、小数も使える。`0` はエラー (何も変わらない)。上限を外すなら `off`。
再起動・電源断・管理する側が複数あるときの挙動は [docs/operations.ja.md](docs/operations.ja.md)。

ヘルプとエラーはロケール (`LANG`) に従い、日本語でも出る。英語で見たいときは `LC_ALL=C netcap -h`。

補完を使うには、`~/.bashrc` に `eval "$(netcap completion bash)"` を足す。zsh では `~/.zshrc` の
`autoload -Uz compinit && compinit` より後に `eval "$(netcap completion zsh)"` を足す (無いと zsh が
`compdef: command not found` を出す)。

## ドキュメント

- [docs/why.ja.md](docs/why.ja.md) — ルーターの QoS や他のツールとの比較。netcap を選ぶとき
- [docs/vision.ja.md](docs/vision.ja.md) — netcap が何のためにあり、どこへ向かい、何をしないか
- [docs/host-setup.ja.md](docs/host-setup.ja.md) — 端末側のセットアップと許可
- [docs/configuration.ja.md](docs/configuration.ja.md) — 設定ファイルの書式
- [docs/operations.ja.md](docs/operations.ja.md) — 再起動・電源断・管理する側が複数のとき
- [docs/platforms.ja.md](docs/platforms.ja.md) — OS ごとの対応状況
- [docs/compatibility.ja.md](docs/compatibility.ja.md) — CLI の各リリースがどの版の agent と動くか
- [docs/design.ja.md](docs/design.ja.md) — 設計判断と実測
- [SECURITY.ja.md](SECURITY.ja.md) — 脅威モデルと脆弱性の報告先
- [CHANGELOG.md](CHANGELOG.md) — 各リリースで変わったこと (英語のみ)
- [CONTRIBUTING.md](CONTRIBUTING.md) — 開発とリリース

## License

[MIT](LICENSE)
