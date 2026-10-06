# 設定ファイル

[English](configuration.md) · 日本語

> この文書は [configuration.md](configuration.md) の翻訳です。英語版と食い違うときは英語版が正です。

`~/.config/netcap/` に `hosts` と `profiles` を置く (`$NETCAP_CONFIG_DIR` か `$XDG_CONFIG_HOME/netcap` でも可)。
1 行 1 件で、`#` から後はコメント。雛形は [examples/](../examples/)。

## hosts

```text
# 名前    OS   経路
laptop   mac  -
server   mac  server
gamepc   win  gamepc
```

| 列 | 値 |
| --- | --- |
| 名前 | `netcap status <名前>` で指す名前。英数字と `_` `.` `-` で、英数字で始める。`all` は使えない |
| OS | `mac` (pf + dummynet)、`linux` (tc)、`win` (NetQosPolicy) のどれか |
| 経路 | ふだんの ssh の宛先。`~/.ssh/config` の Host か `user@host`。netcap を叩くこの機械自身なら `-`。`netcap install` がこの行を書く |

## profiles

```text
# 名前   端末=値 …
game    laptop=2/2  server=1/1  gamepc=off
quiet   laptop=1/1  server=1/1
none    laptop=off  server=off  gamepc=off
```

値は Mbit/s の `上り/下り`、`on` (その端末自身の既定値。フラグなしの `netcap on <名前>` と同じ)、`off` のどれか。小数も使える (`0.5/2`)。`0` はエラーで、netcap は受け付けず何も変えない (macOS の dummynet は 0 を無制限と読むので、「遮断」の意味にはできない)。上限を外すなら `off`。書かなかった端末は触らない (`quiet` は `gamepc` をそのままにする)。プロファイルの名前も端末の名前と同じ決まりに従う。

## 書き出しと取り込み

`netcap export` はこの機械の hosts と profiles を JSON で出し、`netcap import` がそれを読み戻す。
バックアップや、管理する側を増やすとき ([operations.ja.md](operations.ja.md#管理する側が複数)) に使う。

```bash
netcap export > netcap.json
netcap import netcap.json            # 同じ機械でも別の機械でも。- なら標準入力
netcap import netcap.json --replace  # 今ある hosts と profiles を上書きする (hosts.bak と profiles.bak に残す)
```

- **秘密は書き出さない。** 鍵 (`~/.ssh/netcap` は置いたまま) も ssh の設定も入らない。経路は Host 名のままで、
  取り込んだ機械の `~/.ssh/config` が解決する。上限や既定値も入らない。それらは端末の側にある
- **この機械 (経路 `-`) は別の機械に引き継がない。** 別の機械で取り込むとその機械自身を指してしまうので、
  取り込まずに (profiles からも外して) そう伝える。戻すなら `netcap install <名前> --ssh <宛先>`
- **書き込む前に全部を検査する。** 名前、OS、経路、プロファイルの値。書き出した機械の名前は、名前の規則に合うときだけ書く。`-` で始まる経路は、ssh がオプションとして読む
  (`-oProxyCommand=…` はコマンドを実行する) ので受け付けない。hosts と profiles を読むときも同じ検査をし、
  決まりに合わない行はファイル名と行番号を添えて知らせる
- hosts と profiles のコメントは引き継がない
- 新しい管理する側では、端末ごとに `netcap install <名前>` を流して、その機械自身の鍵を登録する
