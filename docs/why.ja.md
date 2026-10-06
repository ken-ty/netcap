# netcap を選ぶ理由

[English](why.md) · 日本語

> この文書は [why.md](why.md) の翻訳です。英語版と食い違うときは英語版が正です。

netcap は、数台のコンピュータのためのホストベースの QoS で、そのうち 1 台から ssh で操作する。
ルーターが役に立たないときに合う道具で、隣り合ういくつかの用途には向かない。このページは選ぶためにある。

## netcap を選ぶとき

- **ルーターに使える QoS が無い**、またはルーターを変えられない (プロバイダー支給、共用・賃貸の回線)
- **絞りたいのがコンピュータ** (macOS、Linux、Windows) で、ssh で入れる
- **端末ごとまるごと、1 か所から絞りたい**。複数台をまとめて切り替えることが多い (「ゲームモード」: ノートとサーバーを絞り、ゲーム用の PC はそのまま)
- **LAN の通信は速いままにしたい**。絞るのはインターネット宛てだけで、LAN・VPN (100.64/10)・ping・DNS は素通し

## 他を選ぶとき

| 状況 | 向いているもの | 理由 |
| --- | --- | --- |
| OpenWrt (または QoS の良いルーター) を使える | ルーターの SQM (cake / fq_codel) | スマホやゲーム機も含めて全端末に効き、回線全体の bufferbloat を解消する。できるならこちらを先に |
| スマホ・ゲーム機・テレビ・IoT を絞りたい | ルーターの QoS | netcap は端末に agent が要り、これらには入れられない |
| Active Directory ドメインの Windows | グループ ポリシーの Policy-based QoS | OS 標準で、ドメイン コントローラーから管理でき、アプリ・ユーザー・アドレス単位で設定できる |
| Windows 1 台をアプリ単位で | NetLimiter | アプリ・接続単位の制限を GUI で (有料) |
| Linux 1 台のインターフェース 1 つ | wondershaper、または `tc` を直接 | スクリプト 1 つかコマンド 1 つで済み、ssh も agent も要らない |
| Unix 系で 1 つのプログラムだけ | trickle | ユーザー空間でプロセスごとに絞る (協調型: ライブラリの差し込みに頼る) |
| 遅い・不安定な回線でアプリを試す | Network Link Conditioner (macOS / iOS)、ブラウザの開発者ツールの throttling | 模擬のための道具で、帯域だけでなく遅延やパケットロスも作れる |

## 並べて比べる

✅ できる · ❌ できない · ❓ 未確認 · n/a 当てはまらない

| | netcap | ルーターの SQM (OpenWrt) | Windows Policy-based QoS | NetLimiter | wondershaper | trickle | Network Link Conditioner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 動く場所 | 各コンピュータ。1 台から操作 | ルーター | 各 Windows PC。ドメイン コントローラーから設定 | Windows 1 台 | Linux 1 台 | 1 プロセス | Mac 1 台 |
| 対象 | 入れたコンピュータ | ルーターの内側すべて | ドメイン参加の Windows | その PC | その機械 | そのプロセス | その Mac |
| OS | macOS、Linux、Windows | ルーターのファームウェア | Windows | Windows | Linux | Unix 系 | macOS |
| 制御するもの | 端末ごとの上り / 下りの上限 | WAN のシェーピングと AQM、フロー間の公平 | 送信の throttle と DSCP の付与 | アプリ / 接続単位の制限 | インターフェース単位の上り / 下り | プロセス単位の速度 | 帯域・遅延・ロス |
| 下りの上限 | ✅ (Windows は上りのみ) | ✅ | ❌ 送信のみ | ✅ | ✅ | ✅ | ✅ |
| LAN は絞らない | ✅ | ✅ (WAN だけを制御) | アドレスで設定できる | ❓ | ❌ インターフェース全体 | n/a | ❌ 端末全体 |
| 複数台をまとめて | ✅ profiles | ✅ (ルーター 1 台で) | ✅ グループ ポリシー | ❌ | ❌ | ❌ | ❌ |
| 必要なもの | ssh + Python 3 | OpenWrt のルーター | Active Directory | ライセンス | root | なし | Xcode の Additional Tools |

## netcap の立ち位置

一番近いのは Windows の Policy-based QoS。上限を各コンピュータでかけ、1 か所から設定する。
netcap はこれを、ドメイン無しで、macOS・Linux・Windows にまたがって、ssh だけを経路にしてやる。
管理する側が何をしてよいかは、各端末が決める (鍵ごとの forced command)。

ルーターの QoS と比べると、netcap は反対の端から攻める。通信に優先度を付けたり、回線のキューを管理したりはしない。
選んだコンピュータから帯域を取り上げて、残りを他の端末のために空けておく。

## netcap がしないこと

全部の一覧と、netcap がどうなるべきかは [vision.ja.md](vision.ja.md) にある。

- 通信の優先度付け、回線の bufferbloat の解消 (ルーターの SQM を使う)
- スマホ・ゲーム機・テレビなど、agent を入れられないものを絞る
- Windows の下りを絞る
- アプリ単位で絞る
- 繰り返しのスケジュールを自前で持つ (cron・launchd・タスクスケジューラから `netcap use` を呼ぶ)。自分で持つのは `on --for` の期限で外すことだけ

パケットキャプチャを探しているなら、それは同じ名前の別プロジェクト [dreadl0ck/netcap](https://github.com/dreadl0ck/netcap)。

## 参考

- [OpenWrt: SQM (Smart Queue Management)](https://openwrt.org/docs/guide-user/network/traffic-shaping/sqm)
- [Microsoft Learn: Quality of Service (QoS) Policy](https://learn.microsoft.com/en-us/windows-server/networking/technologies/qos/qos-policy-top)
- [NetLimiter](https://www.netlimiter.com/)
- [magnific0/wondershaper](https://github.com/magnific0/wondershaper)
- [tc(8)](https://man7.org/linux/man-pages/man8/tc.8.html)
- [mariusae/trickle](https://github.com/mariusae/trickle)
- [NSHipster: Network Link Conditioner](https://nshipster.com/network-link-conditioner/)
