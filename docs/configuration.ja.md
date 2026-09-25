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
| 名前 | `netcap status <名前>` で指す名前。`all` は使えない |
| OS | `mac` (pf + dummynet)、`linux` (tc)、`win` (NetQosPolicy) のどれか |
| 経路 | ふだんの ssh の宛先 (`~/.ssh/config` の Host)。netcap を叩くこの機械自身なら `-`。`netcap install` がこの行を書く |

## profiles

```text
# 名前   端末=値 …
game    laptop=2/2  server=1/1  gamepc=off
quiet   laptop=1/1  server=1/1
none    laptop=off  server=off  gamepc=off
```

値は `上り/下り` (Mbit/s の正の数。macOS の dummynet は 0 を無制限と読むので、0 は受け付けない) か `off`。書かなかった端末は触らない (`quiet` は `gamepc` をそのままにする)。
