# 設定ファイル

どの端末を管理するか (`hosts`) と、まとめて動かす組 (`profiles`) は `~/.config/netcap/` に置く。
`$NETCAP_CONFIG_DIR` があればそこを、無ければ `$XDG_CONFIG_HOME/netcap` を読む。

コードの中 (brew なら Cellar) に置かないのは、編集できず、`brew upgrade` のたびに消えるため。

どちらも 1 行 1 件のテキストで、`#` から後はコメント。雛形は [examples/](../examples/) にある。

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

- 値は `上り/下り` (Mbit/s) か `off`
- `netcap use <名前>` で揃える。**書かなかった端末は触らない** (上の `quiet` は `gamepc` をそのままにする)
- `netcap profiles` の表示はこのファイルと同じ形
