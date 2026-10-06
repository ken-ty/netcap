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
| `on --for` (端末が自分で上限を外す) | ✅ | ✅ (systemd が要る) | ✅ |
| LAN と VPN (IPv4 のプライベート、100.64/10) は素通し | ✅ | ✅ | ✅ |
| DNS は素通し | ✅ | ✅ | ✅ |
| ICMP (ping) は素通し | ✅ | ✅ | ✅ (実測。IPv4) |
| IPv6 (LAN・ICMPv6・DNS は素通し) | ✅ (実測) | ✅ (実測) | ✅ (実測。IPv4 と同じく上りだけ) |
| 関門 | forced command + 動詞ごとの sudoers | forced command + 動詞ごとの sudoers | forced command のみ |
| この機械に `netcap install` | ✅ (sudo) | ✅ (sudo) | ✅ (管理者として) |
| 管理する側から `netcap install --ssh` | ✅ | ✅ | ✅ (ssh のユーザーが管理者であること) |

素通しにする範囲は [design.ja.md](design.ja.md#素通しにする宛先) にある。IPv6 の行は、Linux は CI で実測している。
macOS と Windows は、LAN 宛ての IPv6 を 2026-10-01 に実機で測った。リンクローカルで 2 MB を送ると、0.10.0 のルールでは
8.1 秒 (macOS、2 Mbit/s) と 17.1 秒 (Windows、1 Mbit/s)、今のルールでは 0.14 秒だった。
macOS は、インターネット宛ての IPv6 も 2026-10-04 にスマートフォンのテザリングで測った。上限 1/1 Mbit/s で、IPv6 の
下りは 28.7 から 0.89 Mbit/s に落ち、上りは 0.62 Mbit/s に収まった。その下りで上限を埋めている間、IPv6 の新しい TCP
接続は 0.8〜1.8 秒待たされたが、ping6 は 31 ms、IPv6 経由の DNS は 26〜52 ms で、上限なしのときと変わらなかった。
Windows は 2026-10-06 に同じテザリングで測った。上限 1/1 で、IPv6 の上りは 11.3 から 0.92 Mbit/s に落ちた。その上りで
上限を埋めている間、IPv6 の新しい TCP 接続は 1.0〜1.3 秒かかったが、ping6 は 18〜61 ms、IPv6 経由の DNS は 30〜38 ms で、
上限なしのときと変わらなかった。ICMPv6 を名指しするものは無いが、絞るポリシーはそれを遅らせない。

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
Windows 11 の管理する側から macOS 26.3 の端末へも、同じテストを手で流し、install、forced command、`doctor`、`on` / `off`、uninstall が動くことを確かめた (2026-10-01)。0.10.0 より後の版が要る。
Windows の git clone からでも端末側を LF で送るようにした (#65)。macOS から Windows へは日々使っている。
