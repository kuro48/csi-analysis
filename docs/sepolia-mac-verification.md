# Mac上のSepolia検証環境を別PCから利用する

2026-11-24時点。WebUI・APIはMacに置き、証明の記録・検証先をEthereum Sepolia（chain ID `11155111`）に固定する構成。

現在の公開URL：<https://approaches-beside-trading-travelers.trycloudflare.com>

**画面は公開済みだが、Sepoliaへのデプロイ・証明記録は未実施。** 2026-11-24 18:06 JSTの確認では、デプロイ用・記録用ウォレットの残高がともに0 test ETHだった。患者一覧が空なのはこのため。画面表示の確認と、実際のオンチェーン検証の完了は区別する。

## 別PCでの操作

1. ブラウザで公開URLを開く。同じLANへの接続や、閲覧側のウォレットは不要。
2. 記録完了後、患者の表示用IDを選ぶ。
3. 計測開始時刻を選ぶ。最初の確認には保存済み実CSIの証明を使うため、今日の計測ではない。日付フィルターは空欄のままでよい。
4. 「証明を検証して結果を取得」を押す。
5. 成功すると呼吸判定結果、Sepoliaの検証ブロック番号、記録トランザクションへのリンクが表示される。

APIがSepolia上のコントラクトの `verifyObservation` を `eth_call` で実行してから結果を返す。検証自体はトランザクションを送らないため、閲覧者はガス代を支払わない。記録には記録用ウォレットからテストETHを使う。

公開チェーン上の値は直接読むこともできる。「検証後だけ結果を表示」はAPI・画面の動作であり、オンチェーン値の秘密性を保証するものではない。

## ユーザー側で必要な作業

次の**両方**へSepoliaのテストETHを補充する。秘密鍵を共有する必要はない。

| 用途 | アドレス |
| --- | --- |
| コントラクトのデプロイ | `0xec77D2B256e1c9079CbA30869ca74bBFBb28C32f` |
| 証明の記録 | `0xbe0EEc5d93231938Cf743a792516fbb103B48651` |

Faucetの案内は[Ethereum公式のSepoliaページ](https://ethereum.org/developers/docs/networks/#sepolia)を参照。MainnetのETHではなくSepolia用を利用する。必要な実費は実行時のガス見積もりに依存する。

補充後、こちらでデプロイ→保存済み実CSI証明の記録→公開画面での検証を実行できる。現時点でこれらが成功したとは報告していない。

## Macでの運用手順

コマンドはリポジトリルートから実行する。既存のローカル検証環境とは、ポート・キュー・デプロイ先を分離している。

```bash
# 資金・接続先を確認（未入金は終了コード2）
bash scripts/sepolia-mac.sh check

# コントラクトのコンパイルと保存済み実CSI証明のオフライン検証
bash scripts/sepolia-mac.sh prepare

# 入金後、Sepoliaへデプロイ（2 confirmation待ち）
bash scripts/sepolia-mac.sh deploy

# 最初の実証明を専用キューへ登録。workerを起動する前に行う
bash scripts/sepolia-mac.sh seed
```

API・workerはそれぞれ別のターミナルで継続起動する。APIは現在起動済み、workerはデプロイ・seed完了後に起動する。

```bash
bash scripts/sepolia-mac.sh api
```

```bash
bash scripts/sepolia-mac.sh worker
```

記録・確認待ちが終わったら実行する。

```bash
bash scripts/sepolia-mac.sh verify
```

結果は `.local/sepolia-mac/smoke-result.json` に保存される。記録トランザクションのgas・実費、検証読出し時間を含む。最初の確認は既存の実CSIから作成済みの証明を再利用するため、新たなCSI取得時間や証明生成時間は測定しない。合成CSIは使用していない。

デプロイ先に `manifest.json` または `deployment-journal.json` がある場合、重複デプロイを避けるため再実行を停止する。途中で失敗した場合はjournalのトランザクションを確認して復旧する。journalを削除して盲目的に再実行しない。

## 公開画面の構成と再起動

| 機能 | ローカル待受 | 状態 |
| --- | --- | --- |
| Sepolia用API | `127.0.0.1:8014` | 起動済み |
| 本番ビルドの閲覧UI | `127.0.0.1:3014` | 起動済み |
| 閲覧機能だけのnginx | `127.0.0.1:8084` | 起動済み |
| Cloudflare Quick Tunnel | HTTPS公開URL | 起動済み |

UIは `.local/sepolia-mac/ui` の独立したworktreeでビルド済み。以下は停止後の再起動用であり、起動中に重ねて実行しない。

```bash
cd .local/sepolia-mac/ui/frontend
HOSTNAME=127.0.0.1 PORT=3014 node .next/standalone/server.js
```

以下はリポジトリルートから実行する。

```bash
docker compose -f deploy/staging/compose.sepolia-viewer.yml up -d
cloudflared tunnel --config .local/sepolia-mac/tunnel.yml --url http://127.0.0.1:8084 --no-autoupdate
```

`tunnel.yml` の内容は `url: http://127.0.0.1:8084`。別用途のcloudflared設定を誤って読み込まないため、明示的に指定している。

Quick Tunnelは一時公開用で、Mac・API・UI・Docker・cloudflaredの稼働が必要。Macのスリープや終了で利用できなくなり、トンネルを再起動するとURLが変わる。固定ドメインでの常時公開は別途設定する。[Cloudflare公式説明](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)

公開プロキシでは患者一覧・計測一覧・証明検証だけを許可し、CSI送信、患者作成、管理画面、API仕様画面を遮断する。API・workerの鍵、operator token、SQLiteキューは `.local` に保持し、公開・コミットしない。

今回のsetupは既存のtestnet用鍵とデバッグ設定を使う。証明検証成功は臨床精度の実証ではなく、患者ID・絶対計測時刻の正しさは記録者の入力に依存する。2 confirmation待ちはEthereumのfinalized確定とは異なる。

## 変更と確認の記録

- [進捗・スクリーンショット](progress/2026-11-24-sepolia-mac/README.md)
- 実装：`scripts/sepolia-mac.sh`、`scripts/sepolia_smoke.py`
- 公開範囲：`nginx/sepolia-viewer.conf`、`deploy/staging/compose.sepolia-viewer.yml`
- UI：`frontend/app/patients/PatientResults.tsx`
- 実証明の回帰テスト：`backend/contracts/test/sepolia-real-proof.test.mjs`
