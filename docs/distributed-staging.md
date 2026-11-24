# 手持ち3台で構築するSepolia・Fabric実証環境

2026-11-24。**配備用コードと設定を準備した段階。3台への配備、Sepoliaへのコントラクト配備、分散環境での性能測定はまだ実施していない。** 既存ローカル環境・デバッグUIは継続利用できる。

## 今回の構成

| 実機 | 担当 | 現時点で分かっていること |
| --- | --- | --- |
| GMKtec ミニPC | CSI取得、計測側HospitalMSPのpeer、writer bridge、orderer 1 | OS・RAM・空き容量を確認待ち。既存CSI計測設定を維持する |
| このMac | 閲覧側ResearchMSPのpeer、reader bridge、orderer 2、WebUI/API・証明worker | Core i5-8500B / x86_64 / RAM 16 GiB。DockerのVM割当と証明生成の同時負荷を確認する |
| Raspberry Pi 4 | orderer 3 | RAM 8GB。64bit OS・SSD・有線LANの有無を確認待ち |

3台に1つずつ配置するRaft ordererと、別々の実機に置く2組織のpeerを使用する。channelは`csi-staging`、chaincodeは`csiadaptive4004`。書き込みには両組織peerの承認を必要とする。閲覧時のGroth16検証はreader側peerのchaincodeで実行するが、evaluateは1 peerへの問い合わせであり、両組織の再承認や新しいブロック生成を伴わない。

これは2組織を模したLAN実証である。同一所有者が3台を管理する間は、独立組織による運用や拠点間WANの実証とは区別する。ordererは1台停止に耐える構成だが、各組織peerは1台なので、どちらかのpeer停止中は新規記録できない。WebUI・SQLite観測キュー・workerも単一ホストであり、アプリ全体のHA構成ではない。

### 追加PCが必要になった場合の目安

以下はこの実装の**初期配置・調達目安**であり、性能保証された最低仕様ではない。まず実機の最大メモリ・処理時間・温度・ディスク遅延を測る。最初から追加購入する必要はない。

| 役割 | 試験開始の目安 | 備考 |
| --- | --- | --- |
| orderer専用 | 64bit CPU 2コア、RAM 4GB、SSD空き32GB以上 | 手持ちPi 4 / 8GBをまずこの役割に使う |
| peer + orderer + bridge | 64bit CPU 4コア、RAM 8GB、SSD空き64GB以上 | CSI計測と同居するGMKtecは計測落ちも監視する |
| 証明生成専用PC | 64bit CPU 4コア、RAM 16GB、SSD空き100GB以上 | 既存16GB機で実測済みだがスワップ・待ち時間が発生。新規調達ならRAM 32GB以上を推奨 |
| 証明生成 + WebUI + peer同居 | RAM 32GB以上を推奨 | 現在のMac 16GBでは同時負荷に余裕がない。最初は1ジョブずつ実測し、必要なら証明生成を分離 |

Pi 4には64bit OSと有線LANを使用する。台帳の継続書き込み先はSSDを推奨する。Fabric 2.5.16 peer/ordererの配布マニフェストに`linux/arm64`と`linux/amd64`があることを確認した。Piでのこのチェーンコードの動作・性能は未測定。32bit OSのままではこの配備構成を使えない。OS再インストールやCSI機の設定変更は自動では行わない。

## 利用者にお願いする最初の作業

1. 3台を同じLANへ、可能なら有線接続する。ルーターのDHCP予約などでIPを固定する。Fabric用ポートをインターネットへ転送しない。
2. GMKtecのOS・RAM、PiのOSが64bitか、SSDがあるかを確認する。Mac/Linuxならこのリポジトリで`bash scripts/staging/host-info.sh`を実行すれば、CPU・RAM・空き容量・Docker情報が表示される。Windowsなら「設定 → システム → バージョン情報」とディスク空き容量を確認する。
3. GMKtecとPiへSSH接続できる一般ユーザーを用意する。こちらへ伝えるのはLAN IPまたはSSH設定名・ユーザー名まで。パスワード・秘密鍵はチャットに貼らない。
4. 下記2つの専用アドレスにSepoliaの**テストETH**を用意する。2026-11-24の読み取り確認では、どちらも0だった。メインネットETHは不要。

| 用途 | アドレス |
| --- | --- |
| コントラクト配備 | `0xec77D2B256e1c9079CbA30869ca74bBFBb28C32f` |
| 証明記録 | `0xbe0EEc5d93231938Cf743a792516fbb103B48651` |

[Ethereum公式のネットワーク・faucet案内](https://ethereum.org/developers/docs/networks/#sepolia)を参照。残高確認だけなら以下を実行する（秘密鍵の読み取り・送金なし）。残高ゼロは終了コード2。残高があることと必要gas費用を満たすことは別であり、配備時に費用上限を再確認する。

```bash
node backend/contracts/scripts/check-staging.mjs
```

公開ドメインは今すぐ必要ない。まずLANの`csi.home.arpa`などをLAN DNSでMacのIPへ向け、内部CAのHTTPSで利用する。ブラウザーを使うPCにそのCA証明書を信頼登録する必要がある。外部公開時は管理可能なドメインと到達経路を用意し、公開CAのHTTPS設定へ切り替える。大学・研究室回線のポート開放や外部公開が許可されているかは管理者に確認する。

## 配備作業の順番（実機情報確定後に進める部分）

以下は管理者向けの具体的手順。利用者が今すぐ全てを手作業で行う必要はない。各ホストのIP・OSが分かれば、配置に合わせて設定する。

### 1. 基盤と名前解決

LinuxではDocker Engine + Compose、Node.js 22、Fabric 2.5.16 CLI（`peer`、`configtxgen`、`osnadmin`）、`jq`を使用する。Macは既存Docker Desktopを使用。Linux ARM64にはARM64版CLIを使用する。

`deploy/staging/inventory.example.json`をGit対象外の`.local/distributed/inventory.json`へコピーし、組織名、ホストID、実際に解決できるDNS名へ変更する。例の`.invalid`は意図的に配備スクリプトが拒否する。Mac・GMKtec・PiのhostIdはそれぞれ別にする。

DNS名はブラウザーだけでなく**各コンテナからも**解決できる必要がある。Macの`/etc/hosts`を変更しただけではコンテナに伝わらない。LAN DNSの登録を基本とし、証明書のSANにも同じDNS名を入れる。

| 通信 | 制限 |
| --- | --- |
| peer 7051/TCP | Fabric参加ホスト・bridge・管理者からのみ |
| orderer 7050/TCP | Fabric参加ホストからのみ |
| orderer admin 7053/TCP | 管理者だけ。mTLS必須 |
| bridge 8843/TCP | API/workerホストからだけ。HTTPS + role別token |
| WebUI 443/TCP | LAN利用者。公開時は公開対象 |
| operations 9443/9444 | ホストのloopbackのみ。監視はSSH等で回収 |

コンテナを公開する`PRIVATE_BIND_IP`には各ホストのLAN IPを指定し、ルーター／ホストファイアウォールで送信元も制限する。Compose設定だけで送信元を制限するものではない。

### 2. 各組織のCA・MSPとTLS

既存test-networkの秘密鍵を本環境へ流用しない。HospitalMSP、ResearchMSP、OrderingMSPそれぞれの管理者がCAを管理し、所属するpeer/orderer/admin/clientを発行する。NodeOUsを有効化する。新規CAの場合は[公式CA配備ガイド](https://hyperledger-fabric-ca.readthedocs.io/en/latest/deployguide/ca-deploy.html)に従う。CAの起動・登録・enrollmentは配備先と管理者が未定のため、今回まだ行っていない。

各peer/ordererホストには自分のノードの`msp/`と`tls/server.crt`・`tls/server.key`・`tls/ca.crt`だけを置く。秘密鍵は0600。組織adminのMSPはノードMSPと別に管理する。orderer admin API用にはクライアントTLS証明書も発行し、`ADMIN_TLS_CA_FILE`は管理者専用のTLS CAを指定する。一般clientへ発行するCAをそのままadmin APIの信頼先にしない。

channel生成担当が集めるのは**公開情報のみ**：

```text
/srv/csi/public/
  HospitalMSP/msp/{cacerts,tlscacerts,config.yaml}
  ResearchMSP/msp/{cacerts,tlscacerts,config.yaml}
  OrderingMSP/msp/{cacerts,tlscacerts,config.yaml}
  orderers/<orderer DNS名>.crt       # 3台のTLS公開証明書
  recorder.crt                      # HospitalMSP記録クライアントの公開証明書
```

writer/reader bridgeはそれぞれのpeerと同じホストで起動し、互いの秘密鍵を持たせない。bridgeのHTTPS証明書のSANは`writer.csi.home.arpa`、`reader.csi.home.arpa`など実際のURLに一致させる。発行CAが複数なら公開CA証明書をまとめて`bridges-ca.crt`としてAPI/workerへ渡す。

### 3. ノード起動、channel参加

`compose.peer.yml`に必要な環境変数：`PEER_DNS`、`MSP_ID`、`NODE_IDENTITY_DIR`、`PRIVATE_BIND_IP`。
`compose.orderer.yml`：`ORDERER_MSP_ID`、`NODE_IDENTITY_DIR`、`ADMIN_TLS_CA_FILE`、`PRIVATE_BIND_IP`。同じホストでもpeer用とorderer用のenvファイルを分ける。

```bash
docker compose --env-file /srv/csi/config/peer.env -f deploy/staging/compose.peer.yml up -d
docker compose --env-file /srv/csi/config/orderer.env -f deploy/staging/compose.orderer.yml up -d
node deploy/staging/render-channel.mjs .local/distributed/inventory.json /srv/csi/config/configtx.yaml
configtxgen -configPath /srv/csi/config -profile CSIStaging -channelID csi-staging -outputBlock /srv/csi/public/csi-staging.block
```

生成blockを3台へ配り、各orderer管理者が実行する。`ORDERER_ADMIN_ENDPOINT`はそのordererの証明書SANと一致するDNS名`:7053`。

```bash
osnadmin channel join --channelID csi-staging --config-block /srv/csi/public/csi-staging.block \
  -o "$ORDERER_ADMIN_ENDPOINT" --ca-file "$ORDERER_CA" \
  --client-cert "$ADMIN_TLS_CERT" --client-key "$ADMIN_TLS_KEY"
```

2組織のpeer管理者は、自組織の`CORE_PEER_LOCALMSPID`・`CORE_PEER_MSPCONFIGPATH`（admin）・`CORE_PEER_ADDRESS`・`CORE_PEER_TLS_ENABLED=true`・`CORE_PEER_TLS_ROOTCERT_FILE`を設定し、`peer channel join -b /srv/csi/public/csi-staging.block`を実行する。node起動とchannel参加は別操作。

### 4. 同じ検証鍵のchaincodeを両組織が承認

```bash
node fabric/scripts/prepare-external.mjs .local/distributed/inventory.json \
  .local/circom-adaptive-4004/artifacts.json .local/distributed/release-001
peer lifecycle chaincode package .local/distributed/release-001/chaincode.tar.gz \
  --path .local/distributed/release-001/chaincode --lang node --label csiadaptive4004_1
```

配備パッケージ・公開manifest・検証鍵を両組織へ渡す。**同じtar.gz**のSHA256を確認する。実機情報と証明書が一致することを確認してから承認する。秘密鍵を含める必要はない。

各組織で`RELEASE_DIR`、前段の`CORE_PEER_*`、`ORDERER_ENDPOINT`（DNS`:7050`）、`ORDERER_CA`を設定し、次の順に実行する：

```bash
bash fabric/scripts/external-lifecycle.sh install
bash fabric/scripts/external-lifecycle.sh approve
bash fabric/scripts/external-lifecycle.sh readiness
# 両MSPの承認がtrueになった後、片方の管理者が実行する。
# OTHER_PEER_ENDPOINTとOTHER_PEER_TLS_CAも設定する。
bash fabric/scripts/external-lifecycle.sh commit
bash fabric/scripts/external-lifecycle.sh query
```

既存のreleaseディレクトリへの上書きは禁止。変更時は新releaseを作り、`CC_SEQUENCE`を増やして両組織の再承認を得る。recorder証明書のハッシュが固定されるため、その証明書更新もchaincode更新が必要。

### 5. role別HTTPS bridge

各ホストに`BRIDGE_IDENTITY_DIR`を用意し、`client.crt`、`client.key`、接続先peerの`peer-ca.crt`、HTTPS用`tls/server.crt`・`tls/server.key`、乱数の`bridge.token`（例：`openssl rand -hex 32`、ファイル0600）を置く。writerはパッケージに固定したrecorder証明書を使う。

```bash
node fabric/scripts/configure-external-gateway.mjs /srv/csi/release/deployment/manifest.json \
  writer HospitalMSP peer.hospital.csi.home.arpa:7051 /srv/csi/bridge-writer
docker compose --env-file /srv/csi/config/bridge.env -f deploy/staging/compose.bridge.yml up --build -d
```

閲覧側では`reader ResearchMSP`と閲覧側peerのDNS名・ディレクトリに変更する。`bridge.env`は`BRIDGE_ROLE`、`BRIDGE_IDENTITY_DIR`、`PRIVATE_BIND_IP`を設定する。生成したgateway.json内の`/identity`はコンテナ内パス。ホストからbenchmark CLIを実行するときは、CLI専用設定のパスをそのホストのファイルへ変更する。

### 6. Sepolia配備とアプリ

テストETH準備後、既存の[Sepolia手順](adaptive-sepolia-setup.md)で実デプロイする。デプロイ担当鍵と記録鍵は別にする。鍵ファイルは現在のMacの`.local/sepolia-adaptive/`にあり、Gitに含まれない。`OBSERVATION_DEBUG_INPUTS=true`を付けて実証用debug表示を維持できる。

```bash
OBSERVATION_DEBUG_INPUTS=true node --env-file-if-exists=.env.sepolia.local backend/contracts/scripts/deploy-adaptive-sepolia.mjs
python3 scripts/staging/export_artifacts.py .local/circom-adaptive-4004/artifacts.json .local/distributed/portable-artifacts
```

portable-artifactsをアプリホストの`ARTIFACT_DIR`へ転送する。Mac用のネイティブバイナリをコピーせず、Linuxコンテナ内で同じRustソースとCargo.lockからビルドする。R1CS・WASM・証明鍵・検証鍵のハッシュを維持し、trusted setupは再実行しない。元鍵は`single-party-local-csprng-testnet-only`の実証用であり、正式な本番運用へ進むときは別途setupの信頼設計が必要。

`DEPLOYMENT_DIR/sepolia/`と`DEPLOYMENT_DIR/fabric/`へ、それぞれmanifestと対応する検証鍵を置く。`deploy/staging/{app,api,worker,database}.env.example`をコピーし、空の秘密値を乱数に置き換える。APIにはreader tokenだけ、workerにはwriter tokenとSepolia記録鍵だけを渡す。PostgresパスワードはDB envとAPI DATABASE_URLで一致させ、URLへ入れる場合は適切にURLエンコードする（hex乱数ならそのまま使用可能）。

```bash
# ドメイン未取得のLAN段階
docker compose --env-file /srv/csi/config/compose.env \
  -f deploy/staging/compose.app.yml -f deploy/staging/compose.lan.yml config --quiet
docker compose --env-file /srv/csi/config/compose.env \
  -f deploy/staging/compose.app.yml -f deploy/staging/compose.lan.yml up --build -d
docker compose --env-file /srv/csi/config/compose.env \
  -f deploy/staging/compose.app.yml -f deploy/staging/compose.lan.yml run --rm backend alembic upgrade head
```

Caddyの`/data/caddy/pki/authorities/local/root.crt`をクライアントへ渡し信頼登録する。ブラウザーのTLS検証を無効化しない。外部公開段階では`PUBLIC_DOMAIN`・`ALLOWED_ORIGINS`を実ドメインへ変更し、`compose.lan.yml`を外す。公開HTTPSにはDNSと80/443への到達性が必要。

workerは1個だけ動かす。キューはSQLiteなので、複数ホストへのworker水平分割やNFS上の共有はしない。既存debug環境とはComposeプロジェクトと永続volumeを分けている。新アプリは新しい患者一覧から開始する。既存患者データの移行はこの手順では行わない。

## 実配備後の検証・測定

1. 実CSIで1件送信し、証明生成→両台帳の記録→患者・時刻選択→検証後の`isNormal`表示を確認する。公開チェーンの入力をUI外で読める点は従来仕様どおり。
2. 誤った署名・TLS/CA・別部署token・異なるdeployment・破損proofに対して結果が返らないことを確認する。
3. ordererを1台停止して継続を確認。peerを1台停止した場合は新規記録が失敗し、復帰後に再試行できることを確認する。停止操作は実証データの範囲で行う。
4. 既存の実CSIから新nonceの証明を用意し、同じ回路・検証鍵・proofをSepolia/Fabricへ1回ずつ記録する。合成CSIは使用しない。
5. `deploy/staging/benchmark.example.json`をコピーして設定する。writer/readerの接続先を別々のpeerに指定できる。実行例：`node fabric/benchmark/run.mjs .local/distributed/benchmark.json`。証明バンク作成は[既存手順](adaptive-sepolia-setup.md#比較測定の扱い)に従い、出力先を合わせる。

証明生成・記録確定待ち・検証queryの時間を分ける。FabricはVALID commit、Sepoliaは設定した承認数（初期値2）を待つ。2承認をEthereumのfinalizedと同一視しない。検証queryはFabric evaluate / EVM eth_callであり、検証トランザクションのブロック確定時間ではない。

SepoliaはgasUsed・実test ETH費用、Fabricはgasなしと明記し、実機の消費電力・稼働時間・機器費用を別枠で集計する。機器費用と電力量が未入力なら円換算値は出さない。全機器のCPU・RAM・OS・ネットワーク・同居サービス・時刻同期状態も記録する。LANの結果をWANや医療現場の実測と表現しない。

## 運用上残る作業

実サーバーの配置・証明書発行・実配備、Linux版proverによる実CSIの証明生成、Piでの起動と継続稼働、バックアップ復元、障害試験はまだ完了していない。workerメモリ上限12GiBは仮設定で、MacのDocker VM割当を超えないよう調整し、OOM時は上限だけを増やさず役割分離も検討する。

台帳・Postgres・観測SQLite・CAのバックアップは別々に管理する。SQLiteはworker停止＋SQLite backup APIなど整合性の取れる方法を使い、稼働中のdbファイル単独コピーは避ける。peerのDocker socketはそのホストの強い権限に相当するため、参加組織の管理者だけが操作できる専用実行環境とする。API/workerにはDocker socketを渡さない。

## 根拠となる公式資料

- [Fabric production deployment guide](https://hyperledger-fabric.readthedocs.io/en/release-2.5/deployment_guide_overview.html)：組織別CA・peer・ordererの配備計画。
- [Channel participation](https://hyperledger-fabric.readthedocs.io/en/release-2.5/create_channel/create_channel_participation.html)：system channelなしのchannel作成・参加。
- [Fabric 2.5 architectures](https://hyperledger-fabric.readthedocs.io/en/release-2.5/whatsnew.html)：amd64 / arm64。
- [Ethereum networks](https://ethereum.org/developers/docs/networks/)：アプリ開発用Sepolia。
