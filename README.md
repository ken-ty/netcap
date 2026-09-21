# netcap

Ken の常用機 3 台 (MBP / mini / nucbox) の **WAN 向け通信の帯域上限** を、MBP から 1 本の CLI で
on / off / status する。

```
bin/netcap status [host|all] [--json] [--raw]
bin/netcap on  <host|all>
bin/netcap off <host|all>
bin/netcap set <host> <up_mbit> <down_mbit>
```

status は設定ファイルではなく **実物** (pf の pipe / QoS policy) を読む。`on` / `off` / `set` の
あとも実物を読み直して表にする。

## なぜ

家の回線は 5G/4G の FWA で CPE に QoS が無い。4G に落ちた夜は WAN 全体で下り 10 Mbit/s も出ず、
mini の DL 5〜10 Mbit/s だけで LoL 中の WAN 遅延が 500〜1,600ms に張り付いた。mini を上下
1 Mbit/s に絞ったら 60 秒で中央値 44ms に戻った (2026-09-20、A/B 済)。それを 3 台に広げる。

素通しにしているもの: 宅内 (RFC1918)、tailnet (100.64/10)、ICMP、DNS (53)。home-netmon の
probe が shaper の待ち行列を測らないようにするため。

## 端末ごとの実体

| host | OS | 経路 | 実体 | 起動時 |
| --- | --- | --- | --- | --- |
| `mbp` | macOS | ローカル | `mac/` — pf + dummynet (`/usr/local/sbin/ken-ty-netshape`) | 素のまま (`--boot off`) |
| `mini` | macOS | `ssh macmini-admin` | 同上。元は asakusa-t の `admin/netshape` | **上下 1 Mbit/s** (`--boot on`。Ken 決定) |
| `nucbox` | Windows | `ssh nucbox` | `win/` — NetQosPolicy。**下りは Windows 標準では絞れない** | (段 1 で決める) |

`off` は一時的な操作。再起動すればその端末の起動時既定に戻る。`set` も今回だけで、既定
(`/usr/local/etc/ken-ty-netshape.conf`) は変えない。

### macOS を入れる

```
sudo bash mac/install.sh --boot on|off
```

`/etc/sudoers.d/ken-ty-netshape` に「呼び出したユーザーは `ken-ty-netshape` だけ NOPASSWD」を
切る。netcap が無人で叩く (段 2 の画面) にはこれが要る。pf / dnctl は status を読むだけでも
root が要るため。外すのは `sudo bash mac/uninstall.sh`。

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

## 段 2 (予定)

MBP 上に 127.0.0.1 バインドの小さなローカルサーバーを立て、`netcap --json` を叩いて
1 画面にトグルを並べる。LAN に晒さない。認証は要らない。
