# Mac・GMKtecで稼働するFabric実証ネットワーク

2026-11-27。Piを後回しにする利用者の指示に合わせ、**2台の実機へ配備し、実CSIの保存済み証明を記録・検証した**。旧ローカルtest-networkとは別の証明書、channel、Docker project、volumeを使う。

## 利用する

同じTailscaleネットワークへ接続したPCで、次を開く。

**http://100.110.182.121:8085/patients**

1. 患者 `8ff672b0` を選ぶ。
2. `2026/5/26 3:40:08 JST · Fabric` を選ぶ。
3. 「証明を検証して結果を取得」を押す。成功すると `isNormal: true` を表示する。
4. 患者 `24b55901` の `2026/5/19 11:49:51 JST` は `isNormal: false` の確認用。

表示時刻はブラウザーのタイムゾーンによる。患者は表示用IDで、正常呼吸の正解ラベルを意味しない。どちらも既存の実CSIで作った証明であり、今回合成CSIは使用していない。

HTTPの入口はMacのTailscale IPだけにbindし、Tailscale経路で利用する。一般インターネットへ公開するドメイン・HTTPS入口は今回追加していない。peer、orderer、bridgeはTLS、orderer管理APIは専用CAによるmTLS。第三者画面にはFabric証明書、秘密鍵、bridge tokenを渡さない。

Mac・GMKtec、両方のDockerとTailscaleを起動しておく。Piの準備やテストETHの補充は不要。

## 実配置

| ホスト | コンポーネント | 接続先 |
| --- | --- | --- |
| GMKtec / Ubuntu 22.04 | HospitalMSP peer | `infonetworking-csi.tail2285b4.ts.net:17051` |
| GMKtec | writer HTTPS bridge | 同ホスト `:18843` |
| Mac / Docker Desktop | ResearchMSP peer | `mac-mini.tail2285b4.ts.net:17051` |
| Mac | OrderingMSP / Raft orderer 1台 | 同ホスト `:17050`、管理 `:17053` |
| Mac | reader HTTPS bridge | 同ホスト `:18843` |
| Mac | 閲覧API・WebUI・入口 | loopback `:8015` / `:3015`、Tailscale `:8085` |

Fabric 2.5.16。channel `csi-staging`、chaincode `csiadaptive4004` version 1.0 / sequence 1。

- 書込のendorsement policyは `AND('HospitalMSP.peer','ResearchMSP.peer')`。両peerが必要。
- 閲覧はResearchMSP peerのchaincode内でGroth16検証する。evaluateなので閲覧ごとに新しいブロックを生成せず、両組織の再承認も行わない。
- orderer 1台のためorderer故障許容数は **0**。Mac停止中は新規記録・この閲覧画面とも停止する。
- 同じ利用者が管理する機器上の2組織実証であり、独立した組織管理の実証ではない。
- CSI取得のPicoScenesプロセスは稼働を継続。新しい4004候補回路の証明生成はまだGMKtecへ移していない。取りこぼし・同時負荷は今回未測定。

1 ordererは初期構築に使えるが耐障害構成ではない。[Fabric公式channel participation手順](https://hyperledger-fabric.readthedocs.io/en/release-2.5/create_channel/create_channel_participation.html)

## ファイルと秘密情報の置き場所

MacのGit対象外ディレクトリ：`.local/fabric-consortium/two-host/`

GMKtec：`/home/infonetworking/csi-fabric-consortium/two-host/`

- `research/` と `ordering/` はMacだけに、`hospital/` はGMKtecだけに生成した。
- 各組織にsigning CAとTLS CA、ordererには別のadmin TLS CAがある。秘密鍵・tokenは0600、秘密ディレクトリは0700。
- ホスト間で転送したPKIは `public/` 内の公開MSP・公開TLS証明書だけ。Hospitalのrecorder証明書SHA-256をchaincodeへ固定。
- `bootstrap_fabric_identity.py` はOpenSSLによる**実験用の手動offline issuer**。既存test-networkの鍵を再利用していない。Fabric CAの登録・更新サービスは配備していない。
- leaf証明書は180日、CAは365日。自動更新・失効配布・バックアップ復旧の仕組みは未実装。本番へそのまま持ち込まず、管理CAと運用手順を用意する。recorder証明書更新には固定ハッシュのchaincode更新も必要。

FabricはX.509 CAの証明書を使える。Fabric CAはMSP構造の生成や登録・更新を支援する。[Fabric CA公式ガイド](https://hyperledger-fabric-ca.readthedocs.io/en/latest/deployguide/use_CA.html)

## 再起動

Dockerコンテナは `restart: unless-stopped`。既存volumeを維持する。**`down -v` を実行しない。** MacのAPI/UIは今回の起動時に常駐プロセスとして立ち上げたが、OS再起動後の自動起動登録は行っていない。

MacでDocker DesktopとTailscaleを起動し、リポジトリ直下で実行：

```bash
docker compose -p csi-consortium-orderer --env-file .local/fabric-consortium/two-host/orderer.env -f deploy/staging/compose.orderer.yml up -d
docker compose -p csi-consortium-peer --env-file .local/fabric-consortium/two-host/peer.env -f deploy/staging/compose.peer.yml up -d
docker compose -p csi-consortium-bridge --env-file .local/fabric-consortium/two-host/bridge.env -f deploy/staging/compose.bridge.yml up -d
PRIVATE_BIND_IP=100.110.182.121 docker compose -f deploy/staging/compose.fabric-viewer.yml up -d
```

APIとUIが停止している場合、それぞれ別ターミナルで：

```bash
bash scripts/fabric-consortium-mac.sh api
```

```bash
HOSTNAME=127.0.0.1 PORT=3015 node .local/fabric-consortium/two-host/ui/server.js
```

GMKtecでは次を実行する（Dockerグループ設定は完了済み）：

```bash
ssh infonetworking@100.111.253.60
cd ~/csi-fabric-consortium/two-host
docker compose -p csi-consortium-peer --env-file peer.env -f compose.peer.yml up -d
docker compose -p csi-consortium-bridge --env-file bridge.env -f code/deploy/staging/compose.bridge.yml up -d
```

bridgeのUID/GIDは鍵所有者に合わせる。GMKtecは1000:1000、Macは501:20。0600の鍵をworld-readableにせず、root権限も追加しない。

ログ：Macは `docker logs csi-consortium-peer-peer-1` / `docker logs csi-consortium-bridge-bridge-1`、API/UIは `.local/fabric-consortium/two-host/api.log` / `ui.log`。GMKtecでも同名のコンテナログを確認できる。

## 新しい環境を作る場合

既存ネットワークの再起動時にはこの工程を繰り返さない。新規の空ディレクトリを使う。

1. `deploy/staging/inventory.two-host.example.json` をコピーし、実DNS・ポート・公開recorder証明書パスを設定。`deploymentProfile: "two-host-bootstrap"` を明示する。省略時は従来どおり3ホストRaftの検証を維持する。
2. **各ホストで** `scripts/staging/bootstrap_fabric_identity.py NEW_DIR --msp-id ... --dns ... --bridge-role writer|reader` を実行。ordererは `--node-role orderer` としbridge-roleを付けない。秘密鍵ディレクトリごと転送しない。
3. `public/` だけを統合・交換し、`prepare-external.mjs inventory.json artifacts.json NEW_RELEASE_DIR` で既存のadaptive4004検証鍵を固定する。
4. `render-channel.mjs inventory.json configtx.yaml ABS_PUBLIC_DIR` でホストの公開MSPパスを指定。`configtxgen` でchannel blockを生成し、`osnadmin channel join` と両peerの `peer channel join` を実行する。
5. chaincodeを一度packageし、同じtar.gzを両組織にinstall。両組織がapproveした後にcommitする。管理者鍵は各ホストから動かさない。詳細は [distributed-staging.md](distributed-staging.md) のlifecycle手順。
6. roleごとに `configure-external-gateway.mjs` を実行しHTTPS bridgeを起動。Mac APIはreader tokenだけを持つ。今回のwriter送信はGMKtec側のCLIから実行した。
7. 記録済み証明を閲覧用カタログへ登録するときは `bash scripts/fabric-consortium-mac.sh import --patient-id UUID --capture-id UUID --bundle REAL_PROOF.json --source-csi REAL_CAPTURE.csi`。chaincode検証と記録済みpayloadハッシュの一致を確認してから登録する。新しい書込は行わない。

今回の閲覧APIは書込用workerを起動していない。新CSIを継続収集して自動記録する接続は次工程。証明生成・キューの移行と、このネットワークの配備完了を区別する。

GMKtecではUbuntuの `docker.io` / `docker-compose-v2` を使用。以前転送したDocker公式APT向けインストーラーを重ねて実行しない。APT中に表示されたMATLAB画面は、既存の設定未完了 `matlab-support` によるもの。Docker Composeは導入完了しており、FabricのためにMATLABをインストールする必要はない。MATLAB設定の解決・パッケージ削除は今回行っていない。

## Pi追加時

Piに64bit OS・Docker・Tailscaleを準備し、必要ならSSDを追加する。現在の1 ordererに対してGMKtecとPiへordererを増やすときは、既存channelのconfig更新とTLS証明書交換を行い、consenter変更を1台ずつ完了させる。inventoryだけを書き換えたり、新genesis blockを既存volumeへ上書きしたりしない。3台すべて参加後に3ホストRaftとして障害試験を行う。

スクリーンショット・実測値・制約は [今回の記録](progress/2026-11-27-fabric-two-host/README.md) を参照。
