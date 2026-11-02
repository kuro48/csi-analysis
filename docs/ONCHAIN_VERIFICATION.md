# CSI → Groth16 → オンチェーン検証

通常構成では `/` と `/research` が既存のCSI解析モニター、`/verify` がオンチェーン検証コンソールです。公開用Composeでは `NEXT_PUBLIC_APP_MODE=public` を指定し、トップ `/` は患者別の呼吸判定照会画面になります。証明デバッグコンソールは引き続き `/verify` です。[患者照会・実機収集の運用手順](PATIENT_OBSERVATIONS.md) を参照してください。
標準フローは `csi_breathing_certificate` 回路を使います。CSI解析APIから証明を生成するか、既存の証明JSONを読み込み、ウォレットから検証トランザクションを送信します。

## 検証の仕組み

1. CSIは運用者トークンで保護された `/api/v2/breathing/analyze-certificate` で解析。一時ファイルは処理後に削除。50 MB上限・プロセスあたり同時1件。
2. `/api/v2/onchain/prepare` は実際のRegistryを `eth_call` で実行し、証明を事前検証。ここでは記録されません。
3. ブラウザは送信先・チェーンID・calldata・value=0を再確認し、自分でcalldataを再構築。ユーザーのウォレットがガス代を負担します。サーバー署名鍵は不要です。
4. `VerifiedProofRegistry.verifyAndRecord` が同一トランザクション内でGroth16 Verifierを呼び出します。成功した場合だけ記録と `ProofVerified` イベントを作成します。
5. APIは送信先、receipt.status、イベントの発行元、ブロックハッシュ、確認数を照合。UIはpending / confirming / confirmed / revertedを表示します。

回路設定はデプロイ時に固定され、管理者による「検証済みフラグの書換え」はありません。旧 `ZKProofRegistry` と互換性のない別契約です。旧レコードを新契約の検証済みとして取り込みません。DBマイグレーションは不要です。

回路IDには検証鍵ファイルのSHA-256を含みます。APIはmanifestと実際のチェーンID・Registryコードハッシュ・登録回路を照合します。デプロイした鍵と証明生成に使用する鍵は必ず同じものを使用してください。

## ローカル起動

Python 3.11、Node.js 22以上、既存の回路WASM・R1CS・zkey・verification keyが必要です。
鍵は開発用のものと公開運用用のものを区別してください。この手順では既存の鍵からVerifierを生成し、trusted setupを勝手にやり直しません。

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r backend/requirements.txt
npm ci --prefix zkp
npm ci --prefix backend/contracts
npm ci --prefix frontend
bash scripts/start-onchain-local.sh
```

検証画面は `http://127.0.0.1:3000/verify`。CSI解析用のトークンは `.local/onchain/operator-token` に保存します。
ブラウザウォレットへローカルネットワーク（RPC `http://127.0.0.1:18545`、Chain ID `31337`、通貨記号 `ETH`）を登録し、`.local/onchain/chain.log` の使い捨てテストアカウントを使用します。実資産を入れないでください。
ローカルチェーンは終了時に消えます。既存のPostgres/Redisには接続・変更しません。研究用DB画面は別途DBの起動・初期化が必要です。

## 既存のWeb UIとの統合

1. CSI解析モニター、手動アップロード、保存せず解析の各画面で、必要に応じて「解析APIへのアクセス」に運用者トークンを入力します。認証情報は同じタブ内の画面遷移で共有し、再読み込みすると消えます。CSVの取得にも同じ認証を使います。
2. 解析結果の各証明カードで「この証明をオンチェーンで検証」を選びます。有効な証明本体のない古いレコード、生成失敗、未知の方式ではボタンを無効にします。
3. `/verify` に証明・回路名・公開入力だけを引き継ぎます。生CSI、波形、デバイスID、トークンは引き継ぎデータに含めません。一時的なsessionStorageの証明は読み込み時に削除し、10分で期限切れになります。
4. 送信先・公開入力を確認して公開に同意した後、ウォレットで送信します。画面遷移だけでは事前検証やトランザクション送信を実行しません。

既存解析の前処理・VMD・Lomb–Scargle回路は、certificate回路とは別です。**生成に使った鍵に対応するVerifierの追加デプロイが必要**です。初期構成はcertificateのみで、未登録回路は送信できません。回路名が同じでも公開入力数が異なる版を画面で検出します。入力数が一致しても鍵が違えば、送信前の実Verifier実行で拒否されます。回路を再構築した場合は対応する鍵で証明を再生成してください。

公開用ゲートウェイは研究APIを公開しません。一般公開用コンソールと、認証された研究用UIの配信構成は用途に応じて選んでください。

## 証明JSONの形式

`proof` はsnarkjsが出力したオブジェクトをそのまま利用し、座標・公開入力を**10進数文字列**で渡します。

```json
{
  "circuit": "csi_breathing_certificate",
  "proof": {
    "protocol": "groth16", "curve": "bn128",
    "pi_a": ["...", "...", "1"],
    "pi_b": [["...", "..."], ["...", "..."], ["1", "0"]],
    "pi_c": ["...", "...", "1"]
  },
  "publicSignals": ["0"]
}
```

上記は構造の例で、有効な証明ではありません。生のCSIや診断結果を含む解析レスポンスは、画面で証明と公開入力だけに絞り込まれます。

## テストネット（Ethereum Sepolia）へのデプロイ

当面の公開検証先は **Ethereum Sepolia（Chain ID 11155111）** です。デプロイスクリプト・APIとも、SepoliaとローカルEVM（31337/1337）だけを許可します。メインネット用の設定は拒否します。

1. Sepolia対応のRPCと、Sepolia ETHを持つテスト専用ウォレットを用意します。デプロイ用ウォレットと、UIから証明を送信する各ウォレットにガス代が必要です。
2. ルートで `.env.sepolia.example` を `.env.sepolia.local` にコピーし、`ETHEREUM_RPC_URL` と `BLOCKCHAIN_PRIVATE_KEY` をローカルで設定します。秘密鍵をチャット、フロントエンド、`.env.public` に記載しないでください。このファイルはGit管理対象外です。
3. 次のコマンドで既存zkeyからVerifierを生成し、Sepoliaにデプロイします。

```sh
# リポジトリルート
cp .env.sepolia.example .env.sepolia.local
chmod 600 .env.sepolia.local
# ローカルのエディタで上記2項目を設定
npm run build --prefix backend/contracts
npm run deploy:sepolia --prefix backend/contracts
```

専用コマンドは `.env.sepolia.local` を読み込み、実際のRPCのChain IDも確認します。異なる `ONCHAIN_CHAIN_ID` が設定されていれば送信前に停止します。APIサーバーにはデプロイ用秘密鍵を渡しません。

結果は `backend/contracts/build/onchain/deployment-11155111.json`。manifest、生成Solidity、compiled.json、対応する検証鍵・proving keyの版をセットで保管してください。テストネットで公開する際もデプロイ済みソースをExplorerで検証し、manifestのアドレスとコードハッシュを公開運用者がレビューしてください。
追加回路は `npm run build -- csi_breathing_certificate csi_vmd_approx` のように指定できます。各回路の既存zkeyが必要です。公開入力は1〜256個に制限します。別回路の証明は別レコードで、回路間の連続性は自動的には証明しません。

## 公開Web配信

通常の `docker-compose.yml` は研究・開発用のままです。公開配信には独立した `docker-compose.public.yml` を使用してください。

```sh
cp .env.public.example .env.public
# .env.public にRPC、manifestのパス、公開HTTPS Originを設定
# JWT_SECRET_KEY / OPERATOR_API_TOKEN はそれぞれ openssl rand -hex 32 で生成
# POSTGRES_PASSWORD も独立した強い値に設定
docker compose --env-file .env.public -f docker-compose.public.yml config --quiet
docker compose --env-file .env.public -f docker-compose.public.yml up --build -d
```

TLSを終端するリバースプロキシから `127.0.0.1:8080` に接続してください。インターネット向けTLS、DNS、バックアップ、監視は配信環境側で用意します。ゲートウェイは接続元IPでレート制限するため、外側にプロキシを置く場合は信頼するプロキシだけを対象にreal-IP設定を行ってください。

公開ゲートウェイは以下だけをAPIとして許可します。

| API | 用途 | 認証 |
|---|---|---|
| GET `/api/v2/onchain/status` | 接続・回路・件数 | 公開 |
| POST `/api/v2/onchain/prepare` | 送信前検証、128 KBまで | 公開、レート制限 |
| GET `/api/v2/onchain/transactions/{hash}` | 検証トランザクション照会 | 公開 |
| GET `/api/v2/onchain/proofs/{id}` | Registryレコード照会 | 公開 |
| POST `/api/v2/breathing/analyze-certificate` | CSI解析と証明生成 | Bearer運用者トークン、レート制限 |

研究API・旧ブロックチェーンAPIはゲートウェイで404。APIコンテナの直接アクセスでも `PUBLIC_MODE=true` で研究APIに認証を要求します。Postgres、RPC、バックエンドのホストポートは公開しません。起動時の旧契約自動デプロイやDBへの `alembic stamp head` は、この構成では実行しません。公開フローはステートレスなので研究用DBテーブルは不要です。

## 保証範囲・制約

- 「有効な証明」と公開判定 `isNormal=1` は別です。`isNormal=0` の有効な証明も記録します。
- certificate回路は再構成性・帯域判定を検証します。生CSIの真正性、センサーの所有者、VMD処理全体の正しさ、医学的診断は保証しません。
- 証明・公開入力・送信元・時刻は公開されます。既存certificate回路の公開出力は判定値だけで、個々の計測への暗号学的な紐付けを追加するものではありません。
- 重複防止は同一証明に対して行います。証明の再ランダム化や新しい証明を排除する計測単位のnullifierではありません。他人の証明を先に送信できるため、送信者は計測所有者の証明になりません。
- 現在のUIの認証は運用者用の共有トークンです。一般利用者のアカウント登録、ユーザー別課金・隔離、ジョブキューは実装していません。
- メモリ内の同時実行制限は1ワーカー前提。公開Composeも1ワーカー固定です。複数レプリカに拡張する場合は共有キュー・共有制限を追加してください。
- pendingが長く続く場合、ウォレットでキャンセル・置換された可能性もあります。置換先のハッシュを照会してください。失われたトランザクションを自動で再送信しません。
- 独立した回路・コントラクト監査、trusted setupの検証は未実施です。開発用エントロピーから作成された鍵を本番用として扱わないでください。

## テスト・進捗資料

```sh
cd backend/contracts
npm run build
node scripts/proof-fixture.mjs
npm test
```

証明fixtureは合成波形から作成しますが、Groth16証明とEVM検証は実際に実行します。再実行する場合はfixtureを再生成してください（同じ証明は重複として拒否されます）。

```sh
# ルートディレクトリから
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 DEBUG=true ZKP_AUTO_COMPILE=false \
  .venv/bin/python -m pytest -p pytest_asyncio.plugin -p pytest_cov.plugin backend/tests
cd frontend
npm run lint
npm run type-check
npm run test:unit
npm run build
npx playwright install chromium
# ローカルスタックを起動した状態で
E2E_LOCAL_CHAIN=true npm run test:e2e
# 実測CSIも含める場合
E2E_LOCAL_CHAIN=true E2E_CSI_FILE=../sampledata/csi_20260519_114943.csi \
  E2E_OPERATOR_TOKEN="$(cat ../.local/onchain/operator-token)" npm run test:e2e
```

pytestの自動プラグイン読込を無効化する理由は、既存web3 6.15.1のpytestプラグインと新しいeth_typing間の互換性問題です。必要なpytest-asyncioとpytest-covは明示的に読み込みます。
スクリーンショットと実行結果は [進捗記録](progress/onchain/README.md) に保存します。

Sepoliaの概要・Faucet一覧: [Ethereum公式ネットワーク資料](https://ethereum.org/developers/docs/networks/)。

参照: [snarkjs公式のSolidity検証手順](https://github.com/iden3/snarkjs)、[ethers公式ドキュメント](https://docs.ethers.org/v6/single-page/)、[Next.jsセキュリティ告知](https://nextjs.org/blog/nextjs-security-update-october-14-2026)。
