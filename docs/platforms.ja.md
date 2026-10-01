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
| ICMP (ping) は素通し | ✅ | ✅ | ✅ (実測。IPv4) |
| IPv6 (LAN・ICMPv6・DNS は素通し) | ✅ (ルールから) | ✅ (実測) | ⚠️ LAN と DNS は素通し (ルールから)。ICMPv6 は ❓ |
| 関門 | forced command + 動詞ごとの sudoers | forced command + 動詞ごとの sudoers | forced command のみ |
| この機械に `netcap install` | ✅ (sudo) | ✅ (sudo) | ✅ (管理者として) |
| 管理する側から `netcap install --ssh` | ✅ | ✅ | ✅ (ssh のユーザーが管理者であること) |

素通しにする範囲は [design.ja.md](design.ja.md#素通しにする宛先) にある。IPv6 の行は、Linux は CI で実測し、
macOS と Windows はルールを読んだ結果で、実測ではない。

## 管理する側 (CLI) として

| 機能 | macOS | Linux | Windows |
| --- | --- | --- | --- |
| `status` `get` `on` `off` `set` `check` `use` `profiles` | ✅ | ✅ | ✅ |
| この機械の `install` / `uninstall` / `rename` | ✅ | ✅ | ✅ |
| `--ssh` で他の端末へ `install` / `uninstall` | ✅ | ✅ | ✅ |
| `export` / `import` | ✅ | ✅ | ✅ |
| brew で入れる | ✅ | ✅ (Homebrew on Linux) | ❌ (curl か zip。[host-setup.ja.md](host-setup.ja.md#スクリプトの在り処) を参照) |
| 日本語ロケールでヘルプとエラーが日本語 | ✅ | ✅ | ⚠️ `LANG` か `LC_ALL` を設定しない限り英語 |

CLI に要るのは Python 3 と OpenSSH のクライアントだけ。

Linux から Linux、Windows から Windows への `--ssh` は、CI で試している。ランナーが本物の sshd を通して自分自身に入る
(`tests/test_e2e_ssh.py`)。Windows では sshd の既定のシェル (`cmd.exe`) と PowerShell の 2 通りで流す。
