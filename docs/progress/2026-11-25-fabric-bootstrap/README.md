# 3ホストFabricの配備準備（2026-11-25）

**構築準備まで。分散ネットワークの稼働・検証成功はまだ報告していない。**

配置方針：GMKtec＝Hospital peer/writer/orderer 1、Mac＝Research peer/reader/orderer 2、Pi 4 / 8GB＝orderer 3。証明生成・UIは当面Macで継続する。

## 実機で確認したこと

- GMKtecへ `infonetworking@100.111.253.60` で接続できる。Ubuntu 22.04、64bit、RAM約16GB、空き約420GiB。PicoScenes稼働中。
- GMKtecはDocker/Compose未導入。sudoは非対話認証不可。インストールは利用者の端末でsudo認証が必要。
- MacはDocker 28.4.0、Compose 2.39.4。新環境で使用するprivate IPとポートはbind可能。
- Piはユーザー回答でOS未書込・SSDなし。SSH接続先はまだない。
- Macの既存DockerコンテナからGMKtecのTailscale DNS解決とTCP 22への疎通を確認。GMKtecからMacのDNS解決も成功。Fabricポートの相互通信・3台の接続・CA/TLSは未確認。

## 実装・準備

- peer/orderer/admin/bridge/監視ポートをComposeで設定可能にした。既定値は維持。
- channel生成でpeer anchor・orderer endpoint・Raft consenterのポートをinventoryから統一して反映。
- Gateway設定で既定7051以外のDNS:port接続先を受け付け、不正ポートやlocalhost/プレースホルダーを拒否。
- 資格情報やプロセス引数を読まないホスト事前検査 `inspect_fabric_host.py` を追加。
- Docker公式APTに基づく `install-docker-ubuntu.sh` を追加。GMKtecの `~/csi-fabric-bootstrap-20261125/` に転送し、`--check` 成功。実インストールは未実施。
- PiのOS書き込みからSSH接続までの利用者向け手順を作成。
- `.local/fabric-consortium/inventory.pending.json` にMac/GMKtecの実DNS・新ポートを準備。Piは未準備のため意図的に `.invalid` としており、配備validatorは拒否する。実接続確認後に置き換える。

今回の証跡はCLIと設定検査であり、新しいFabric WebUIのスクリーンショットはまだない。既存ローカルFabricの画像を分散環境の証跡として流用しない。

## 確認

- `node --test fabric/test/external-deployment.test.mjs`：4件成功。既定ポートと新ポートのchannel生成、不正入力拒否、既存の公開鍵固定・bridge TLS制限を確認。
- `cd fabric && npm test`：全18件成功。
- Docker Compose 3ファイルの構文・展開確認成功。peer/ordererの公開アドレスと待受ポートの一致を検査。
- Python構文・Black/isort、shell構文確認済み。
- 生データ：`mac-preflight.json`、`gmktec-preflight.json`、`config-checks.json`、`bootstrap-transfer.json`。転送スクリプトはローカルとリモートのSHA256一致確認済み。

利用者に必要な操作と配備工程は [fabric-three-host-setup.md](../../fabric-three-host-setup.md) にまとめた。
