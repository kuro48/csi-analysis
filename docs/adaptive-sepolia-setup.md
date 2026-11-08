# 4,004列のCircom選択版をSepoliaに接続する手順

2026-11-09時点。Sepoliaへの実デプロイ・実測は未実施。RPCのchain ID（11155111）と専用ウォレットの残高ゼロを確認した。

## 利用者の作業

以下の**両方**にSepolia用のテストETHを用意する。メインネットETHを送金する必要はない。

| 用途 | Sepoliaアドレス |
| --- | --- |
| VerifierとRegistryのデプロイ | `0xec77D2B256e1c9079CbA30869ca74bBFBb28C32f` |
| CSI証明の記録トランザクション | `0xbe0EEc5d93231938Cf743a792516fbb103B48651` |

[Ethereum公式のテストネット・faucet案内](https://ethereum.org/developers/docs/networks/#sepolia)からテストETHを取得する。必要量はその時点のgas価格による。デプロイ処理はトランザクションごとに0.05 test ETHの上限を設けているが、これは使用量の見積もりではない。

秘密鍵はこの作業機の `.local/sepolia-adaptive/deployer.key` と `recorder.key` に0600で保存済み。Git対象外。チャットやスクリーンショットに秘密鍵を掲載しない。別端末ではこのファイルは自動的に共有されない。

## 証明鍵の生成が完了した後のデプロイ

リポジトリ直下で実行する。`artifacts.json` と対応する全証明アーティファクトが必要。

```bash
node --env-file-if-exists=.env.sepolia.local backend/contracts/scripts/deploy-adaptive-sepolia.mjs
```

標準RPCは `https://ethereum-sepolia-rpc.publicnode.com`。専用RPCを使う場合は、Git対象外の `.env.sepolia.local` に `ETHEREUM_RPC_URL=...` を設定する。スクリプトはネットワークID・鍵ファイル権限・両ウォレットの残高・アーティファクトSHA256・デプロイ費用上限を確認してから送信する。残高ゼロなら送信前に停止する。成功時は `.local/adaptive-evm/11155111/manifest.json` が生成される。

## APIと記録ワーカー

APIとワーカーの両方で以下を設定して再起動する。既存のlegacy用設定はそのまま使用できる。

```bash
export ADAPTIVE_OBSERVATION_MANIFEST="$PWD/.local/adaptive-evm/11155111/manifest.json"
export ADAPTIVE_ETHEREUM_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com
export ADAPTIVE_ONCHAIN_CONFIRMATIONS=2
export ADAPTIVE_ARTIFACT_MANIFEST="$PWD/.local/circom-adaptive-4004/artifacts.json"
```

ワーカーだけに次を設定する。公開APIに送信鍵を渡さない。

```bash
export ADAPTIVE_RECORDER_KEY_FILE="$PWD/.local/sepolia-adaptive/recorder.key"
```

同じWebUIのCSI送信画面で「4,004列の回路内選択」とEthereum系台帳を選択する。患者一覧画面では、保存済み証明のオンチェーン検証が成功した後にだけ `isNormal` を表示する。公開チェーン上の公開入力は直接読むことができるため、暗号化による閲覧制限ではない。

## 比較測定の扱い

Fabricとの比較には、同じ回路・同じ検証鍵・同じ証明と公開入力を使用する。証明生成、記録確定待ち、検証呼び出しを別々に測り、Sepoliaのgas使用量と実際のtest ETH料金を保存する。ローカルGanacheの時間や料金をSepoliaの実測値として扱わない。Fabricのgasは存在しないが、ノード運用費用はゼロとは限らない。

両台帳の配備後、リポジトリ直下で実行する。証明生成は重いため時間がかかる。各試行に新しいnonceと証明を使い、同じ証明を両台帳へ一度ずつ記録する。

```bash
DEBUG=true ZKP_AUTO_COMPILE=false .venv/bin/python fabric/benchmark/adaptive-fixtures.py \
  sampledata/csi_20260519_114943.csi .local/adaptive-benchmark/fixtures.json \
  --artifacts .local/circom-adaptive-4004/artifacts.json --count 6
ADAPTIVE_ETHEREUM_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com \
  node fabric/benchmark/run.mjs fabric/benchmark/adaptive-config.example.json
```

設定例はウォームアップ1回＋実測5回。JSONの `output` に生データ・集計・HTMLレポートを保存する。再測定には新しい証明バンクと出力ディレクトリを指定する。同じ証明の再利用は両台帳で拒否される。これは実行手順であり、未実施のSepolia測定値を含まない。
