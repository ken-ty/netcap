# 開発

## リポジトリの形

| パス | 中身 |
| --- | --- |
| `bin/netcap` | CLI (Python 3、標準ライブラリだけ) |
| `mac/` | macOS の端末側 (pf + dummynet)。agent と netcap-check は Linux も使う |
| `linux/` | Linux の端末側 (tc) |
| `win/` | Windows の端末側 (NetQosPolicy) |
| `examples/` | `hosts` と `profiles` の雛形 |
| `Formula/netcap.rb` | Homebrew の formula (このリポジトリ自体が tap) |
| `scripts/measure.sh` | 上限の効き目を測る |
| `tests/` | README と docs の仕様をなぞるテスト |
| `.github/workflows/ci.yml` | CI。E2E は macOS / Linux / Windows の matrix |

## テスト

```bash
python3 -m unittest discover tests           # CLI (偽の ssh) と、docs と実装の突き合わせ
NETCAP_E2E=1 python3 -m unittest tests/test_e2e.py   # 実機。この機械に端末側を入れて上限をかけ、最後に外す
```

E2E はこの機械の設定を書き換え、sudo (Windows は管理者) が要る。ふだんは CI に任せる。
docs に書いた振る舞いを変えるときは、先にテストを直して落ちることを確かめてから実装する。

`README.md` (英語) と `README.ja.md` (日本語) は同じ PR で揃える。docs/ は日本語だけ。

## リリース

1. main に `vX.Y.Z` の注釈付きタグを打って push する
2. `Formula/netcap.rb` の `tag` と `revision` をそのタグに合わせる
3. [docs/host-setup.md](docs/host-setup.md) の curl と zip の例にある版を合わせる

版の正本はタグ。formula が `bin/netcap` の `@VERSION@` を埋め、clone では `git describe` を使う。
