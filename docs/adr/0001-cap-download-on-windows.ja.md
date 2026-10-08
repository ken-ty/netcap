# ADR 0001: Windows の下りを WinDivert で絞る

[English](0001-cap-download-on-windows.md) · 日本語

> この文書は [0001-cap-download-on-windows.md](0001-cap-download-on-windows.md) の翻訳です。英語版と食い違うときは英語版が正です。

- 状態: Accepted
- 日付: 2026-10-09
- 決めた人: Ken ([#108](https://github.com/ken-ty/netcap/issues/108) で)

## 背景

[vision.ja.md](../vision.ja.md) は 3 つの OS すべてで上りと下りを絞ると約束している。Windows は上りしか絞れなかった。
NetQosPolicy が絞るのはその機械が送る通信で、機械全体の下りを絞る仕組みは Windows に組み込まれていない
(Windows 11 25H2 まで確認)。この差は「Windows の下りにはドライバが要り、netcap の規模を超える」として受け入れていた。
#108 でそれを見直した。

## 選択肢

下りをどこで止めるか:

| | どこで | Windows 側 | 下りを絞れるか |
| --- | --- | --- | --- |
| 1 | Windows の中: カーネルドライバが受信パケットを待たせる | 署名済みのドライバと、絞っている間だけ動くプロセス | はい |
| 2 | Windows の外: LAN の別の機器を出口にして、そこで絞る (Tailscale の exit node、または NAT するデフォルトゲートウェイ) | 経路か `tailscale set --exit-node`。何も入れない | はい |
| 3 | 組み込みとアプリ: TCP 受信ウィンドウ、リンク速度、アプリごとの制限 (Steam、OneDrive、BITS) | 設定だけ | いいえ。接続ごと・アプリごとで、上限にならない |

**選択肢 1 にした。** 選択肢 2 は「各機器で強制する」を崩し、出口の機器が止まると効かなくなる。選択肢 3 は上限ではなく、
1 か 2 と組み合わせたときの補助にしかならない。

自前のドライバ (WFP callout や NDIS フィルタ) を書くと、EV 署名とカーネルの保守を抱える。これは引き続き範囲外とし、
ドライバは借りる:

| | WinDivert | Windows Packet Filter (ndisapi) |
| --- | --- | --- |
| ドライバ | WFP ベース | NDIS lightweight filter |
| ライセンス | LGPL v3 か GPL v2 | ライブラリは MIT。ドライバは個人・教育・非営利なら無料、製品に入れて配るなら $3,000 |
| 保守 | 最後のリリースは 2.2.2 (2022-09-21) | 2025 年にもコミットがある |
| ARM64 | 署名済みのビルドが無い | ある |
| 使っているもの | mitmproxy (pydivert 経由)、GoodbyeDPI、zapret、Suricata、clumsy | オープンソースではわずか |

**WinDivert にした。理由は採用の広さ。** 上のどのプロジェクトも netcap よりずっと利用者が多い。その利用者が WinDivert に
修正や後継を求める圧力をかけており、netcap はほとんど誰も使わないドライバではなく、その圧力に乗る。
Windows Packet Filter のほうが保守はされているが、その圧力が無い。

## 決めたこと

- **必要になったときに、確認してから入れる** (2026-10-09、最初の CI のあとに決めた): 答えなしに WinDivert を入れるものは無い。
  端末から打った `netcap on` は、まだ決めていない Windows の機器について、入れる前に聞く:
  「<host> の下りを絞るには WinDivert (サードパーティのカーネルドライバ、LGPL) が要る。今入れる? [y/N]」。`--yes` と
  `netcap install <name> --with-download` は聞かずに入れる。端末が無いとき、`--json` や `-q` のとき、多くの機器に触る
  `use` と `protect` では何も聞かず、これまでどおり上りだけ絞って機器の名前を出す。ARM64 の Windows は断る
- **前もって断る**: `netcap install <name> --without-download` は WinDivert を外し、断ったことを機器に記録する
  (`download.declined`)。どの管理する側からも同じ答えが見え、`on` は聞かなくなる。`--with-download` で消える。
  `netcap get` に選択が出る。どちらのフラグも付けない install は選択を変えない
- **配らずに取ってくる**: インストーラが公式の 2.2.2 リリースを HTTPS で取ってきて、SHA-256 が固定した値と一致しなければ
  断る。中から x64 の `WinDivert.dll`、`WinDivert64.sys`、`LICENSE` だけを `C:\ProgramData\netcap\windivert` に置き、
  netcap のほかのファイルと同じ ACL をかける。netcap のリポジトリと formula に WinDivert のバイナリは入っていない
- **shaper はスクリプト**: `netshape-down.ps1` が WinDivert.dll を呼ぶ小さな C# のクラスを `Add-Type` でコンパイルする。
  上りと同じ除外 (LAN、VPN、ループバック、リンクローカル、マルチキャスト。DNS。ICMP と ICMPv6) を除いた受信パケットを
  受け取り、トークンバケットで上限の速さに合わせて送り出し、待ちが 50 パケットを超えた分は落とす (macOS の下りの pipe
  と同じ)。SYSTEM としてスケジュールタスク `\netcap\download` から動き、`on` と、上限がかかっている間の起動時に始まり、
  `off` と `on --for` の期限で終わる。速さの変更は shaper が読むファイル経由で、ハンドルは開いたまま
- **WinDivert の既知の不具合を避ける**: shaper はサービスが起動中・停止中なら待ち、オープンを間隔を広げながらやり直す。
  読み込み途中のドライバと競争しない ([basil00/WinDivert#408](https://github.com/basil00/WinDivert/issues/408))
- **ドライバは既定では再起動まで読み込んだまま**: `off` がするのは netcap のハンドルを閉じることだけ。WinDivert は最後の
  ハンドルが閉じてもドライバを外さず、netcap もサービスを止めない。ハンドルが 1 つでも開いている間に止めると以後の
  オープンが 1058 で失敗し ([basil00/WinDivert#406](https://github.com/basil00/WinDivert/issues/406))、netcap には
  ハンドルを持ちうるプログラムをすべては見えないため。ハンドルの無いドライバは何も待たせない。`off` でドライバが
  読み込まれたまま上限が外れること (2026-10-09 の実行で、上限なし 842 Mbit/s、1 Mbit/s の上限で 0.95、`off` のあと 826。サービスは動いたまま)、`on` / `off` を 20 回繰り返して毎回絞り、毎回 shaper が終わること
  (20 回で 206 秒。最後の `on` のあと 0.95 Mbit/s、最後の `off` のあと 849) を CI で測っている
- **低レベルのコマンドとしての `unload-driver`**: `netcap unload-driver <host>` は求めに応じてサービスを止める。git が
  plumbing をそうするように、`netcap help --all` にだけ載る。下りの上限がかかっている間と、WinDivert.dll を読み込んだ
  プロセスがある間は、機器が断る。既定にしないのは、DLL を使わずにドライバと話すプログラムはこの確認で見えず、
  見落とすと #406 でドライバが再起動まで使えなくなるため

## ライセンス

netcap は WinDivert をインストール時に取ってくるだけで、配布しない。利用者は上流から LGPL v3 (か GPL v2。利用者が選ぶ)
で受け取り、ライセンスファイルもその隣に置かれる。netcap は改変していない DLL を実行時に呼ぶだけで、MIT のまま。

## 結果

この選択とともに受け入れたもの (CVE が付いたものは無い):

- [LOLDrivers](https://www.loldrivers.io/) は WinDivert 2.2 を悪性として載せている (2024-09)。攻撃者がセキュリティ製品を
  黙らせるために持ち込むため。Malwarebytes は検出し、Bitdefender は隔離したことがある
  ([basil00/WinDivert#395](https://github.com/basil00/WinDivert/issues/395))
- 署名の証明書は 2023 年に切れている。署名にタイムスタンプがあるので Windows はまだ読み込む (GitHub の Windows Server
  2022 と 2025 のランナーは読み込んだ) が、ブロックするセキュリティソフトもある
  ([basil00/WinDivert#397](https://github.com/basil00/WinDivert/issues/397)、
  [basil00/WinDivert#401](https://github.com/basil00/WinDivert/issues/401))
- 未修正のクラッシュ: ドライバの読み込み途中でデバイスを開くと 0xD1 のバグチェックになる
  ([basil00/WinDivert#408](https://github.com/basil00/WinDivert/issues/408)。
  [basil00/WinDivert#330](https://github.com/basil00/WinDivert/issues/330) の原因)。BIOS の更新後にバグチェックが頻発した
  という報告もある ([basil00/WinDivert#398](https://github.com/basil00/WinDivert/issues/398))
- ARM64 のビルドが無い。コンパイルはできるが、署名できる人がいない
  ([basil00/WinDivert#236](https://github.com/basil00/WinDivert/issues/236)、
  [basil00/WinDivert#379](https://github.com/basil00/WinDivert/issues/379))
- 最後のリリースは 2022 年。作者は活動中で、機能は完成していると言っている
  ([basil00/WinDivert#395](https://github.com/basil00/WinDivert/issues/395))
- `off` のあともドライバは次の再起動まで読み込まれたまま。WinDivert は最後のハンドルが閉じてもドライバを外さず、netcap は
  そのサービスを止めない。GitHub のランナーでは、`off` のあともアンインストールのあとも、サービスは削除予定のまま動いていた。
  それまで `.sys` は消せないので、アンインストールはその 1 ファイルを次の起動時のタスクに任せる。下りの上限を一度も
  かけない機器は読み込まない。アンチチート (Vanguard、Easy Anti-Cheat、BattlEye) が嫌がるかはまだ確かめていない
- オプトインした機器は、絞っている間サードパーティのカーネルドライバを動かし、セキュリティソフトが報告することがある。
  [SECURITY.ja.md](../../SECURITY.ja.md) にそう書いた

## 見直すとき

- 上のプロジェクトが移る後継 (フォーク、またはコミュニティが移る新しいドライバ) が出たら、netcap もそれに移る
- Windows の更新で WinDivert が読み込めなくなったら
- アンチチートやセキュリティソフトのせいで、オプトインが実際には使えないとわかったら
