# 端末側のセットアップ

netcap の CLI は、端末に何を頼むときも ssh 越しに端末側の agent を叩く。agent が動詞と引数を
検査し、root / 管理者が要るものだけ本体 (shaper) に渡す。この文書は端末側に入れるものと、
その許可の決め方を扱う。最短の手順は [README](../README.ja.md#quick-start) にある。

## スクリプトの在り処

端末側のスクリプトはリポジトリの `mac/` と `win/` にある。brew で CLI を入れたなら
`$(brew --prefix)/opt/netcap/libexec/` の下にある。

brew を使わないなら、clone か curl で取ってくる。CLI もこの中の `bin/netcap` を PATH に通せば動く。

```bash
# git clone
git clone https://github.com/ken-ty/netcap.git ~/.local/share/netcap

# curl (git を使わない)
mkdir -p ~/.local/share/netcap
curl -fsSL https://github.com/ken-ty/netcap/archive/refs/tags/v0.5.0.tar.gz \
  | tar xz --strip-components 1 -C ~/.local/share/netcap

# CLI を使うなら
ln -s ~/.local/share/netcap/bin/netcap ~/.local/bin/netcap
```

curl で入れた場合、`netcap --version` は `unknown` を返す (版をタグから読むため)。

Windows では、git が無くても curl と tar が標準で入っている。

```powershell
curl.exe -fsSL -o netcap.zip https://github.com/ken-ty/netcap/archive/refs/tags/v0.5.0.zip
tar -xf netcap.zip
cd netcap-0.5.0
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

pf / dnctl は状態を読むだけでも root が要るので、無人で叩くには sudoers が要る。許す動詞は
`status` / `get` / `off` / `on` / `on <数値> <数値>` / `set <数値> <数値>` に限っている。
sudoers に書くユーザーは `sudo` を呼んだユーザー。別のユーザーにするなら `NETCAP_USER=<user>` を渡す。

- `--boot on`: 起動時に既定の上限 (初期値は上下 1 Mbit/s。`netcap set` で変える) をかける
- `--boot off`: 起動時は素のまま。`netcap on` のときだけ絞る

外すのは `sudo bash mac/uninstall.sh`。

v0.5.0 までは本体が `ken-ty-netshape` という名前だった。`install.sh` を流し直せば旧名を外して
既定値を引き継ぐ。上限がかかっていた場合は外れるので、`netcap on` でかけ直す。

## Windows

**Windows は操作される側にだけなれる。** 管理者の PowerShell で:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File win\install.ps1
```

`C:\ProgramData\netcap\` に `netshape.ps1` (本体) / `netcap-agent.ps1` (入口) / `netcap-check.ps1`
(実測) / `uninstall.ps1` を置く。外すのは `C:\ProgramData\netcap\uninstall.ps1`。

mac 版とはできることが違う。

| | mac (pf + dummynet) | Windows (NetQosPolicy) |
| --- | --- | --- |
| 下りを絞る | できる | **できない**。QoS ポリシーは送信側にしか効かない。表では `非対応` |
| 再起動したとき | `--boot on` なら上限をかけ直す。`off` なら素のまま | **`on` / `off` の状態がそのまま残る** (`boot=keep`) |
| 操作する側 (CLI) | なれる | なれない |

上りの制限・素通しの宛先・`status` / `get` / `set` / `check` は両方で同じように動く。

## 許可は操作される側が決める

**どの動詞を許すかは、操作される端末の `authorized_keys` が決める。** netcap 専用の鍵を作り、
端末側でその鍵を forced command に固定する。

```bash
# 操作する側 (1 回だけ)
ssh-keygen -t ed25519 -f ~/.ssh/netcap -C netcap@<この機械> -N ""
```

操作される Mac の `~/.ssh/authorized_keys` に 1 行 (公開鍵は `~/.ssh/netcap.pub`):

```text
restrict,command="/Library/PrivilegedHelperTools/netcap-agent --allow 'status get check on off set'" ssh-ed25519 AAAA… netcap@<この機械>
```

操作される Windows では、管理者の鍵なら `C:\ProgramData\ssh\administrators_authorized_keys` に:

```text
restrict,command="powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\netcap\netcap-agent.ps1 --allow 'status get check on off set'" ssh-ed25519 AAAA… netcap@<この機械>
```

操作する側の `~/.ssh/config` に、その鍵を使う Host を切り、`hosts` の経路に書く。

```text
Host server-netcap
  HostName server.example.ts.net
  User admin
  IdentityFile ~/.ssh/netcap
  IdentitiesOnly yes
```

- `--allow` に並べた動詞しか通らない。上限を外させたくない端末は `'status get check'` にする。
  netcap からは読めるが、`on` / `off` / `set` は `denied` になる
- `restrict` で pty・転送・エージェント転送を切る。その鍵で ssh してもシェルは取れない
- 頼まれた中身 (`$SSH_ORIGINAL_COMMAND`) は空白で区切るだけで、グロブも `$(…)` も解釈しない。
  引数は数値だけ、`check` は `--bytes <数値>` だけ受ける
- Mac では agent を抜けても sudoers が動詞単位で止める。Windows の管理者の ssh セッションは
  昇格した状態で動くので、この二段目が無く、forced command が唯一の関門になる

操作する側は `hosts` にある端末しか叩かず、操作される側は `authorized_keys` にある鍵の、許した
動詞しか受けない。

## 表の読み方

`status` / `get` / `check` の表は、どれも `reach` と `note` の列を持つ。`status` はさらに `cap` を持つ。

### reach — その端末に届いて、頼めたか

| reach | 意味 |
| --- | --- |
| `ok` | 動いた |
| `unreachable` | ssh が届かない (終了コード 255) |
| `timeout` | 時間内に応答が返らない |
| `no-agent` | 端末側に agent が入っていない |
| `no-sudo` | 端末側の sudoers に無い (mac) |
| `denied` | 端末側がその動詞を許していない (forced command の `--allow`) |
| `error` | 届いたが、端末側が 0 以外で終わった |

### cap — いま上限がかかっているか

設定ではなく、pf の pipe や QoS ポリシーの実物から決める。

| cap | 意味 |
| --- | --- |
| `on` | 上限がかかっている |
| `off` | かかっていない |
| `partial` | pf のルールと dnctl の pipe が食い違っている (mac)。`on` か `off` を打ち直せば揃う |
| `?` | reach が `ok` でないので読めていない |

### note — うまくいかなかった理由

reach が `ok` なら空。それ以外は、端末から返った出力 (stdout と stderr) の最後の 1 行を出す。
ssh のエラー、`netcap-agent:` で始まる agent の拒否、`sudo:` のメッセージのどれかになることが多い。
全文は `--json` の `raw` にある。
