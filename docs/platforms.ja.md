# 対応状況

[English](platforms.md) · 日本語

> この文書は [platforms.md](platforms.md) の翻訳です。英語版と食い違うときは英語版が正です。

OS ごとに何ができるか。✅ 対応 · ⚠️ 制限あり · ❌ 非対応 · ❓ 未確認

## 操作される側として

| 機能 | macOS | Linux | Windows |
| --- | --- | --- | --- |
| 絞る仕組み | pf + dummynet | tc (HTB。下りは ifb 経由) | NetQosPolicy |
| 上りの上限 | ✅ | ✅ | ✅ |
| 下りの上限 | ✅ | ✅ | ❌ (`unsupported` と出る) |
| `status` が実物から読む | ⚠️ 下りは `on` のとき記録した値で、`*` が付く ([理由](design.ja.md#macos-の-status-の下りに付く-)) | ✅ | ✅ |
| 再起動後 (`boot`) | `off` (既定) か `on` | `off` (既定) か `on` | `keep` のみ。状態が再起動をまたいで残る ([理由](design.ja.md#windows-は再起動しても状態が残る)) |
| `check` (上り下りの測定 + ping) | ✅ | ✅ | ✅ |
| LAN と VPN (IPv4 のプライベート、100.64/10) は素通し | ✅ | ✅ | ✅ |
| DNS は素通し | ✅ | ✅ | ✅ |
| ICMP (ping) は素通し | ✅ | ✅ | ❓ |
| IPv6 | ⚠️ LAN 宛ても絞る。ICMPv6 と DNS は素通し | ⚠️ IPv6 はすべて絞る (LAN、ICMPv6、DNS も) | ⚠️ LAN 宛ても絞る。DNS は素通し |
| 関門 | forced command + 動詞ごとの sudoers | forced command + 動詞ごとの sudoers | forced command のみ |
| この機械に `netcap install` | ✅ (sudo) | ✅ (sudo) | ✅ (管理者として) |
| 管理する側から `netcap install --ssh` | ✅ | ⚠️ 偽の ssh でしか試していない | ✅ (ssh のユーザーが管理者であること) |

素通しにする範囲は [design.ja.md](design.ja.md#素通しにする宛先) にある。macOS と Windows の IPv6 の行は、ルールを読んだ結果
(素通しにする範囲が IPv4 だけ) で、実測ではない。

## 管理する側 (CLI) として

| 機能 | macOS | Linux | Windows |
| --- | --- | --- | --- |
| `status` `get` `on` `off` `set` `check` `use` `profiles` | ✅ | ✅ | ✅ |
| この機械の `install` / `uninstall` / `rename` | ✅ | ✅ | ✅ |
| `--ssh` で他の端末へ `install` / `uninstall` | ✅ | ❓ | ❓ |
| `export` / `import` | ✅ | ✅ | ✅ |
| brew で入れる | ✅ | ❓ (Homebrew on Linux。未確認) | ❌ (curl か zip。[host-setup.ja.md](host-setup.ja.md#スクリプトの在り処) を参照) |
| 日本語ロケールでヘルプとエラーが日本語 | ✅ | ✅ | ⚠️ `LANG` か `LC_ALL` を設定しない限り英語 |

CLI に要るのは Python 3 と OpenSSH のクライアントだけ。
