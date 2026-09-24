# 開発

## リポジトリの形

| パス | 中身 |
| --- | --- |
| `bin/netcap` | CLI (Python 3、標準ライブラリだけ) |
| `mac/` | macOS の端末側 (pf + dummynet) |
| `win/` | Windows の端末側 (NetQosPolicy) |
| `examples/` | `hosts` と `profiles` の雛形 |
| `Formula/netcap.rb` | Homebrew の formula (このリポジトリ自体が tap) |
| `scripts/measure.sh` | 上限の効き目を測る |

リポジトリから直接動かすときは `bin/netcap` をそのまま叩けばよい。

README は英語の [README.md](README.md) と日本語の [README.ja.md](README.ja.md) の 2 つ。片方を
変えたら、もう片方も同じ PR で揃える。docs/ は日本語だけ。

## リリース

1. main に `vX.Y.Z` の注釈付きタグを打って push する
2. `Formula/netcap.rb` の `tag` と `revision` をそのタグに合わせる
3. [docs/host-setup.md](docs/host-setup.md) の curl と zip の例にある版を合わせる

版の正本はタグ。formula がインストール時に `bin/netcap` の `@VERSION@` を置き換える。
リポジトリから直接動かしたときは `git describe` の結果を、どちらでもないときは `unknown` を出す。
