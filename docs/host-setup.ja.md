# 端末側のセットアップ

[English](host-setup.md) · 日本語

> この文書は [host-setup.md](host-setup.md) の翻訳です。英語版と食い違うときは英語版が正です。

CLI は ssh 越しに端末側の agent を叩き、agent が動詞と引数を検査して本体に渡す。
最短の手順は [README](../README.ja.md#quick-start) にある。

## `netcap install` がやること

`netcap install` (この端末) と `netcap install --ssh DEST` (別の端末) は下のすべてをやる。このページの残りは、
中身の説明と、手で入れるときのためにある。

1. OS を判定する (`uname`、Windows なら PowerShell)
2. `mac/`、`linux/`、`win/` を向こうの一時ディレクトリへ送る。agent には CLI の版を書き込む
3. インストーラを流す: `sudo bash …/install.sh --boot off` (向こうの sudo パスワード)、Windows なら `install.ps1`
   (ssh のユーザーが管理者であること)。終わったら一時ディレクトリを消す
4. 手元に `~/.ssh/netcap` が無ければ作り、向こうに forced command の行
   ([下](#許可は操作される側が決める)) を足す。鍵がもうあれば足さない
5. `hosts` に端末を足す。名前を 1 回聞く

更新は `netcap install <名前>` をもう一度流す。`netcap get` の `agent` 列に各端末の版が出る。
`netcap uninstall <名前>` で全部を戻す (`--config-only` はもう無い端末の登録だけ消す)。

## スクリプトの在り処

リポジトリの `mac/`、`linux/`、`win/`。brew で入れたなら `$(brew --prefix)/opt/netcap/libexec/` の下。
brew を使わないなら clone か curl で取る。CLI は `bin/netcap` を PATH に通せば動く。

```bash
# git clone
git clone https://github.com/ken-ty/netcap.git ~/.local/share/netcap

# curl (git を使わない)
mkdir -p ~/.local/share/netcap
curl -fsSL https://github.com/ken-ty/netcap/archive/refs/tags/v0.7.0.tar.gz \
  | tar xz --strip-components 1 -C ~/.local/share/netcap

# CLI を使うなら
ln -s ~/.local/share/netcap/bin/netcap ~/.local/bin/netcap
```

curl で入れると `netcap --version` は `unknown` になる。Windows でも curl と tar は標準で使える。

```powershell
curl.exe -fsSL -o netcap.zip https://github.com/ken-ty/netcap/archive/refs/tags/v0.7.0.zip
tar -xf netcap.zip
cd netcap-0.7.0
python bin\netcap --version   # CLI として使うなら
```

## macOS

```bash
sudo bash mac/install.sh --boot on|off
```

| パス | 役割 |
| --- | --- |
| `/Library/PrivilegedHelperTools/netcap-agent` | netcap が叩く入口。forced command にも使う |
| `/Library/PrivilegedHelperTools/netcap-netshape` | 本体 (root で動く。pf + dummynet) |
| `/usr/local/bin/netcap-check` | 実測 (curl と ping だけなので root 不要) |
| `/etc/pf.anchors/netcap-netshape` | pf のルール |
| `/etc/sudoers.d/netcap-netshape` | 呼び出したユーザーに、本体の決まった動詞だけ NOPASSWD |
| `/Library/LaunchDaemons/netcap-netshape.plist` | `--boot on` のときだけ |

- `--boot on` は起動時に既定の上限 (初期値 1/1。`netcap set` で変える) をかける。`off` は素のまま
- sudoers は `sudo` を呼んだユーザーに、本体の決まった動詞だけを許す。別のユーザーなら `NETCAP_USER=<user>`
- 外すのは `sudo bash mac/uninstall.sh`
- v0.5.0 までの旧名 `ken-ty-netshape` は、`install.sh` を流し直せば外れる。上限も外れるので `netcap on` でかけ直す

## Linux

```bash
sudo bash linux/install.sh --boot on|off
```

| パス | 役割 |
| --- | --- |
| `/usr/libexec/netcap/netcap-agent` | netcap が叩く入口。forced command にも使う |
| `/usr/libexec/netcap/netcap-netshape` | 本体 (root で動く。tc) |
| `/usr/local/bin/netcap-check` | 実測 (root 不要) |
| `/etc/sudoers.d/netcap-netshape` | 呼び出したユーザーに、本体の決まった動詞だけ NOPASSWD |
| `/etc/systemd/system/netcap-netshape.service` | `--boot on` のときだけ |

- 既定の経路のインターフェースを絞る。下りは `ifb` で受信を折り返して絞る
- `--boot`・sudoers・`NETCAP_USER` は macOS と同じ。外すのは `sudo bash linux/uninstall.sh`

## Windows

管理者の PowerShell で:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File win\install.ps1
```

`C:\ProgramData\netcap\` に入る。外すのは `C:\ProgramData\netcap\uninstall.ps1`。

mac との違いは 2 つ。下りは絞れない (表では `unsupported`)。`on` / `off` の状態は再起動しても残る (`boot=keep`)。

## 許可は操作される側が決める

**どの動詞を許すかは、操作される端末の `authorized_keys` が決める。** netcap install は netcap 専用の鍵を作り、
端末側でその鍵を forced command に固定する。手でやるなら:

```bash
# 操作する側 (1 回だけ)
ssh-keygen -t ed25519 -f ~/.ssh/netcap -C netcap@<この機械> -N ""
```

操作される Mac の `~/.ssh/authorized_keys` に 1 行 (公開鍵は `~/.ssh/netcap.pub`):

```text
restrict,command="/Library/PrivilegedHelperTools/netcap-agent --allow 'status get check on off set'" ssh-ed25519 AAAA… netcap@<この機械>
```

操作される Linux では、agent のパスを `/usr/libexec/netcap/netcap-agent` にする。

操作される Windows では、管理者の鍵なら `C:\ProgramData\ssh\administrators_authorized_keys` に:

```text
restrict,command="powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\netcap\netcap-agent.ps1 --allow 'status get check on off set'" ssh-ed25519 AAAA… netcap@<この機械>
```

`hosts` の経路には、ふだん使っている ssh の Host を書く。netcap は `~/.ssh/netcap` を最初に差し出すので、上の行がある端末では
agent しか動かず、無い端末では自分の鍵に戻る。このとき接続の共有も切る (`ControlPath=none`)。自分のログインで張った
`ControlMaster` の接続に相乗りすると、forced command を素通りするため。

- `--allow` に並べた動詞しか通らない。読むだけにしたい端末は `'status get check'` にする
- `restrict` でシェル・pty・転送を切る。agent は引数を空白で区切るだけで、シェルとして解釈しない
- Windows には sudoers に当たる二段目が無く、forced command が唯一の関門になる
- Windows の sshd は、`administrators_authorized_keys` が UTF-16 (Windows PowerShell 5 の `>>` が書く形) だったり、
  SYSTEM と Administrators 以外が書けたりすると、黙って無視する。UTF-8 で書き、新しく作ったファイルには
  `icacls <ファイル> /inheritance:r /grant:r "*S-1-5-18:F" "*S-1-5-32-544:F"` をかける

## 表の読み方

### reach — その端末に届いて、頼めたか

| reach | 意味 |
| --- | --- |
| `ok` | 動いた |
| `unreachable` | ssh が届かない (終了コード 255) |
| `timeout` | 時間内に応答が返らない |
| `no-agent` | 端末側に agent が入っていない |
| `no-sudo` | 端末側の sudoers に無い (mac、linux) |
| `denied` | 端末側がその動詞を許していない (forced command の `--allow`) |
| `error` | 届いたが、端末側が 0 以外で終わった |

### cap — いま上限がかかっているか (`status` のみ。実物から読む)

| cap | 意味 |
| --- | --- |
| `on` | 上限がかかっている |
| `off` | かかっていない |
| `partial` | pf のルールと dnctl の pipe が食い違っている (mac)。`on` か `off` を打ち直せば揃う |
| `?` | reach が `ok` でないので読めていない |

### agent — agent の版 (`get` のみ)

`netcap install` が書き込む。この列より前に入れた agent は `-`、clone から手で入れたものは `unknown`。
CLI と違っていたら `netcap install <名前>` を流す。

### note — うまくいかなかった理由

reach が `ok` でないとき、端末から返った出力の最後の 1 行。全文は `--json` の `raw` にある。
