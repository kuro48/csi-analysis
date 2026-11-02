# CSI収集から第三者による呼吸判定照会まで

今回の通常フローは、`PicoScenes → 認証付き収集API → 永続キュー → 証明生成ワーカー → 証明記録 → 第三者の照会時にオンチェーン検証 → isNormal表示` です。

第三者画面は `/patients`。公開用ビルドでは `/` もこの画面になります。ログインは設けず、表示用患者IDの一覧と計測開始時刻から選択します。実名・生年月日を登録する項目はありません。患者一覧、計測時刻、公開判定を第三者が読める運用です。

`/capture` は運用者による患者ID登録とデバッグ用アップロードです。既存の `/research`、`/upload`、`/analyze`、`/verify` は残しています。

## 利用者側で必要な作業

| 作業 | 担当環境 | 内容 |
|---|---|---|
| テストネットの準備 | 運用PC | Sepolia RPC、デプロイ用ウォレット、記録用ウォレットにSepolia ETHを用意 |
| 配信環境の準備 | サーバー | Docker、HTTPS、ドメイン、永続ディスクを用意。公開URLの既存502も配信環境側で解消 |
| 患者ID登録 | `/capture` | 運用者トークンを設定し、表示用IDを登録。実患者との対応表はこの公開サービス外で管理 |
| 収集端末の設定 | PicoScenes端末 | 対応NIC、送信機、100 Hzの取得条件、時計同期、患者ID、接続先、トークンファイルを設定 |
| 運用開始 | サーバー・収集端末 | ワーカーと収集クライアントを起動。収集状態と記録用ウォレットの残高を監視 |
| 結果照会 | 第三者ブラウザ | 患者と時刻を選び「証明を検証して結果を取得」 |

秘密鍵や運用者トークンはチャットに貼り付けず、各端末のファイルで設定します。

## ローカルで確認する

依存関係は [既存のセットアップ手順](ONCHAIN_VERIFICATION.md) を参照してください。現在のポート3000/8000/18545に別のスタックがいる場合は、そのスタックを停止してから起動します。

```sh
# 通常モード。短い入力・時刻情報の不備を拒否。
OBSERVATIONS_ENABLED=true bash scripts/start-onchain-local.sh

# 短い既存サンプルのデバッグ時だけこちらを使用。
# 別のコントラクトとしてデプロイし、画面に「デバッグ計測」を表示。
OBSERVATIONS_ENABLED=true OBSERVATION_DEBUG_INPUTS=true bash scripts/start-onchain-local.sh
```

このスクリプトはローカルEVMのみを使い、テスト用記録アカウントへの資金付与、契約デプロイ、API・ワーカー・UIの起動を行います。運用者トークンは `.local/onchain/operator-token`、ワーカーログは `.local/onchain/worker.log` です。

ローカルチェーンは終了時に消えます。再起動ごとに別の患者カタログ・キュー用ディレクトリを作り、以前のデータは削除しません。過去のローカル記録が新しいチェーンでも有効になるわけではありません。

1. `http://127.0.0.1:3000/capture` を開く。
2. 運用者トークンを設定し、「表示用の患者IDを新規登録」。
3. 実機収集なら次節のクライアントを設定。デバッグならファイル・計測開始時刻・期間を指定して投入。
4. 「処理状態を確認」で `recorded` を確認。
5. `http://127.0.0.1:3000/patients` で患者と計測時刻を選んで照会。古い計測は計測日で絞り込めます（一覧は指定範囲の最新2,000件）。

`recorded` は保存状態です。結果は照会のたびに保存済み証明を再検証して取得します。`isNormal=false` は検証失敗ではなく、検証済みの公開判定値が0だったことを示します。

## 通常モードとデバッグモード

既存certificate回路は、100 Hzを前提にしたPython処理から5 Hz・300点の証明入力を作ります。通常モードでは以下を検査します。

- 収集側の指定期間が60秒。
- 少なくとも5 Hzへの間引き後に300点を確保できる5,981サンプル。
- フレーム時刻が単調増加し、平均サンプリング周波数が95〜105 Hz、間隔の変動係数が0.2以下。
- 対象窓が極端に圧縮されていないこと。解析対象は先頭最大6,000サンプル。

これは既存の固定100 Hz処理を使用するための入力検査です。任意のサンプリング条件に対応する再設計ではありません。収集端末で100 Hzのフレーム取得条件を用意してください。

デバッグモードだけは既存処理による不足分のゼロ埋めを許可します。`debugMode` は契約のデプロイ時に固定し、APIは実契約の値とmanifestを照合します。通常とデバッグを後から設定だけで入れ替えません。UIに必ず区別を表示します。今回の150サンプルの既存CSIを使った実行記録はデバッグモードです。

## Sepoliaへのデプロイ

旧デバッグ用Registryと今回の患者照会用Registryは別契約です。前回の記録を新しい記録と見なして移行しません。

```sh
# リポジトリルート。初回のみコピーして設定。
cp .env.sepolia.example .env.sepolia.local
chmod 600 .env.sepolia.local

# 記録用の専用鍵をファイルに生成。標準出力は公開アドレスのみ。
node backend/contracts/scripts/create-recorder.mjs .local/observations/sepolia-recorder.key
```

`.env.sepolia.local` に次を設定してください。

- `ETHEREUM_RPC_URL`: Sepolia RPC。
- `BLOCKCHAIN_PRIVATE_KEY`: デプロイ専用の秘密鍵。
- `ONCHAIN_CHAIN_ID=11155111`。
- `OBSERVATION_RECORDER_ADDRESS`: 上で表示された公開アドレス。

デプロイ用・記録用の両アドレスにSepolia ETHを用意します。記録用アカウントはこのワーカー専用にし、別プロセスから同じ鍵で送信しないでください。

```sh
# 既存デバッグ用契約も公開構成で使う場合
npm run build --prefix backend/contracts
npm run deploy:sepolia --prefix backend/contracts

# 通常の患者照会用契約。OBSERVATION_DEBUG_INPUTSは指定しない。
ONCHAIN_DEPLOY_PUBLIC=true npm run deploy:observations --prefix backend/contracts
```

生成物は `backend/contracts/build/onchain/observations-11155111.json` と `csi_breathing_certificate.vkey.json` です。この2つと、使用したWASM・zkey・検証鍵を同じ版として保管します。ビルドは既存の鍵を使用し、trusted setupをやり直しません。既存鍵・回路の監査と生成経緯の確認は別途必要です。

新契約は回路名・回路IDを各計測に保存しません。デバッグ用の識別情報はmanifestに残します。ただし、公開チェーン上のVerifierコードやアドレスから実装を調べることは可能であり、回路そのものを暗号学的に隠す機能ではありません。

## サーバー起動

`.env.public.example` を基に `.env.public` を設定します。観測用の追加項目は以下です。

```dotenv
OBSERVATION_BUILD_DIR=./backend/contracts/build/onchain
OBSERVATION_MANIFEST_FILE=observations-11155111.json
OBSERVATION_RECORDER_KEY_FILE=./.local/observations/sepolia-recorder.key
OBSERVATION_MAX_TX_WEI=10000000000000000
OBSERVATION_RAW_RETENTION_HOURS=24
```

`OBSERVATION_MAX_TX_WEI` は1トランザクションのガス上限×単価の上限です。例は0.01 ETH相当で、実際に必ずこの金額を支払う意味ではありません。残高不足や上限超過時は処理を停止・再試行します。

```sh
docker compose --env-file .env.public \
  -f docker-compose.public.yml -f docker-compose.observations.yml config --quiet

docker compose --env-file .env.public \
  -f docker-compose.public.yml -f docker-compose.observations.yml up --build -d
```

外側のHTTPSリバースプロキシから `127.0.0.1:8080` に接続します。秘密鍵は署名ワーカーだけに読み取り専用でマウントし、API・フロントエンドには渡しません。公開用ゲートウェイは患者照会APIと認証付き収集APIを許可します。既存研究APIの公開制限は維持します。

今回の永続キューとカタログは専用SQLite/WALで、既存研究DBにマイグレーションは不要です。`observation_data` volumeは保持してください。**単一ホスト・署名ワーカー1プロセス**の構成です。ファイルロックで二重起動を拒否します。複数ホストやNFS共有での運用は対象外です。

患者一覧と計測IDの索引はこのDBにあるため、volumeを失うと患者・時刻の一覧を復元できません。バックアップはAPIとワーカーの書込みを停止してvolume全体を取得するか、SQLiteのbackup APIを使用してください。稼働中のDB本体だけをコピーしないでください。

## PicoScenes端末からの収集

`scripts/capture_observation.py` はPython標準ライブラリのみを使用します。PicoScenes自体のインストール・対応NIC・フレーム送信元の準備は端末側で行います。端末時計はNTP等で同期してください。

```sh
export CSI_SERVER_URL=https://your-domain.example
export CSI_PATIENT_ID=登録した患者UUID
export CSI_OPERATOR_TOKEN_FILE=/保護された場所/operator.token
export CSI_NIC_INDEX=2
export CSI_CBW=160
export CSI_MAIN_DURATION=60

# トークンファイルはサーバーのOPERATOR_API_TOKENと同じ値、権限0600。
chmod 600 "$CSI_OPERATOR_TOKEN_FILE"

# 1回収集
python3 scripts/capture_observation.py

# 継続収集。プロセス停止・通信障害後は同じspoolを使って再起動。
python3 scripts/capture_observation.py --loop

# 未送信分だけを再送
python3 scripts/capture_observation.py --retry-only
```

通信はHTTPSを必須とし、ローカル確認時のloopback HTTPだけを例外とします。標準の一時保存先は `~/.csi-observation-spool`、`CSI_OBSERVATION_SPOOL` で変更できます。端末側でもファイルロックで同時収集を防ぎます。

送信失敗時は同じ収集UUIDで再送します。サーバーが永続キューへの受領を返した後に端末側のコピーを削除します。サーバー側で証明生成が失敗した場合はキューの状態を確認してください。端末での未送信CSIは次回実行時に24時間経過したものを削除します（`CSI_SPOOL_RETENTION_HOURS`）。停止したままの端末では削除処理も動かないため、運用時はサービス管理機構で再起動・監視してください。

既存ファイルを使うデバッグ投入も可能です。元ファイルは削除せず、spoolへのコピーだけを管理します。

```sh
python3 scripts/capture_observation.py \
  --file sampledata/csi_20260519_114943.csi \
  --observed-at 2026-05-19T11:49:43+09:00
```

## 失敗時と再試行

| 状態・エラー | 対応 |
|---|---|
| `queued` | ワーカー起動、鍵、RPC、対象manifestを確認 |
| `processing` | 証明生成中。再起動時は保存済み証明から再開 |
| `submitted` | 同じ署名済みトランザクションを追跡。再署名しない |
| `recorded` | 記録済み。第三者照会ではその都度証明を検証 |
| `insufficient_capture_samples` 等 | 100 Hz・60秒の収集条件を確認して再収集 |
| `raw_expired` | 生CSIの保存期限切れ。再収集が必要 |
| `transaction_reverted` | RPC receiptと契約設定を運用者が確認 |
| `processing_failed` | RPC・鍵・鍵ファイル権限・残高・ガス上限・鍵の版を確認 |

収集状態は認証付き `GET /api/v2/observations/captures/{id}`、再試行は認証付き `POST /api/v2/observations/captures/{id}/retry` です。通常は最大5回、待ち時間を増やして再試行します。入力品質違反は即失敗にします。生CSIは証明保存直後に削除し、未処理・失敗分もワーカー稼働中は保存期限を適用します。

受付中ジョブは標準100件までです。満杯の場合は429を返し、端末に残った同じ収集IDで後から再送します。

署名済みトランザクションの成否が不明な場合、同じnonceで別計測を送ることを避けるため後続署名を止めます。5回失敗後も署名済みデータは保持し、運用者の再試行で同じbytesを再送します。ガス不足による長期pending、外部からのnonce消費、手動置換の自動解決は実装していません。

## 検証範囲

- コントラクトは先に証明を保存し、`verifyObservation` が保存済み証明を検証してからbooleanを返します。不正・未登録はrevertします。
- APIは患者参照ID・計測時刻・期間をチェーンと照合し、必要な確認数と同じブロックの状態で検証します。未確定、照合不一致、RPC障害、検証失敗では `isNormal` を返しません。
- 判定値そのものは公開チェーンのストレージ・トランザクションに存在します。「検証前は暗号学的に秘密」という設計ではありません。
- 患者・時刻・期間は認証された収集側／記録者の申告です。呼吸回路が患者の身元、時計の正確さ、生CSIのセンサー由来を証明しているわけではありません。外部の患者対応表と端末設置・時計管理が必要です。
- 新契約は単一certificate Verifierを固定します。既存VMD/LSのデバッグ回路を切り替えて記録する経路は `/verify` に残します。
- 通常モードの実機連続収集、Sepoliaでの公開運用、コンテナ実起動はこの開発環境では未確認です。手元の実行記録は保存済みCSIを使ったローカルEVMでのデバッグ確認です。

実装コード、スクリーンショット、検証記録は [進捗資料](progress/observations/README.md) にあります。
