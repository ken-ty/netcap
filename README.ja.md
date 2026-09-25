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

同じ回線を使う複数の端末の WAN 向け帯域を、1 台の端末から 1 コマンドで絞る / 戻す CLI。
ルーターで帯域を制御できない回線でも、端末の側で上限をかけられる。

<p align="center">
  <img src="docs/overview.svg" alt="netcap use game で laptop と server を絞り、gamepc には回線を丸ごと残す" width="760">
</p>

- 絞るのはインターネットとの通信だけ。同じ LAN の機器どうしの通信は絞らない
- 例外として、インターネット宛てでも ping (ICMP) と DNS は絞らない。遅延の測定を歪めないため
- 端末へは ssh で頼み、許可は操作される側の `authorized_keys` が決める

## Quick Start

### 1. インストール

```bash
brew tap ken-ty/netcap https://github.com/ken-ty/netcap
brew install netcap
netcap install          # この端末を使える状態にする。名前を聞かれる (Enter で "me")
```

`netcap install` はパスワードを 1 回聞く (sudo。Windows は管理者として実行する)。要るのは Python 3 だけ。
brew を使わないときは [docs/host-setup.ja.md](docs/host-setup.ja.md) を見る。

### 2. 自分の回線で試す

```bash
netcap on me --up 2 --down 2    # この端末を上り下り 2 Mbit/s に絞る
netcap status                   # 実際にかかっている上限を読む
netcap off me                   # 外す
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
> macOS と Linux は再起動でも上限が外れる。Windows は再起動しても残る。

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
netcap use none      # 全部外す
```

名前は `netcap rename me laptop` で変えられる。外すときは `netcap uninstall gamepc`。
ファイルの書式は [docs/configuration.ja.md](docs/configuration.ja.md)、install が端末に何を置くかは [docs/host-setup.ja.md](docs/host-setup.ja.md)。

## 対応 OS

| 役割 | macOS | Linux | Windows |
| --- | --- | --- | --- |
| 操作する側 (CLI) | ✅ | ✅ | ✅ |
| 操作される側 | ✅ 上り・下り (pf + dummynet) | ✅ 上り・下り (tc) | ⚠️ 上りのみ (NetQosPolicy) |

## ユースケース

- **遅延を守る** — ゲームやビデオ会議の間、他の端末の大きなダウンロードで回線が詰まらないようにする
- **バックグラウンドの通信を抑える** — OS の更新、クラウド同期、バックアップが回線を使い切るのを防ぐ
- **容量に上限がある回線で使いすぎを防ぐ** — モバイル回線やテザリングで、端末ごとに上限をかける
- **細い回線を再現して試す** — アプリや配信が遅い回線でどう動くかを、実機で確かめる
- **時間帯で切り替える** — cron や launchd から `netcap use` を呼び、夜間だけ絞るといった運用にする

## 使い方

```text
netcap status [host|all] [--json]           実際にかかっている上限を読む
netcap get    [host|all] [--json]           設定 (既定値・起動時の挙動) を読む
netcap on     <host|all> [--up N --down N]  上限をかける (flag は今回だけ)
netcap off    <host|all>                    上限を外す (再起動で既定に戻る)
netcap set    <host|all> --up N --down N    既定を書き換える
netcap check  <host|all> [--json]           実測 (curl の上下 + ping)
netcap use    <profile>                     プロファイルを適用
netcap profiles                             プロファイル一覧
netcap install [name] [--ssh DEST]          端末に agent を入れて登録する
netcap uninstall <name>                     agent と登録を外す
netcap rename <old> <new>                   端末の名前を変える
netcap --version
```

ヘルプとエラーはロケール (`LANG`) に従い、日本語でも出る。英語で見たいときは `LC_ALL=C netcap -h`。

## ドキュメント

- [docs/host-setup.ja.md](docs/host-setup.ja.md) — 端末側のセットアップと許可
- [docs/configuration.ja.md](docs/configuration.ja.md) — 設定ファイルの書式
- [docs/design.ja.md](docs/design.ja.md) — 設計判断と実測
- [CONTRIBUTING.md](CONTRIBUTING.md) — 開発とリリース

## License

[MIT](LICENSE)
