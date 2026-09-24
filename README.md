# netcap

Ken の常用機 3 台 (MBP / mini / nucbox) の **WAN 向け通信の帯域上限** を、MBP から 1 本の CLI で
on / off する。状態は実物 (pf の pipe / QoS policy) から読む。

```
netcap status [host|all] [--json]           実物 (pf の pipe / QoS policy) を読む
netcap get    [host|all] [--json]           設定 (既定値・起動時の挙動) を読む
netcap on     <host|all> [--up N --down N]  上限をかける。flag は今回だけ
netcap off    <host|all>                    上限を外す
netcap set    <host|all> --up N --down N    既定を書き換える (再起動後も効く)
netcap check  <host|all> [--json]           実測 (curl の上下 + ping)
netcap use    <profile>                     プロファイルを全台へ
netcap profiles                             プロファイル一覧
```

**`status` は設定ファイルではなく実物を読む。** `on` / `off` / `set` / `use` のあとも実物を
読み直して表にする。設定のほうは `get` が返す。

## コマンドの骨格は tailscale から借りた

- **`get` (設定) と `status` (実物) を別コマンドに割る。** 「再起動したらどうなるか」と
  「いまどうなっているか」は別の問いなので、1 表に混ぜない
- **`set` は永続する設定だけを変える。** いま絞っている最中なら、その値で張り直す
  (設定を変えることが、いまの状態を壊すことにならないように)
- **`on` の flag は「今回の完全な希望状態」。** `--up` と `--down` は両方セットで指定する。
  片方だけはエラーにした。「上りだけ絞ったつもりで下りが既定のまま」を構造で防ぐ

**動詞だけは借りていない。** tailscale は `up` / `down` だが、netcap のドメインは「上り/下り」で
既に up/down を使っている。`netcap up mini --up 2` は読めないので `on` / `off` のままにした。

**プロファイルは tailscale に無い概念。** netcap は 1 台ではなく 3 台をまとめて扱うので、
「LoL やるから他を絞る」を 1 コマンドにする `netcap use lol` を足した (`~/.config/netcap/profiles`)。

## なぜ

家の回線は 5G/4G の FWA で CPE に QoS が無い。4G に落ちた夜は WAN 全体で下り 10 Mbit/s も出ず、
mini の DL 5〜10 Mbit/s だけで LoL 中の WAN 遅延が 500〜1,600ms に張り付いた。mini を上下
1 Mbit/s に絞ったら 60 秒で中央値 44ms に戻った (2026-09-20、A/B 済)。それを 3 台に広げる。

素通しにしているもの: 宅内 (RFC1918)、tailnet (100.64/10)、ICMP、DNS (53)。home-netmon の
probe が shaper の待ち行列を測らないようにするため。

## 端末ごとの実体

| host | OS | 経路 | 実体 | 起動時 |
| --- | --- | --- | --- | --- |
| `mbp` | macOS | ローカル | `mac/` — pf + dummynet (`/Library/PrivilegedHelperTools/ken-ty-netshape`) | 素のまま (`--boot off`) |
| `mini` | macOS | `ssh macmini-admin` | asakusa-t の `admin/netshape` が入れた旧形 (`/usr/local/sbin`)。netcap からはまだ叩けない | **上下 1 Mbit/s** (`--boot on`。asakusa-t ADR 0021) |
| `nucbox` | Windows | `ssh nucbox` | `win/` — NetQosPolicy。**下りは Windows 標準では絞れない** | (段 1 で決める) |

`off` は一時的な操作。再起動すればその端末の起動時既定に戻る。既定そのものを変えるのは
`netcap set` (端末の `/etc/ken-ty-netshape.conf` を書き換える)。

### CLI を入れる

このリポジトリ自体を tap にしている (`Formula/netcap.rb`)。private なので、git が GitHub に
認証できること (`gh auth setup-git` など) が前提。

```
brew tap ken-ty/netcap https://github.com/ken-ty/netcap
brew install netcap
```

版を上げるときは、main に `vX.Y.Z` の注釈付きタグを打って push し、Formula の `tag` と
`revision` をそれに合わせる。brew が入れるのは CLI だけで、端末側の shaper は下の手順で別に入れる。

### macOS を入れる

```
sudo bash mac/install.sh --boot on|off
```

`/etc/sudoers.d/ken-ty-netshape` に「呼び出したユーザーは `ken-ty-netshape` の決まった動詞だけ
NOPASSWD」を切る (`status` / `get` / `off` / `on` / `on <数値> <数値>` / `set <数値> <数値>`)。
netcap が無人で叩くにはこれが要る。pf / dnctl は status を読むだけでも root が要るため。
実測の `/usr/local/bin/netcap-check` は curl と ping だけなので root は要らず、sudoers にも
入れていない。

### root で動くものの置き場所

NOPASSWD で root になれる本体は、**置き場所の親ディレクトリまで root だけが書ける**ことが前提。
利用者が書けるディレクトリにあると、ファイル自体が root 所有でも差し替えられ、`sudo -n` で
パスワード無しに root が取れる。Homebrew を使ってきた Mac では `/usr/local/sbin` や
`/usr/local/etc` が利用者の持ち物になっていることがある (この MBP がそうだった)。

だから本体は `/Library/PrivilegedHelperTools`、設定は `/etc` に置き、`install.sh` が親ディレクトリを
/ まで辿って所有者と書き込み権限を検査する。設定は source せず、数値の key=value として読む。

### pf と dnctl は自分の分だけ触る

- pf のルールはアンカー `com.apple/ken-ty.netshape` に読み込む。main ruleset (`/etc/pf.conf`) は
  差し替えない。macOS は起動時に `/etc/pf.conf` を読み、そこに `dummynet-anchor "com.apple/*"`
  があるので、アンカーのルールが評価される。main にアンカーの受け口が無ければ、差し替えずに止まる
- `off` はアンカーを空にし、pipe 1 / 2 だけ消す。`dnctl flush` はしない
- pf の有効化は参照カウント (`pfctl -E` の token) で、`off` は自分の token だけ返す

残る制約: dnctl の pipe 番号は機械全体で 1 つの空間なので、Network Link Conditioner など
pipe 1 / 2 を使う道具とは同時に使えない。

外すのは `sudo bash mac/uninstall.sh`。

### macOS の dnctl は pipe 2 の帯域を表示できない

`dnctl list` は 2 本目以降の pipe の見出し行を出さない (`dnctl pipe 2 show` は空、`dnctl -s list`
は segfault。2026-09-21 MBP / macOS 26 で実測)。だから status の下りは、pipe が 2 本あることを
dnctl で確かめたうえで、値だけ `on` 時の記録 (`/var/run/com.ken-ty.netshape.applied`) から読み、
表では `*` を付ける。値が本当に効いていることは実測で確認した (下の表)。

## 実測 (MBP、2026-09-21 18:49〜20:10、`scripts/measure.sh`)

各行は 1 回の転送。curl の下り・上りと、その最中の 1.1.1.1 への ping (ICMP は shaper を通らない)。

| 条件 | 下り | 上り | ping 中央値 / p95 / max (ms) |
| --- | ---: | ---: | --- |
| off ×3 | 18.5〜32.8 | 5.2〜8.0 | 38〜46 / 60〜315 / 255〜477 |
| **on 1/1 ×3** | **0.52〜0.72** | **0.35〜0.85** | 32〜37 / 48〜184 / 77〜260 |
| off ×1 | 30.5 | 5.4 | 51 / 311 / 317 |
| off ×1 | 24.7 | 7.3 | 35 / 80 / 406 |
| **set 2/3 ×2** | **2.04〜2.65** | **0.90〜1.33** | 38 / 116〜148 / 223〜298 |
| off ×1 | 32.0 | 6.9 | 40 / 175 / 215 |

- 実測で言えること: curl は上限に張り付く (1/1 で 1 Mbit/s 未満、2/3 で下り 2.0〜2.7 と上りより
  高い = 上下が別々の pipe で効いている)。上限未満に収まるのは、この MBP 自身の他の通信
  (Claude Code の API など) が同じ pipe を分け合うため
- 実測で言えること (弱い): 1/1 のとき ping の p95 は 3 本中 2 本で 50ms 前後に収まった。
  off は 60〜315。ただし off の ping サンプルは転送が数秒で終わるため 9〜10 個しかなく、
  ばらつきが大きい。「跳ねない」の断定には mini から見た WAN 遅延 (home-netmon) と
  突き合わせるほうが確か
- 今夜の WAN は下り 20〜33 / 上り 5〜8 Mbit/s (4G 相当)。バンドは記録していない

## 端末とプロファイルは利用者のもの (`~/.config/netcap/`)

**どの端末を管理するか (`hosts`) と、まとめて動かす組 (`profiles`) はコードに持たない。**
netcap は `~/.config/netcap/` (`$XDG_CONFIG_HOME` / `$NETCAP_CONFIG_DIR` で差し替え可) から読む。
brew で入れた版の中 (Cellar) に置くと、編集できず `brew upgrade` のたびに消えるため。

どちらも 1 行 1 件のテキストで、`#` から後はコメント。書き方は `examples/` にある。

```
$ cat ~/.config/netcap/hosts
mbp     mac  -               # 名前 OS 経路 (~/.ssh/config の Host 名。この機械自身なら -)
mini    mac  macmini-admin
nucbox  win  nucbox

$ netcap profiles             # ~/.config/netcap/profiles をそのまま表にしたもの
lol    mbp=2/2  mini=1/1  nucbox=off
none   mbp=off  mini=off  nucbox=off
quiet  mbp=1/1  mini=1/1  nucbox=off

$ netcap use lol
```

`profiles` のファイルの形は `netcap profiles` の表示と同じにしてある。書かなかった端末は触らない。

## 段 2 (予定)

MBP 上に 127.0.0.1 バインドの小さなローカルサーバーを立て、`netcap --json` を叩いて
1 画面にトグルを並べる。LAN に晒さない。認証は要らない。
