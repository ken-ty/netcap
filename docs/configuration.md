# 設定ファイル

`~/.config/netcap/` に `hosts` と `profiles` を置く (`$NETCAP_CONFIG_DIR` か `$XDG_CONFIG_HOME/netcap` でも可)。
1 行 1 件で、`#` から後はコメント。雛形は [examples/](../examples/)。

## hosts

```text
# 名前    OS   経路
laptop   mac  -
server   mac  server-netcap
gamepc   win  gamepc
```

| 列 | 値 |
| --- | --- |
| 名前 | `netcap status <名前>` で指す名前。`all` は使えない |
| OS | `mac` (pf + dummynet) か `win` (NetQosPolicy) |
| 経路 | `~/.ssh/config` の Host 名。netcap を叩くこの機械自身なら `-` |

## profiles

```text
# 名前   端末=値 …
game    laptop=2/2  server=1/1  gamepc=off
quiet   laptop=1/1  server=1/1
none    laptop=off  server=off  gamepc=off
```

値は `上り/下り` (Mbit/s) か `off`。書かなかった端末は触らない (`quiet` は `gamepc` をそのままにする)。
