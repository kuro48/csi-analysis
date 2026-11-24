# Macで検証を続け、GMKtecへ段階的に集約する実証環境

2026-11-24、段階的な移行方針を確認。**本番まではMacでWebUI・開発・検証を継続し、最終的にCSI取得・証明生成・アプリをGMKtecへ集約する。** 「今からMacを実行環境から外す」という前回の解釈を訂正する。新回路のGMKtec移行・実Sepolia配備・分散Fabric測定は未実施。

## 検証段階と最終配置

| 段階 | GMKtec | Mac |
| --- | --- | --- |
| 現在 | 既存CSI取得・旧証明環境を維持 | 現行WebUI、証明コードの開発・検証を継続 |
| 次の分離検証 | 新回路の証明生成、API、観測キュー、記録処理 | WebUIを動かし、GMKtecのAPI経由で操作・結果を確認 |
| 本番前の集約 | CSI取得・API・証明生成・WebUIを運用 | 常時稼働に依存しない。開発・保守には引き続き使用可能 |

GMKtecはSSH確認済み（i5-12450H / 8コア12スレッド / RAM約16GB / Ubuntu 22.04.5 / 空き約420GiB）。CSI取得・新証明生成・WebUIの同時負荷を測ってから集約する。Mac側での検証を先に止める必要はない。

WebUIの配置と証明の正しさは独立している。UIはAPIに要求を送り、APIが台帳検証に成功した場合だけ結果を返す。WebUIを別端末に置く場合も、ブラウザーに証明鍵や記録用秘密鍵を渡さない。

### 台帳の配置はアプリ移行と別に決める

Pi 4 / 8GBはFabricノード候補。2組織peer・3ホストRaftの設定は準備済みだが、各ノードの実機配置はまだ確定していない。Macも検証期間の候補に戻す。ただし、WebUIをMacに置く方針だけを理由に台帳ノードまで自動配置はしない。

前回の「追加PC不要」と、その後の「追加2台が必要」という断定はいずれも採用しない。台帳ノードの同居可否・障害時要件・計測への負荷を決めてから必要台数を判断する。3ホストRaftを維持するなら、3つの異なるホストが必要という条件自体は変わらない。

「GMKtecへ集約」は計測・証明・アプリの配置方針。Sepolia自体や、独立組織で運用するFabricの全ノードまでGMKtec一台へ集約するという意味ではない。

channelは`csi-staging`、chaincodeは`csiadaptive4004`。書き込みには両組織peerの承認を必要とする。閲覧時のGroth16検証はreader側peerのchaincodeで実行するが、evaluateは1 peerへの問い合わせであり、両組織の再承認や新しいブロック生成を伴わない。

同一所有者が機器を管理する間は2組織を模した実証であり、独立組織・拠点間WANの実証とは区別する。3ホストRaftはorderer 1台停止を想定できるが、各組織peerが1台なので、どちらかのpeer停止中は新規記録できない。

### WebUIと証明生成は、まずAPIを境界に分ける

`compose.app.yml`のAPIとworkerは同一ホストのSQLite観測キューを共有する。**WebUIだけをMacに置き、API・worker・キューをGMKtecに置くなら、このキューを分離する必要はない。** 逆に、APIをMacに残してworkerだけをGMKtecへ移す構成には、別途リモートジョブ連携が必要。この2つを混同しない。

`compose.edge-api.yml`を追加した。GMKtecのAPIをloopbackに公開し、SSHトンネル経由でMacのWebUIから使うための開発用設定。設定検査済みだがGMKtecへの実配備・WebUIからの疎通は未実施。GMKtecにはDockerコマンドが見つかっておらず、導入またはネイティブ配備の準備も必要。具体的な接続手順は[GMKtec移行手順](gmktec-edge-migration.md)を参照。

最終的には同じAPIインターフェースを保ったままWebUIもGMKtecへ移す。画面移動だけのために回路や証明鍵を作り直す必要はない。

「取得と同時に生成」は、計測を続けながら取得済みの窓を別ジョブで証明する方式とする。未来のサンプルを待たずに証明できるという意味ではない。GMKtecでの新回路の生成時間・最大RAM・CSI取りこぼしは未測定で、リアルタイム処理能力を保証しない。

### ハードウェアの目安

以下は初期配置の目安であり、性能保証された最低仕様ではない。GMKtecのメモリ増設や機器追加は、実際の同時稼働測定と配置確定後に判断する。

| 役割 | 試験開始の目安 | 今回の扱い |
| --- | --- | --- |
| orderer専用 | 64bit CPU 2コア、RAM 4GB、SSD空き32GB以上 | Pi 4 / 8GBを候補とする |
| peer + orderer + bridge | 64bit CPU 4コア、RAM 8GB、SSD空き64GB以上 | 今後割り当てる台帳側ホストの配置目安。WebUI同居時は追加の余裕を測る |
| CSI取得 + 証明生成 | 64bit CPU 4コア、RAM 16GB、SSD空き100GB以上 | GMKtecは初期試験の候補。取得との同時稼働は未検証。RAM32GBなら余裕を持たせやすい |

Pi 4には64bit OSと有線LANを使用する。台帳の継続書き込み先はSSDを推奨する。Fabric 2.5.16 peer/ordererの配布マニフェストに`linux/arm64`と`linux/amd64`があることを確認した。Piでのこのチェーンコードの動作・性能は未測定。32bit OSのままではこの配備構成を使えない。OS再インストールやCSI機の設定変更は自動では行わない。

## 利用者にお願いする最初の作業

1. GMKtec・Pi・割り当てる台帳側ホストを、可能なら同じ有線LANへ接続する。MacにWebUIを置く検証期間は、MacからGMKtecへ接続できるようにする。ルーターのDHCP予約などでIPを固定する。Fabric用ポートをインターネットへ転送しない。
2. GMKtecのOS・RAMはSSHで確認済み。PiのOSが64bitか、SSDがあるかと、台帳側ホストに割り当てられる機器を確認する。Mac/Linuxならこのリポジトリで`bash scripts/staging/host-info.sh`を実行すれば、CPU・RAM・空き容量・Docker情報が表示される。Windowsなら「設定 → システム → バージョン情報」とディスク空き容量を確認する。
3. GMKtecは`ssh infonetworking@100.111.253.60`で接続確認済み。Piと台帳側ホストへのSSH接続先を確認する。こちらへ伝えるのはLAN IPまたはSSH設定名・ユーザー名まで。パスワード・秘密鍵はチャットに貼らない。
4. 下記2つの専用アドレスにSepoliaの**テストETH**を用意する。2026-11-24の読み取り確認では、どちらも0だった。メインネットETHは不要。

| 用途 | アドレス |
| --- | --- |
| コントラクト配備 | `0xec77D2B256e1c9079CbA30869ca74bBFBb28C32f` |
| 証明記録 | `0xbe0EEc5d93231938Cf743a792516fbb103B48651` |

[Ethereum公式のネットワーク・faucet案内](https://ethereum.org/developers/docs/networks/#sepolia)を参照。残高確認だけなら以下を実行する（秘密鍵の読み取り・送金なし）。残高ゼロは終了コード2。残高があることと必要gas費用を満たすことは別であり、配備時に費用上限を再確認する。

```bash
node backend/contracts/scripts/check-staging.mjs
```

公開ドメインは今すぐ必要ない。まずLANの`csi.home.arpa`などをLAN DNSでWebUIを配備するホストのIPへ向け、内部CAのHTTPSで利用する。ブラウザーを使うPCにそのCA証明書を信頼登録する必要がある。外部公開時は管理可能なドメインと到達経路を用意し、公開CAのHTTPS設定へ切り替える。大学・研究室回線のポート開放や外部公開が許可されているかは管理者に確認する。

## 配備作業の順番（実機情報確定後に進める部分）

以下は管理者向けの具体的手順。利用者が今すぐ全てを手作業で行う必要はない。各ホストのIP・OSが分かれば、配置に合わせて設定する。

### 1. 基盤と名前解決

LinuxではDocker Engine + Compose、Node.js 22、Fabric 2.5.16 CLI（`peer`、`configtxgen`、`osnadmin`）、`jq`を使用する。Mac上のDocker Desktopと既存開発環境は、本番移行までWebUI・証明コードの検証に使用する。Linux ARM64にはARM64版CLIを使用する。

`deploy/staging/inventory.example.json`をGit対象外の`.local/distributed/inventory.json`へコピーし、組織名、ホストID、実際に解決できるDNS名へ変更する。例の`.invalid`は意図的に配備スクリプトが拒否する。ordererを置く3ホストのhostIdはそれぞれ別にする。配備先が確定するまでGMKtec・Mac・Piを台帳ノードとして自動登録しない。

DNS名はブラウザーだけでなく**各コンテナからも**解決できる必要がある。開発機の`/etc/hosts`を変更しただけでは他ホストやコンテナに伝わらない。LAN DNSの登録を基本とし、証明書のSANにも同じDNS名を入れる。

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

実サーバーの配置・証明書発行・実配備、Linux版proverによる実CSIの証明生成、Piでの起動と継続稼働、バックアップ復元、障害試験はまだ完了していない。workerメモリ上限12GiBは仮設定で、GMKtecのCSI取得・OS用メモリを残せるよう実測して調整する。PicoScenes稼働中に検証なしで重い証明ジョブを自動起動しない。

台帳・Postgres・観測SQLite・CAのバックアップは別々に管理する。SQLiteはworker停止＋SQLite backup APIなど整合性の取れる方法を使い、稼働中のdbファイル単独コピーは避ける。peerのDocker socketはそのホストの強い権限に相当するため、参加組織の管理者だけが操作できる専用実行環境とする。API/workerにはDocker socketを渡さない。

## 根拠となる公式資料

- [Fabric production deployment guide](https://hyperledger-fabric.readthedocs.io/en/release-2.5/deployment_guide_overview.html)：組織別CA・peer・ordererの配備計画。
- [Channel participation](https://hyperledger-fabric.readthedocs.io/en/release-2.5/create_channel/create_channel_participation.html)：system channelなしのchannel作成・参加。
- [Fabric 2.5 architectures](https://hyperledger-fabric.readthedocs.io/en/release-2.5/whatsnew.html)：amd64 / arm64。
- [Ethereum networks](https://ethereum.org/developers/docs/networks/)：アプリ開発用Sepolia。
