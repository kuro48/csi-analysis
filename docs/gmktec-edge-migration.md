# GMKtecへの証明生成移行

2026-11-24。本番まではMacでWebUI・証明コードの検証を続け、段階的にGMKtecへ集約する。次の構成は「WebUIだけMac、API・証明worker・キューはGMKtec」。本番前にはWebUIもGMKtecへ移す。SSH確認と接続設定の準備までで、新回路の実移行・サービス切替はまだ行っていない。

## 接続・確認結果

```bash
ssh infonetworking@100.111.253.60
```

表示名として共有された`InfoNetworking`に対し、SSH認証が成功したLinuxユーザー名は小文字の`infonetworking`。既存known_hostsのホスト鍵検査と公開鍵認証を使い、パスワードやホスト鍵設定は変更していない。

- Ubuntu 22.04.5 LTS / x86_64、Core i5-12450H（8コア12スレッド）、RAM約16GB、swap 2GiB。
- SSD空き約420GiB。数値は確認時点のもの。
- PicoScenesプロセスが稼働中。停止・再起動・計測設定変更・CSIファイル読み取りはしていない。
- `/home/infonetworking/csi-zkp`に既存環境がある。専用Python 3.11.14、Node.js 22.23.3、NumPy 1.26.4、SciPy 1.15.3、picoscenes 0.1.0を確認。
- `packages/lomb_scargle_e2e`が存在する。[既存配備記録](../zkp/experiments/edge-setup/2026-10-19/findings.json)では64観測×8系列の旧版。新しい4,004候補回路をGMKtecで検証済みという意味ではない。
- ログイン時のPATH上にDockerは見つからなかった。Dockerのインストールは行っていない。

今回の[機器確認JSON](progress/2026-11-24-gmktec-role-correction/host-inventory.json)を保存済み。再確認は開発機から次で行える。スクリプトはSSHの標準入力から実行し、GMKtecへファイルを配置しない。

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes \
  infonetworking@100.111.253.60 python3 - < scripts/staging/inspect_edge.py
```

## 最終的な処理の担当

1. GMKtec：PicoScenesで取得。収録が完了した計測窓をローカルキューに登録する。
2. GMKtec：既存前処理を適用し、Circom内でサブキャリアを選択してwitness・証明を生成する。
3. GMKtecの記録クライアント：完成した証明・公開入力・観測メタデータをSepoliaまたはFabricへ送信し、結果を永続化する。
4. 第三者用API：患者・計測時刻から記録を参照し、台帳側での検証成功後に`isNormal`を返す。分離検証ではAPIをGMKtec、WebUIをMacに置き、最終的にはWebUIもGMKtecへ移す。

CSI収録と証明生成は別プロセスで並行する。次の窓を収録しながら前の窓を証明する想定であり、証明生成が窓の到着速度に追いつくかは未測定。キュー上限・再試行・計測ファイルの確定検出・原本保持を実装・検査してから自動連携する。

## 移行するもの

| 対象 | 扱い |
| --- | --- |
| 前処理・証明runner・記録クライアント | ソースと依存バージョンを固定してGMKtecへ配置 |
| Circomソース・Cargo.lock等 | 再現・将来更新用としてGMKtecにも保持 |
| R1CS、WASM、witness計算JS、proving key、verification key | 準備済み約7.5GiBのportable-artifactsを移送し、SHA256照合。鍵再生成は不要 |
| ネイティブprover | GMKtecのUbuntuに適合するものをビルド・検証。Macバイナリやコンテナ内バイナリをそのままホストで実行できるとは扱わない |
| deployment manifest・公開CA証明書 | 接続先の実配備後に移送・固定 |
| 記録用秘密鍵／writer認証情報 | 実運用切替時に必要なものだけをGMKtecの専用権限付き領域へ配置。チャット・Gitには含めない |

既存`csi-zkp`の環境を上書きせず、例えば`packages/adaptive4004-v1/`のような新releaseを用意する。新しいユーザー領域環境で依存・Linux ABI・実CSIの前処理・保存済み証明の検証を確認した後、新規証明生成を試す。現行のportable manifestはコンテナの`/artifacts`を参照するため、ネイティブ配備ではパスの再配置も必要。

## WebUIだけMacに置く検証手順

この構成ではAPIとworkerはGMKtec内の同じキューを利用する。WebUIはHTTP経由でAPIに接続するだけなので、SQLite同期やリモートジョブ配送の新実装は不要。以下はDocker・回路アーティファクト・台帳manifest・認証情報を準備した後の手順であり、実際にはまだ起動していない。

GMKtecでAPI・worker・DBだけを起動する。既存のCSI計測・開発UIは先に停止しない。

```bash
# GMKtec上、リポジトリ直下
# api.envのALLOWED_ORIGINSには検証用 http://127.0.0.1:3001 を明示する。
# Compose全体の変数はapp.env.exampleを元に設定済みとする。
docker compose --env-file /srv/csi/config/compose.env \
  -f deploy/staging/compose.app.yml -f deploy/staging/compose.edge-api.yml \
  up --build -d backend worker postgres
```

開発用APIはGMKtecの`127.0.0.1:8000`にだけ公開する。Macでは別ターミナルでSSHトンネルを開く。`18000`が使用中なら別のローカルポートに変更する。

```bash
# Mac上
ssh -N -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=yes \
  -L 127.0.0.1:18000:127.0.0.1:8000 infonetworking@100.111.253.60
```

MacのNext.jsは既存のAPI rewriteを利用する。`NEXT_PUBLIC_API_URL`は空文字にしてブラウザーからは同じオリジンの`/api/v2/...`を使う。既存devサーバーとビルド出力を共有しないよう、別worktreeからポート3001で起動する。ポートだけ変えて同じディレクトリで二重起動しない。

```bash
# Mac上、別ターミナル。リポジトリ直下から初回だけworktreeを作成する。
git worktree add --detach .local/webui-edge-check HEAD
cd .local/webui-edge-check/frontend
npm ci
NEXT_PUBLIC_API_URL= API_INTERNAL_URL=http://127.0.0.1:18000 \
  npm run dev -- --hostname 127.0.0.1 --port 3001
```

ブラウザーは`http://127.0.0.1:3001`へアクセスする。これらはSSH認証を利用した開発用接続であり、インターネット公開用の設定ではない。APIの操作権限は既存のoperator token等のルールを維持する。Next.jsのrewrite設定は起動・ビルド時に解決されるため、API接続先を変えたらdevサーバーを再起動し、production buildでは再ビルドする。

最終的にWebUIもGMKtecに配置するときは、`compose.app.yml`のfrontend/gateway/TLSを使用する。開発用`compose.edge-api.yml`は外し、公開ポートをHTTPS側にまとめる。公開CAまたは内部CAの設定は[配備手順](distributed-staging.md)を参照。

### APIまで別端末にする場合だけ必要な追加作業

APIをMac等へ残したままworkerだけをGMKtecへ移す場合は、リモートジョブ受け渡し・観測一覧同期・通信断時の再試行を別途実装する。今回の「WebUIだけMac」の必須条件ではない。SQLiteのNFS共有は使用しない。

## 次の実機試験

まず保存済みの実CSIを使い、1ジョブの証明生成時間、最大RSS、swap、CPU使用率を測る。次に実収録と並行した際のフレーム数・欠落・キュー滞留を比較する。合成CSIは使わない。16GBで足りるかは、この同時稼働試験で判断する。

本番前の最終確認ではMacへのRPC・ファイル参照・署名・API依存が残っていないことを調べ、Macがオフラインでも取得→証明→記録→第三者検証が完了することを確かめる。
