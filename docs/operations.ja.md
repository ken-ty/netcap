# 運用

[English](operations.md) · 日本語

> この文書は [operations.md](operations.md) の翻訳です。英語版と食い違うときは英語版が正です。

再起動・電源断のとき、netcap を動かす機械が複数あるときに何が起きるか。

## 状態はどこにあるか

**上限は各端末の側にある。** netcap を動かす機械 (管理する側) が持つのは設定だけ:
`~/.config/netcap/` (hosts、profiles) と鍵 `~/.ssh/netcap`。コマンドとコマンドの間は、どちらの側でも何も動いていない。
だから管理する側の電源が入っていてもいなくても、端末は何も変わらない。

## 電源断と再起動

| 起きること | 結果 |
| --- | --- |
| 管理する側が電源断・スリープ・ネットワークから外れる | 端末は何も変わらない。上限は誰かが `off` するまで残る。時間で外れる仕組みは無い |
| macOS / Linux の端末が再起動、`boot=off` (既定) | 上限なしで起動する |
| macOS / Linux の端末が再起動、`boot=on` | 既定値 (`netcap get` の `default` 列) で上限をかけて起動する |
| Windows の端末が再起動 (`boot=keep`) | 再起動前のまま。かかっていればかかったまま、外れていれば外れたまま |
| コマンドを打ったとき端末が落ちている・届かない | `unreachable` か `timeout` と出る。他の端末は変わる。予約はされないので、戻ってきたらもう一度打つ (`netcap use` も同じ) |

管理する側が操作される側 (`me`) でもあるときは、それにも同じ行が当てはまる。

サーバーのように、いつでも回線を丸ごと持って戻ってきてほしい機械は `boot=off` のままにする。
入れ直すと `boot` も設定し直される。`netcap install <名前>` は `--boot on` を渡さない限り `--boot off` になる。

## 管理する側が複数

CLI が入っていればどの機械も管理する側になれて、同じ端末を何台からでも管理できる。
状態は端末の側にあるので、どこから `status` を読んでも同じものが見える。最後に打ったコマンドが勝つ。
排他制御は無いので、同じ端末に 2 台から同時にコマンドを送るのは避ける。

設定と鍵は管理する側ごとに持つ:

- **名前は管理する側ごと。** Mac mini の上の `me` は Mac mini 自身。同じ端末が、管理する側によって別の名前でもよい
- **profiles も管理する側ごと。** 同じレシピを使うなら `profiles` をコピーして、名前を合わせる
- **鍵は管理する側ごとに登録する。** 端末に agent は 1 つで、`authorized_keys` の行が管理する側の数だけ並ぶ

管理する側を増やすには、その機械に CLI を入れ、`netcap export` / `netcap import` で設定を持ってきて
([configuration.ja.md](configuration.ja.md#書き出しと取り込み))、そこから `netcap install` を流す。自分自身は `netcap install`、
取り込んだ各端末は `netcap install <名前>`。端末のインストーラがもう一度流れるが害は無い。気をつけるのは 2 つ:

- **管理する側ごとに別の ssh ユーザーで入ってよい。** インストーラは、流したユーザーを端末の sudoers に足し、
  すでにいるユーザーは残す (macOS / Linux)。netcap 0.10.0 以前は置き換えていたので、複数のユーザーで使う前に
  すべての管理する側の CLI を更新する
- **`--boot` を揃える。** 入れ直すと設定し直される (上)

1 つの管理する側からだけ外したいときは、`netcap uninstall <名前>` を使わない。全部の管理する側から agent が消える。
代わりに `netcap uninstall <名前> --config-only` を流し、端末の `~/.ssh/authorized_keys`
(Windows は `C:\ProgramData\ssh\administrators_authorized_keys`) から、その管理する側の行 (`netcap@<管理する側>` で終わる) を消す。

Windows でも CLI は日々のコマンドも `netcap install --ssh` も動く (どちらも CI で動かしている。後者は Windows の端末へ)。
