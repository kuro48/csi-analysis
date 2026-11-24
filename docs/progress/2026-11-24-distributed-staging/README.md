# 分散実証環境への移行準備

**後続の補足あり：本番まではMacでWebUI・検証を継続し、最終的にGMKtecへアプリを集約する。以下は当初の準備記録であり、最新配置は[現行手順](../../distributed-staging.md)を参照。**

2026-11-24。実配備は未実施。追加PCの購入を前提にせず、Mac / GMKtec / Pi 4（8GB）の3台を利用する構成を準備した。[操作・配備手順](../../distributed-staging.md)を参照。

## 実装したもの

- Fabric 2組織・別ホストpeer + 3ホストRaft ordererのCompose設定、公開MSPからのchannel定義生成、組織ごとの承認・commit用スクリプト。
- test-networkのディレクトリ構造に依存しないchaincode梱包。既存のadaptive4004回路・検証鍵を維持する。実在しない例示DNSや同一hostId構成を拒否し、既存releaseへの上書きも拒否する。
- role別Fabric gateway設定、HTTPS bridge、秘密tokenファイル、APIの組織CA検証。APIにwriter秘密鍵・tokenを渡さない構成。
- Linux版ネイティブproverをビルドするアプリイメージ、証明アーティファクトの移送スクリプト、WebUIの公開HTTPS/LAN HTTPS設定。
- Sepoliaの読み取り専用残高確認。比較benchmarkのwriter/readerを別peerへ接続する設定。

既存ローカル環境は停止・変更していない。新しいCircuit/選択方法や新しいCSIは生成していない。ユーザー作成の`output/figures/`と`scripts/plot_subcarrier_selection_error.py`は変更対象外。

## 今回の確認結果

| 確認 | 結果と範囲 |
| --- | --- |
| Fabric Nodeテスト | 17 passed。外部構成の拒否条件、実検証鍵の梱包、非loopback平文bridgeの拒否を含む |
| backend Fabricテスト | 17 passed。CA検証、CA不正時のfail closed、患者・時刻・deployment結合など |
| フロントエンド | lint / type-check成功。UIコード変更なし |
| Compose | peer / orderer / bridge / app / LAN overlayの5構成を検査。サービス起動はしていない |
| channel設定 | Fabric 2.5.16のconfigtxgenが生成設定を受理。試験用公開MSP・TLS証明書を使った構文検査で、ネットワーク参加は行っていない |
| Docker | app / bridgeのLinux amd64イメージを実ビルド。最終build成功 |
| API起動 | 一時コンテナでPUBLIC_MODE=trueの`/health`がhealthy。DB/台帳への接続検証を意味しない |
| 実CSI読み込み | 既存`csi_20260519_114943.csi`をLinuxコンテナで処理し、candidateCount 4004 / timestamps 64を確認 |
| 既存証明 | 保存済み実CSI由来proofをLinuxコンテナのsnarkjsで検証成功。新規証明生成は未実施 |
| アーティファクト移送 | `.local/distributed/portable-artifacts/`に約7.5GiBを書き出し。元のR1CS/WASM/証明鍵/検証鍵のSHA256を確認、コンテナでLinux proverとの結合を確認 |
| ARM64 | Docker配布マニフェストでFabric peer/orderer 2.5.16のarm64/amd64を確認。Pi実機起動は未実施 |
| Sepolia | chainId 11155111へ実RPC接続、両ウォレット0 test ETH。送信なし。[記録](sepolia-readiness.json) |

backendの既存環境ではweb3のpytest自動プラグインが依存関係エラーになるため、今回の同期unitテストは以下で実行した。既存pytest.iniのcoverage引数も外しており、全体カバレッジ検査を通したという意味ではない。

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 DEBUG=true ZKP_AUTO_COMPILE=false PYTHONPATH=backend \
  .venv/bin/python -m pytest -o addopts='' backend/tests/unit/test_fabric_observations.py -q
python3 scripts/staging/validate_config.py
cd fabric && npm test
```

ビルド中に不足するビルド依存とRust最低バージョンを修正し、最終イメージで再検査した。Dockerのsnapshot cacheエラーはbridgeのno-cache再ビルドで解消。稼働中の既存コンテナの再起動・volume削除はしていない。

## 次に必要なもの

GMKtecのOS/RAM、Piの64bit OS/SSD、有線LANと固定IP、SSH接続先が必要。各組織CAを発行してからFabricへ配備する。Sepoliaは2つの専用ウォレットへのテストETH補充が必要。ドメインは未取得でもLAN HTTPSから開始できる。

本資料の時間・成功件数は配備準備の検査結果である。分散FabricやSepoliaの記録時間・検証時間の新しい測定値はまだない。
