# Mac・GMKtec・Pi 4で進めるFabric実証ネットワーク

**2026-11-27更新：Piは後回しとなり、[Mac・GMKtecの2ホスト構成](fabric-two-host-setup.md)で実配備・記録検証を完了。以下は11月25日時点の準備記録と、将来のPi追加に向けた手順。GMKtecのDocker / Compose導入は完了済みのため、下記インストーラーを再実行しない。**

2026-11-25。**実機への配備準備中。3ホストFabricネットワークの起動・channel参加・分散検証はまだ完了していない。** Macの既存ローカルFabricでの成功とは区別する。

## 今回の配置

| 機器 | 役割 | 確認状況 |
| --- | --- | --- |
| GMKtec（Ubuntu 22.04、RAM約16GB） | HospitalMSPのpeer・writer bridge、orderer 1。既存CSI取得を継続 | SSH接続可。Docker未導入。PicoScenes稼働中 |
| Mac（現在の開発機） | ResearchMSPのpeer・reader bridge、orderer 2。WebUI・API・証明生成を当面継続 | Docker 28.4.0 / Compose 2.39.4。新ポートのbind確認済み |
| Raspberry Pi 4（RAM8GB） | orderer 3 | ユーザー回答：OS未書込、SSDなし |

3 ordererは3台の実ホストへ分ける。同一所有者が管理する2組織の模擬実証で、独立した組織による運用の実証とは異なる。Raftは3台中2台の稼働でordererの合意を維持する。今回の書込承認は両組織peerを必要とするため、peerが1台停止すると新規記録は止まる。[Fabric公式の3 orderer構成](https://hyperledger-fabric.readthedocs.io/en/release-2.5/create_channel/create_channel_participation.html)

証明生成をPiへ移さない。GMKtecへの新回路の証明生成移行は、CSI取得と同居した場合の負荷を確認する別工程とする。まずMacで作成した実証明を分散Fabricへ記録・検証する。

## ユーザー側の作業1：GMKtecへDockerを導入

SSHではsudoの非対話実行ができなかったため、管理者パスワードの入力だけは利用者の端末で行う。パスワードをチャットへ送る必要はない。専用スクリプトはGMKtecへ転送済み。

Macのターミナルで実行する：

```bash
ssh infonetworking@100.111.253.60
sudo bash ~/csi-fabric-bootstrap-20261125/install-docker-ubuntu.sh --install
exit
```

再接続してDocker実行権限を反映する：

```bash
ssh infonetworking@100.111.253.60
docker info --format '{{.ServerVersion}}'
docker compose version
```

スクリプトは[Docker公式Ubuntu APT手順](https://docs.docker.com/engine/install/ubuntu/)に基づき、Engine・CLI・Compose・Buildxを導入してサービスを起動する。実行したsudoユーザーをDockerグループへ追加する（ホスト管理に相当する権限）。既存の競合パッケージや別のDocker APT設定があれば停止し、勝手に削除しない。OS更新全体、再起動、PicoScenesの停止、CSI設定変更は行わない。Docker導入自体はネットワーク・firewall構成を追加するため、計測に余裕のある時間に実施し、完了後にCSI取得の継続を確認する。

実際のインストールは未実行。GMKtecで `--check` によるOS・アーキテクチャ・Docker有無の確認だけを実施済み。導入成功後、こちらで再接続して配備前チェックを再実行する。

## ユーザー側の作業2：PiへOSを書き込む

準備するもの：Pi 4 / 8GB、適合する電源、有線LANケーブル、microSDとカードリーダー。今回の試験用容量目安は32GB以上、余裕を持たせるなら64GB以上。これはFabricの性能保証値ではない。

1. Macへ [Raspberry Pi Imager](https://www.raspberrypi.com/software/) を入れる。
2. 機種にRaspberry Pi 4を選び、OSは **Ubuntu Server 24.04 LTS（64-bit、Raspberry Pi用）** を選ぶ。GUIは不要。見つからなければ、[Ubuntu公式配布一覧](https://cdimage.ubuntu.com/releases/24.04/release/)の **Raspberry Pi Generic (64-bit ARM) preinstalled server image** を取得し、Imagerのカスタムイメージとして指定する。通常のARM64 server ISOではなく、Pi用のpreinstalled imageを使う。
3. 書込先にmicroSDを選ぶ。**選択したmicroSDの内容は消去されるため、Macの内蔵ディスクや別の外付けドライブを選ばない。**
4. OSのカスタマイズで、ホスト名を `csi-orderer-pi`、ログインユーザー名を自分で決め、SSHを有効にする。カスタマイズが利用できないイメージの場合は、初回起動時のコンソールでユーザーとSSHを設定する。
5. 書込後、PiにmicroSD・有線LAN・電源を接続する。最初はMacからアクセスできる同じLANに置く。
6. ルーターの接続機器一覧などでPiのIPアドレスを調べ、MacからSSH接続する。

```bash
ssh <設定したユーザー名>@<PiのIPアドレス>
uname -m
cat /etc/os-release
df -h /
```

`uname -m` が `aarch64` なら64bit ARM。接続できたら、**IPアドレスとユーザー名**をこちらへ伝える。公開鍵の登録が必要なら、その時点で公開鍵の設定を案内する。秘密鍵やパスワードを共有しない。

ImagerでOSを書き込む方法とmicroSDからの起動は[Pi公式手順](https://www.raspberrypi.com/documentation/computers/getting-started.html)に沿う。SSDがなくても小規模な初期起動・疎通確認は進められるが、継続運用や代表的な性能比較にはSSDへの移行を勧める。microSDで測った結果は、その記憶媒体を明記して報告する。

## こちらで進める配備工程

1. PiのSSH接続・64bit OS・ストレージを確認。Dockerを用意し、必要なら既存のTailscaleネットワークへ参加させる。Tailscaleのアカウント認証はユーザー自身のブラウザーで行う。
2. 3台間の実通信と、DockerコンテナからのDNS解決を確認。現時点ではMac/GMKtecのホストIPへのbind、MacのDockerコンテナからGMKtecのDNS解決・SSHポートへの疎通、GMKtecからMacのDNS解決まで確認済み。Fabricの各ポート・Piとの通信は未確認。
3. 2組織＋OrderingMSPの新しいCA/MSP・TLS証明書を用意する。既存ローカルtest-networkの秘密鍵を流用しない。CAは組織別に管理し、Pi名・各ホスト名と一致するSANでTLS証明書を発行する。[Fabric CA公式手順](https://hyperledger-fabric-ca.readthedocs.io/en/latest/deployguide/cadeploy.html)
4. 3台のorderer・2組織peerを起動し、`csi-staging` channelへ参加。
5. Sepoliaと同じ検証鍵を含む `csiadaptive4004` chaincodeを配り、2組織が承認してcommit。
6. writer/reader bridgeとMacのAPI・workerを接続。公開WebUIは閲覧・検証だけを公開し、Fabricノードのポートを一般公開しない。
7. 実CSIのtrue/falseの証明で記録・検証し、Sepoliaと同条件で時間・リソース使用量を計測する。新しいnonceの証明を両台帳へ1回ずつ記録して比較する。以前のチェーンで使った証明の再記録・再利用による重複拒否に注意する。

FabricではFaucetやテストETHは不要。処理時間・CPU/RAM・ストレージ・電力などを測り、gasがないことと運用コストがないことを混同しない。

## 既存環境と分けるポート

| 用途 | 新環境の設定 | 備考 |
| --- | --- | --- |
| peer | `PEER_PORT=17051` | inventoryのpeerPortも同じ値 |
| peer→chaincode | `CHAINCODE_PORT=17052` | peerの専用Docker network内、ホストへ公開しない |
| orderer | `ORDERER_PORT=17050` | inventoryのorderers[].portも同じ値 |
| orderer admin | `ORDERER_ADMIN_PORT=17053` | 管理者向けmTLS |
| reader/writer bridge | `BRIDGE_PORT=18843` | private IP上のHTTPS |
| peer/orderer監視 | `19443` / `19444` | loopbackのみ |

各Composeのプロジェクト名も `-p csi-consortium-peer`、`-p csi-consortium-orderer`、`-p csi-consortium-bridge` に分け、peer用networkは `PEER_NETWORK=csi-consortium-peer-runtime` とする。既存debug用コンテナ・volumeを削除しない。

既定の7051/7050等は後方互換のため維持した。新環境の起動時はポート設定・channel設定・Gateway接続先を必ずそろえる。ポート番号を変えただけでは通信元制限にはならず、Tailscale ACL等で参加ホスト・管理者に限定する。自宅／研究室ルーターで一般向けポート転送は不要。

詳細なchannel参加・chaincode lifecycleは [distributed-staging.md](distributed-staging.md) を参照。そちらの既定ポートの例をそのまま新環境へ適用しない。
