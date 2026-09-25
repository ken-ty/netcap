# 設計

## 素通しにする宛先

インターネットに出ない宛先は絞らない。

| 宛先 | 範囲 |
| --- | --- |
| プライベート IP | 10/8、172.16/12、192.168/16 |
| CGNAT 帯 (Tailscale などの VPN) | 100.64/10 |
| ループバック、リンクローカル、マルチキャスト | 127/8、169.254/16、224/4 |

インターネット宛てでも ICMP と DNS (53) は絞らない。ping で遅延を監視するとき、shaper の待ち行列を
測ってしまわないため。Windows は DNS だけを明示的に除外していて、ICMP は確かめていない。

100.64/10 で素通しになるのは VPN のトンネルの内側だけ。インターネットへ出る外側の UDP は絞られる。

## root で動くものの置き場所

パスワード無しで root になれる本体は、親ディレクトリまで root だけが書ける場所に置く。利用者が
書けるディレクトリにあると、差し替えるだけで root が取れる (Homebrew を使ってきた Mac では
`/usr/local/sbin` がそうなっていることがある)。

- macOS: 本体は `/Library/PrivilegedHelperTools`、設定は `/etc`。`install.sh` が `/` まで所有者と
  権限を検査する。設定は source せず、数値の key=value として読む
- Linux: 本体は `/usr/libexec/netcap`、設定は `/etc`。検査は macOS と同じ
- Windows: `C:\ProgramData` は Users が書けるので、`install.ps1` が継承を切る

## pf と dnctl は自分の分だけ触る

- ルールはアンカー `com.apple/netcap-netshape` に読み込み、`/etc/pf.conf` は差し替えない
- `off` はアンカーを空にし、pipe 1 / 2 だけ消す。pf の有効化は `pfctl -E` の token で数え、自分の分だけ返す

pipe 番号は機械全体で共有なので、pipe 1 / 2 を使う Network Link Conditioner などとは同時に使えない。

## tc は自分の qdisc だけ触る (Linux)

- 既定の経路のインターフェースの root qdisc を自分の HTB (handle `ca9:`) に差し替え、`off` で消して既定に戻す。
  他の道具が root に qdisc を置いていれば、差し替えずに止まる
- 下りは ingress を `ifb-netcap` に折り返して、そこの HTB で絞る
- 素通しの宛先と ICMP・DNS は、絞らないクラスへ振り分ける

## macOS の status の下りに付く `*`

macOS の `dnctl` は 2 本目の pipe の帯域を表示できない (macOS 26)。下りは、pipe の実在だけ確かめ、
値は `on` 時の記録から読んで `*` を付ける。

## Windows は再起動しても状態が残る

再起動で消える ActiveStore は宛先の条件を保持せず、LAN 宛ても絞ってしまった。そのため永続の
保存先に置いている。

## 実測

macOS の端末 1 台、4G 相当の回線、`scripts/measure.sh` (2026-09-21)。

| 条件 | 下り (Mbit/s) | 上り (Mbit/s) |
| --- | ---: | ---: |
| off | 18.5〜32.8 | 5.2〜8.0 |
| on 1/1 | 0.52〜0.72 | 0.35〜0.85 |
| set 2/3 | 2.04〜2.65 | 0.90〜1.33 |

上限未満に収まるのは、その端末の他の通信が同じ pipe を分け合うため。

## 成り立ち

作者の FWA (5G のホームルーター) 回線で、別の端末のダウンロードがLoLの遅延を 500〜1,600ms に
押し上げた。快適にLoLをやる為に都度他のPCの電源を落とすのは馬鹿げている。
ルーターに QoS が無いので端末の側で絞ることにし、その端末を上下 1 Mbit/s にすると
遅延は中央値 44ms に戻った。これが netcap が生まれた経緯だ。
このおかげで、 gamePCでLoLをやりながら、serverは止まることなく動き続けるし、
別端末ではclaudeを回し続けることができている。
