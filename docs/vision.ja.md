# ビジョン

[English](vision.md) · 日本語

> この文書は [vision.md](vision.md) の翻訳です。英語版と食い違うときは英語版が正です。

netcap が何のためにあり、どうなるべきで、何をしないか。変更はこのページに近づくものにする。
[やらないこと](#やらないこと) に当たる提案は受けない。他のツールとの比較は [why.ja.md](why.ja.md)。

## 解決すること

**QoS 対応ルーターが無い回線で、守りたい通信 (ゲーム・通話・配信・回線監視) を速く保つ。そのために、他のコンピュータの帯域を
1 か所から安全に絞り、必ず戻せるようにする。**

netcap は、ドメインの要らない Windows Policy-based QoS にあたる。各コンピュータの側で上限をかけ、macOS・Linux・Windows に
またがり、経路は ssh だけ。ルーターの SQM の代わりではない。SQM を入れられるなら、そちらが先。

## 原則

- **上限は各端末がかけ、許可も各端末が決める。** 管理する側は頼むだけで、何を頼んでよいかは端末の `authorized_keys` が決める
- **絞るのはインターネット宛てだけ。** LAN・VPN・ping・DNS は素通しにして、回線を使える状態に保ち、測定を歪めない
- **どの上限も戻せる。** 絞られた機械自身から、回線が無くても戻せる
- **1 つの作業に 1 つのコマンド。** 端末の導入、絞る、戻す、がそれぞれ 1 コマンド
- **小さく。** CLI は標準ライブラリだけの Python 1 ファイル。端末側はスクリプトで、コマンドの間は netcap のものは何も動いていない。
  例外は、`boot=on` の起動時と `on --for` の期限に OS が本体を動かすことと、WinDivert のある Windows の端末で
  上限がかかっている間に下りの shaper が動くことだけ
- **OS がやることは OS に任せる。** 繰り返しのスケジュールは cron・launchd・タスクスケジューラから netcap を呼ぶ。`on --for` の期限は端末の
  スケジューラ (launchd、systemd のタイマー、タスクスケジューラ) が持つ。帯域の制御は pf・tc・NetQosPolicy で、Windows の下りは
  借りたドライバ WinDivert ([ADR 0001](adr/0001-cap-download-on-windows.ja.md))

## あるべき姿と現在

残っている差分は [`vision-gap`](https://github.com/ken-ty/netcap/labels/vision-gap) ラベルで追う。

| 観点 | あるべき姿 | 現在 | 差分 |
| --- | --- | --- | --- |
| インターネット宛てだけ | LAN・VPN・ping・DNS は IPv4 でも IPv6 でも素通し | IPv4 と IPv6 で同じ。Linux・macOS・Windows で実測 | なし |
| 守りたいものを守る | 守る端末を指定すると、他を絞り、効いたかを示す | `netcap protect --load` が他を絞り、前後とも他から回線を埋めて、守る端末の遅延が良くなったかを言う | なし |
| 戻せる | 絞りっぱなしにならない | 手元の `off` は回線不要、`on` の後に戻し方を表示、`boot` の既定は off。`on --for`・`use --for`・`protect --for` は各端末が自分で外す | なし |
| 対応 OS | 3 OS で上りも下りも | Windows は WinDivert で下りも絞る。`on` が入れるか聞く (x64。[ADR 0001](adr/0001-cap-download-on-windows.ja.md))。CI で測った | 未解決: 実機では未計測、アンチチートは未確認、ARM64 は無い ([#108](https://github.com/ken-ty/netcap/issues/108)) |
| 導入 | 端末 1 台に 1 コマンド | `netcap install`。`--ssh` は CI (Linux、Windows) で試し、Windows から macOS へは実測した | なし |
| 管理する側が複数 | どの ssh ユーザーで入っても管理できる | export / import。sudoers はインストールした各ユーザーを許し、uninstall は 1 つの管理する側の分だけ戻す | なし |
| 端末が決める | forced command の後ろにもう一段の関門 | macOS / Linux は動詞ごとの sudoers。Windows は forced command のみ | 受け入れる: Windows には標準の二段目が無い |
| 状態が見える | `status` が実物から読む | 達成。macOS の下りだけ `on` のとき記録した値 | 受け入れる: dnctl が値を出さない |
| スケジュール | 夜だけ絞る、など | cron・launchd・タスクスケジューラから `netcap use` を呼ぶ | なし: OS に任せる |

## やらないこと

| netcap の仕事ではないこと | 代わりに使うもの |
| --- | --- |
| 通信の優先度付け、回線の bufferbloat の解消 | ルーターの SQM (cake / fq_codel) |
| スマホ・ゲーム機・テレビ・IoT | ルーターの QoS |
| アプリ単位の制限 | NetLimiter (Windows) |
| 1 プロセスだけ | trickle |
| 遅延やパケットロスの模擬 | Network Link Conditioner、ブラウザの開発者ツール |
| netcap 独自の Windows ドライバ | 借りる ([ADR 0001](adr/0001-cap-download-on-windows.ja.md)) |

## このページを保つ

- 差分を埋める変更は、同じ PR でこの表を直し、その issue を閉じる
- 新しい差分が見つかったら、`vision-gap` ラベルの issue を立て、ここに行を足す
- 解決すること・原則・やらないことを変えるのは、それ自体が判断。先に issue を立てる
