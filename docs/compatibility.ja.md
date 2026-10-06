# 互換性

[English](compatibility.md) · 日本語

> この文書は [compatibility.md](compatibility.md) の翻訳です。英語版と食い違うときは英語版が正です。

管理する側の CLI と各端末の agent は同じリリースから来るが、更新は別々に起きる。
`netcap install <名前>` が CLI の版を agent に書き込むのは 1 台ずつだからだ。このページは、CLI の各リリースが
どの版の agent と動くかを記録する。

## 決まり

- 1.0 より前は、マイナーリリース (0.x.0) が新しい agent を必要とすることがある。パッチリリース (0.x.y) は必要としない
- 新しい agent が要るリリースは、下の表の下限を上げ、タグのメッセージにもそう書く。
  各端末は `netcap install <名前>` で更新する
- `netcap get` の `agent` 列に各端末の版が出る。CLI と版が違う agent があれば `netcap get` が知らせる

リリースが次のどれかを変えたら、下限を上げる。

- agent が受け付ける操作とその引数、agent が出す `key=value` の行
- 端末の鍵ファイルにある forced command の行 ([host-setup.ja.md](host-setup.ja.md#許可は操作される側が決める)):
  古い CLI が書いた行は、新しい操作を許可していないことがある
- インストーラが端末に置くものと、その場所 ([host-setup.ja.md](host-setup.ja.md#スクリプトの在り処))

## CLI ごとの、動く agent の下限

| CLI | 下限の agent | 備考 |
| --- | --- | --- |
| 0.12.0 | 0.11.0 | 端末側は 0.11.0 から変わっていない |
| 0.11.0 | 0.11.0 | `on --for`、`until=` / `left=`、インストーラが変わった。古い agent も `status` `get` `on` `off` `set` `check` には答えるが、`--for` は何も変えずに拒み、IPv6 と cmd.exe の不具合は残る。`netcap install <名前>` で更新する |
| 0.10.0 | 0.9.0 | 端末側は 0.9.0 から変わっていない。`netcap get` はこれらの agent を CLI と違うと指摘するが、それで正しい |
| 0.9.1 | 0.9.0 | 端末側は 0.9.0 から変わっていない |

0.9.1 より前のリリースは、これを記録していない。agent が 0.9.0 より古い端末は `netcap install <名前>` で更新する。
