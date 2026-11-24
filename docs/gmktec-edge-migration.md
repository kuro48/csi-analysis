# GMKtecへの証明生成移行

2026-11-24。GMKtecがCSI取得と証明生成を担当し、このMacを常時運用から外す方針。今回実施したのはSSHによる読み取り確認と配置・手順の訂正であり、新しい証明コードの転送やサービス切替はまだ行っていない。

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
4. 第三者用API：患者・計測時刻から記録を参照し、台帳側での検証成功後に`isNormal`を返す。WebUI/APIの最終配備ホストは未確定。

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

## 現行コードから追加で必要な実装

現在の`compose.app.yml`はAPIとworkerが同一ホストのSQLiteを共有する。同じセットをGMKtecに配置する移行途中の形には使えるが、workerだけのリモート移動には使えない。

GMKtecと第三者用APIを分離する段階では、以下を実装する。

- GMKtec内の取り込み・証明・記録キューと、完了済みファイルだけを取り込む処理。
- 観測ID、患者参照、時刻、proof digest、deployment ID、transaction IDを結合した記録通知と一覧同期。
- 通知を信頼済み判定として扱わず、第三者用APIが台帳上の証明を検証する経路。
- 通信断・再起動・二重送信を想定した永続化と冪等性。

NFSでSQLiteを共有する方法には置き換えない。現時点ではこの分離を実装済み・動作確認済みとはしていない。

## 次の実機試験

まず保存済みの実CSIを使い、1ジョブの証明生成時間、最大RSS、swap、CPU使用率を測る。次に実収録と並行した際のフレーム数・欠落・キュー滞留を比較する。合成CSIは使わない。16GBで足りるかは、この同時稼働試験で判断する。

最終確認ではMacへのRPC・ファイル参照・署名・API依存が残っていないことを調べ、Macがオフラインでも取得→証明→記録→第三者検証が完了することを確かめる。
