# Hyperledger Fabric と Sepolia の比較

既存のEVM/Sepolia実装を維持し、同じCSI証明をFabricにも記録できます。第三者用の `/patients` は共通です。患者・時刻を選択すると、その計測の記録先に問い合わせ、証明が有効な場合だけ `isNormal` を返します。`false` も有効な検証結果で、エラーや未確定を `false` と表示しません。

**実測済みなのはローカルFabricとローカルEVMです。Sepoliaの実測には、利用者側のRPC・テストETH・デプロイ設定が必要です。ローカルEVMの測定値をSepoliaとして扱ってはいけません。**

## 実装と信頼の範囲

| 工程 | Sepolia / EVM | Fabric |
|---|---|---|
| CSI取得・前処理・証明生成 | 既存の収集端末、Pythonワーカー、Groth16 | 同じ処理・同じ検証鍵 |
| 記録 | `BreathingObservationRegistry.recordObservation` | `Observations.RecordObservation` |
| 記録確定 | receipt + 指定confirmation数 | Gateway CommitStatus `successful=true` / code 0 |
| 結果の取得 | `verifyObservation` の `eth_call` | `VerifyObservation` の Gateway evaluate |
| 暗号検証 | Solidity BN254 verifier | peer上のchaincodeで `snarkjs.groth16.verify` |
| 第三者アクセス | 公開API → RPC | 公開API → 読み取りbridge → Org2のMSP ID |
| 送信者制限 | recorderウォレット | Org1MSP + 記録者証明書のDER SHA-256 |
| 記録承認ポリシー | EVMネットワーク | `AND('Org1MSP.peer','Org2MSP.peer')` |

Fabricの検証は**peer上のchaincode実行**です。照会を新たなブロックに記録する機能ではありません。Gateway evaluateは通常1つのpeerで実行し、両組織の検証署名を収集する方式ではありません。EVM側もread-only `eth_call` なので、比較では読み取り同士をそろえています。第三者がFabricのメンバー証明書を持つ必要はなく、APIが照会用IDを使用します。

API/UIが検証後に結果を表示する要件を実装しています。台帳を読めるFabric参加者は保存された公開信号を直接読めます。Sepoliaでは誰でも読めます。暗号的な結果秘匿・患者本人認証は追加していません。患者IDと時刻は記録者による付帯情報で、現在の一出力回路がその真実性を証明するわけではありません。

検証鍵・書き込み証明書・MSP・チャネル・コードハッシュをdeployment manifestに固定します。Fabricの管理組織はchaincodeを更新できるため、この固定はコンソーシアムの運営・更新承認を信頼する前提です。検証鍵や記録者を更新する場合は両組織のlifecycle承認とmanifest更新が必要です。古い計測を新しいdeploymentへ自動的に付け替えません。

## ローカルネットワークの起動

前提：Docker起動済み、Node 22.12以上、Git・curl・jq、既存の `.venv` とZKPのWASM/zkey/vkey。TCP 7050・7051・9051・7053・9443〜9445等のFabricポートを空けます。

```bash
# リポジトリのルートで実行。短いサンプルCSIで確認する場合だけ true。
FABRIC_DEBUG_MODE=true bash fabric/scripts/setup-test-network.sh
```

Fabric 2.5.16、fabric-samples commit `5789681b4f4d24e58fa40f19a69f5496892374b6` を使用します。2組織各1peer、Raft orderer 1台、LevelDB、標準test-networkのブロック設定です。FabricバイナリとDockerイメージの初回ダウンロードが発生します。

`setup-test-network.sh` は既存ネットワークの `down` やDockerのpruneを実行しません。既存の同名ネットワークがある場合は構成を確認してから実行してください。`.local/fabric` に証明書、ローカル秘密鍵、bridgeトークン、生成chaincodeパッケージ、manifestを配置します。これらはGit対象外です。再実行で既存manifestと内容が変わる場合は停止します。意図的な更新時のみ `FABRIC_UPGRADE=true FABRIC_CC_SEQUENCE=2 FABRIC_CC_VERSION=1.1` 等を指定してください。

```bash
# それぞれ別の端末で起動（ローカルループバック限定）
bash fabric/scripts/bridge.sh reader  # 8801 / Org2 / verifyのみ
bash fabric/scripts/bridge.sh writer  # 8802 / Org1 / recordのみ

# APIとワーカー。通常の8000番が使用中なら既存APIの設定へ下記を統合する。
bash fabric/scripts/app.sh api
bash fabric/scripts/app.sh worker

# 既存フロントエンド
cd frontend && npm run dev
```

`app.sh` はローカル開発用です。既定の患者カタログは `.local/fabric/observations`。既存の患者カタログを共有する場合はAPIとワーカーの両方に同じ `OBSERVATION_DATA_DIR` を指定します。既存運用者トークンを利用する場合は `OPERATOR_TOKEN_FILE` を指定します。既定のローカル運用者トークンは `.local/fabric/operator.token` にあり、画面へ入力します。秘密値をチャットやGitに貼らないでください。

通常のサービス構成に組み込む場合：

| 設定 | API | ワーカー |
|---|---|---|
| `OBSERVATION_DATA_DIR` | 同じ永続ディレクトリ | 同じ永続ディレクトリ |
| `FABRIC_OBSERVATION_MANIFEST` | `.local/fabric/deployment/manifest.json` | 同左 |
| `FABRIC_READER_URL` / `FABRIC_READER_TOKEN` | reader bridgeのURL・トークン | 不要 |
| `FABRIC_WRITER_URL` / `FABRIC_WRITER_TOKEN` | **不要** | writer bridgeのURL・トークン |
| `OBSERVATION_MANIFEST` / `ETHEREUM_RPC_URL` | EVMも利用する場合 | EVMも利用する場合 |
| `OBSERVATION_RECORDER_KEY_FILE` | **不要** | EVMも利用する場合 |

bridgeのURLはローカルHTTPまたはHTTPSのみ許可します。公開運用ではAPI、writer bridge、reader bridgeを別の実行ユーザー/コンテナに分け、秘密鍵とトークンを各サービスにだけmountしてください。サンプルの同一OSユーザーでのプロセス分離は、秘密鍵へのOSレベルのアクセス分離ではありません。

## WebUI・収集端末

1. `/capture` の「証明の記録先」で **Hyperledger Fabric** を選択。
2. 運用者トークンを入力し、患者・時刻・CSIを送信。
3. ワーカーが証明生成→Fabricの両組織による記録承認→コミットを待機。
4. `/patients` で同じ患者と `· Fabric` 表示の時刻を選択。「証明を検証して結果を取得」で `isNormal` を表示。

通常の収集端末では、既存の設定に `CSI_LEDGER=fabric` を加えます。未指定は従来どおり `evm`。スプールには記録先も保存されるため、再送時に環境変数を変更しても元の記録先を維持します。

```bash
CSI_LEDGER=fabric python3 scripts/capture_observation.py --loop
```

通常モードは従来どおり約100Hz・60秒のCSIを要求します。付属の短いCSIはdebug deployment専用です。画面にもデバッグ計測と表示します。

## 同条件での比較測定

新しいfixtureを毎回生成してください。各証明はランダム化されますが、一度台帳に記録した同じ証明の再使用は重複拒否の対象です。各trialでは**同じ証明・公開信号・患者参照・時刻**を両基盤へ送り、実行順序を交互にします。並列数は1です。

```bash
# 実CSIを使う。短いサンプルは --debug。通常計測はこのオプションを外す。
.venv/bin/python fabric/benchmark/csi-fixtures.py \
  sampledata/csi_20260519_114943.csi .local/fabric/csi-fixtures.json --debug --count 6

# 合成信号による暗号処理だけの確認も可能（実患者CSIとは区別）
node fabric/benchmark/generate-fixtures.mjs .local/fabric/fixtures.json 6

# Sepolia設定のひな形
cp fabric/benchmark/sepolia.example.json .local/fabric/benchmark-sepolia.json
# パス、確認数、出力先を編集した後に実行。RPCは環境変数で渡す。
node fabric/benchmark/run.mjs .local/fabric/benchmark-sepolia.json
```

ローカルEVMを使用する場合は `targets: ["fabric", "local-evm"]`、EVMのmanifest・recorder鍵・RPCをローカル用に変更します。chain IDが11155111でなければ `sepolia` ターゲットは動作しません。mainnetには送信できません。

既存結果への追記・上書きを防ぐため、再測定では `output` に新しいディレクトリを指定してください。

出力は `raw.jsonl`（各試行を即時保存）、`raw.csv`、`summary.json`、ブラウザで開く `report.html`。成功件数、失敗件数、中央値、nearest-rank p95を記録します。5回のp95は最大値に等しく、統計的な性能保証ではありません。論文・評価用途では回数・負荷・配置条件を増やしてください。ウォームアップは集計から外れますがrawには残ります。

- **証明生成**：合成信号版はsnarkjs fullProve（witness+prove）。CSI版は既存Pythonサービス呼び出し全体で、ローカル検証・子プロセス等も含みます。各reportに範囲を明記。CSI前処理は別測定し、チェーン別の合計には含めません。
- **記録**：Fabricはproposal→endorse→submit→VALID commit。EVMはsend→receipt→指定confirmation数。EVMのgas見積もり・接続準備は除外。confirmation数はEthereumのfinalizedを保証するものではありません。
- **検証・取得**：Fabric evaluateとEVM eth_callの往復時間。EVMはreceiptのブロックに固定し、reorgも確認します。両者は実行エンジンもネットワーク配置も違うため、差をコンセンサス方式だけの効果と断定できません。
- **合計**：上記3工程の和。CSI取得時間、API受付、キュー待ち、初期接続、デプロイは除外。
- **gas・料金**：EVM receiptのgasUsed × effectiveGasPriceをweiで保存。Sepoliaはテスト通貨であり実際の金銭支出ではありません。検証成功後の集計だけでなく、記録済みで後続照会に失敗した試行の支払手数料も残します。送信後にタイムアウトしreceiptを取得できなかった試行は料金未確定として扱い、transaction IDで後から確認が必要です。
- **Fabric運用費**：ネイティブ通貨の取引料金はありませんが、peer/orderer、CA、監視、保守、バックアップ等の費用が必要です。標準では未算出。設定に `infrastructure: {"target":"fabric","hourlyCost":100,"operationsPerHour":1000,"currency":"JPY"}` を与えると、明示した仮定による配賦額を表示します。実測料金とは区別します。

## 利用者側に必要なSepolia作業

1. SepoliaのRPCを取得し、ローカル環境変数 `ETHEREUM_RPC_URL` に設定。
2. デプロイ用ウォレットと記録専用ウォレットにSepoliaテストETHを用意。既存の [Sepolia手順](ONCHAIN_VERIFICATION.md) と [患者計測手順](PATIENT_OBSERVATIONS.md) に従い、記録専用鍵は0600のファイルに保存。
3. `ONCHAIN_CHAIN_ID=11155111`、`ONCHAIN_DEPLOY_PUBLIC=true`、`BLOCKCHAIN_PRIVATE_KEY`、`OBSERVATION_RECORDER_ADDRESS` を設定し、`node backend/contracts/scripts/deploy-observations.mjs` を実行。比較するFabricと同じ `OBSERVATION_DEBUG_INPUTS` / 検証鍵を使用。
4. 生成された `observations-11155111.json` と記録者鍵ファイルをbenchmark設定に指定。新しいfixtureを生成して実行。
5. JSON/HTMLを共有すれば、実測Sepoliaとの比較表を得られます。秘密鍵・RPCのAPIキーはレポートへ書き出しません。

## 検証・運用上の制約

```bash
npm --prefix fabric test
# 実ネットワークのテスト。2件以上の未使用fixtureが必要。
node fabric/test/network.mjs .local/fabric/gateway.json .local/fabric/integration-fixtures.json
```

実ネットワークではvalid true/false、改ざん公開信号の拒否、Org2による書き込み拒否、再送の冪等性、ID衝突・証明使い回しの拒否を確認しています。バックエンドはFabric停止・結果改ざん・患者/時刻/transaction不一致で結果を返しません。

このtest-networkは本番構成ではありません。別組織・別ホスト配置、複数orderer、CA登録/失効、鍵更新、バックアップ、障害時復旧、APIの公開運用設定は実運用前に設計・検証が必要です。通常のソース変更で既存記録の検証鍵を取り替えないでください。SQLiteには `ledger` 列を追加し、既存行は `evm` として移行します。ファイルとDBのバックアップは従来どおり必要です。

## 公式仕様

- [Fabric test network](https://hyperledger-fabric.readthedocs.io/en/latest/test_network.html)：テスト構成の用途・制約。
- [Fabric Gateway](https://hyperledger-fabric.readthedocs.io/en/latest/gateway.html)：evaluate / endorse / submit / commit status。
- [Gateway Node Contract API](https://hyperledger.github.io/fabric-gateway/main/api/node/interfaces/Contract.html)：処理段階別の呼び出し。
- [Fabric performance considerations](https://hyperledger-fabric.readthedocs.io/en/latest/performance.html)：配置、ブロック設定、エンドースメント等の性能条件。
