# 既存CSI・4,004列のCircom内選択

## 変更点

- 既存の `sampledata/csi_20260519_114943.csi` を使用。追加収集は不要。
- 既存parserが同じCSI形式として読み取った150フレームから時刻方向に64点を整形し、**4,004列は間引かず**Circomへ渡す。Pythonはバイナリ読み取り・時刻整形・共通スケールでの量子化だけを担当する。
- 各列の電力変動、相対変動量、滑らかさをCircom内で評価し、最大スコアの列を選択。その列だけをLomb–Scargleへ渡す。低電力・変動なし・極端なスパイクを除外。同点は小さい列番号を採用。
- 選択に負けた列を含む、整形後の全64×4,004 I/Q入力をコミットメントに束縛。CSIの元ファイル全150フレームを証明するものではない。
- 既存WebUIの `/capture` に方式選択を追加。`legacy` と `adaptive4004` をジョブに固定し、別の検証鍵・コントラクト・Fabric chaincodeに送る。既存のデバッグ用アップロードと旧方式を保持。
- 第三者の `/patients` は患者・計測時刻の選択だけ。APIが保存済み証明をチェーン上で検証できた場合のみ `isNormal` を返す。未記録・未確定・接続障害・証明不正では結果を表示しない。
- 70公開信号のプロトコルをEVM/Fabricで共通化し、比較測定用の実CSI証明バンク生成にも対応。

## 実測と確認範囲

全4,004列の実CSIからGroth16証明を生成し、ローカルEVMとFabricに記録して検証に成功した。
両台帳とも、WebUIでの実CSI送信→ワーカーでの証明生成→記録→第三者画面での検証・結果表示まで確認済み。
初期の64候補合成データの証明とは別の検証鍵を使用している。

| 項目 | 確認結果 |
| --- | --- |
| 実CSI入力 | 150フレーム、4,004列、64時刻・53.217秒へ整形 |
| 回路規模 | 14,530,543制約、13,981,543 wires、70公開信号 |
| コンパイル | 846.82秒、約13.4 GB peak footprint |
| Circom WASM witness | 19.618秒 |
| 元R1CSの全制約検査 | 成功、170.487秒 |
| 初回snarkjs setup | V8 12 GiB heap上限で失敗、約25.7 GB peak footprint |
| ネイティブsetup | 成功、288.968秒（ハッシュ作成込み308.19秒）、最大RSS 10.06 GB |
| WebUI→workerでの実証明 | 成功。前処理0.356秒、アーティファクト確認19.113秒、witness 20.028秒、native prove 595.730秒、独立snarkjs検証0.315秒 |
| 証明処理の合計 | 635.187秒（約10分35秒、前処理は別計測） |
| ローカルEVM | chain ID 1337、記録成功・検証成功、第三者WebUIで `isNormal=false` 表示 |
| Fabric | 同じ証明での台帳検証に加え、独立したWebUI送信ジョブでも生成・記録・第三者画面での検証成功。`isNormal=false` |
| Fabric向けWebUIジョブの証明時間 | 614.762秒（前処理0.370秒を除く）。EVM向けとは別のnonceで生成 |
| 旧64候補回路への影響 | コンパイル後R1CSのSHA256が変更前と完全一致 |
| Sepolia | RPC/chain ID確認済み。両ウォレット残高ゼロ、未配備・未測定 |

Circomのwitness上では選択列721、`isNormal=0`。旧8列間引き版は元列2859、`isNormal=0`。
列番号は0始まりで、PicoScenesの列にはアンテナ対も含まれる。物理的なトーン番号と同一視しない。
両者の判定が一致した1サンプルであり、選択精度や臨床的な正確性を示す評価ではない。
全候補の評価・範囲制約・コミットメントには大きな計算量が必要で、旧方式より総証明コストが小さいとは主張しない。

### 台帳の動作確認値（各1回）

| 項目 | Fabric | ローカルEVM | Sepolia |
| --- | --- | --- | --- |
| 保存済み証明の検証 | 成功 | 成功 | 未実施 |
| 記録確定まで | 2,207.93 ms | ワーカー内の時間は未計測 | 未計測 |
| 検証照会 | 575.01 ms | 855.16 ms | 未計測 |
| 記録gas | gas制度なし | 1,823,250 gas | 未計測 |
| 記録手数料 | ネイティブ取引手数料なし | 0.0024958993361445 local test ETH | 未計測 |

これは負荷のある開発機での単発動作確認。検証照会は別時点・別クライアントで計測しており、速度の優劣や本番料金を示す比較ではない。
Fabricのノード運用費用、EVMのインフラ費用、証明生成サーバー費用は含めていない。
正式な同条件・複数回のFabric/Sepolia比較は[設定手順](../../adaptive-sepolia-setup.md)の新しい証明バンクで実行する。

- [Fabricの生データ・集計](fabric-smoke-summary.json) / [HTMLレポート](fabric-smoke-report.html)
- [ローカルEVMの実receipt・照会時間](evm-smoke.json)
- [公開証明・70公開信号・証明時間](evm-proof-bundle.json)
- [両WebUIジョブの実行結果](end-to-end-jobs.json) / [第三者APIの実応答](ui-verification.json) / [Fabric向けジョブの公開証明](fabric-proof-bundle.json)
- [検証鍵](verification_key.json) / [アーティファクトSHA256](artifact-hashes.json)
- [実台帳での改ざん拒否](full-pool-negative-controls.json): EVMでは公開信号0/1/2/5/69の改ざんを拒否。Fabricでは判定値を改ざんした証明を別のテスト記録として保存し、正常なreader接続と記録存在を確認した上で `Invalid proof` による取得拒否を確認。

## コードの場所

| 処理 | 実装 |
| --- | --- |
| 4,004列main | `zkp/circuits/csi_lomb_scargle_adaptive_4004.circom` |
| 回路内の評価・選択・全候補コミット | `zkp/circuits/csi_motion_selector.circom` |
| 全列入力の整形 | `backend/app/services/adaptive_csi_input.py` |
| ネイティブGroth16 | `zkp/native-prover/` |
| 鍵固定・witness・証明・独立検証 | `zkp/scripts/prove_adaptive_capture.cjs` |
| キューと証明生成 | `backend/app/services/adaptive_observation.py`, `observation_worker.py` |
| 方式と検証鍵の固定 | `backend/app/services/observation_protocol.py` |
| EVM記録・検証 | `backend/contracts/AdaptiveBreathingObservationRegistry.sol` |
| Fabric記録・検証 | `fabric/chaincode/lib/observations.js`, `proof.js` |
| UI | `frontend/app/capture/page.tsx`, `frontend/app/patients/PatientResults.tsx` |
| 実CSI比較バンク | `fabric/benchmark/adaptive-fixtures.py`, `run.mjs` |

## スクリーンショット

- [既存CSIをFabric向けに送信](capture-fabric.png)
- [既存CSIをローカルEVM向けに送信](capture-evm.png)
- [EVMの検証前（結果なし）](before-verify-evm.png)
- [EVMの検証成功・PC](verified-evm.png) / [スマートフォン](verified-evm-mobile.png)
- [Fabricの検証前（結果なし）](before-verify-fabric.png)
- [Fabricの検証成功・PC](verified-fabric.png) / [スマートフォン](verified-fabric-mobile.png)
- [Fabric実台帳での単発測定レポート](fabric-measurement.png)
- [Circom内の選択コード](code-selection.png)
- [EVMの検証後出力コード](code-verification.png)

`frontend/scripts/capture-adaptive-progress.mjs` で実際のWebUIを操作して撮影する。API応答を差し替えるモックは使用しない。
コード画像は実際のソースファイルから抜粋。秘密鍵・トークンは画像にもGitにも含めない。

## テスト

- Backend: 183 passed。
- Fabric: 11 passed。70公開信号の実Groth16 fixtureと改ざん拒否を含む。
- EVM contracts: 5 passed。70公開信号用Registryの実検証、権限、重複、不正証明を含む。
- Rust native: 2 passed。元R1CS制約の評価、不正witness・不正バイナリ・非正規field値・改ざん公開出力を拒否。
- 独立互換性確認: nativeで生成した64候補の証明をsnarkjsで検証成功、公開出力改ざんを拒否。
- Frontend: lint/type-check成功、17 unit tests passed。UI方式送信テストと、検証失敗時に以前の結果を消すテストも成功。
- 65候補のCircomテストで16列ごとの部分和と末尾グループを確認。旧64候補のR1CSハッシュ一致も確認。

上記の小さいfixtureによるテストは全4,004列の実証明の代わりにはしない。実データのチェーン結果は上記JSON・スクリーンショットとして別に記録した。

## 起動・再現

この作業機の証明アーティファクトは `.local/circom-adaptive-4004/artifacts.json` で固定。
実行確認URLは `http://127.0.0.1:3011/capture` と `/patients`（APIは8011）。既存Next.jsアプリの同じ画面に統合している。
公開中のDocker frontend（3000番）や公開ドメインへの再配備は今回行っていない。
確認用のSQLiteキューは `.local/circom-adaptive-4004/observations`。既存の患者・計測DBは移動も削除もしていない。
既存DBを使う場合は `OBSERVATION_DATA_DIR` とlegacy用manifest/RPCを元の設定に合わせる。追加列 `proof_profile` は自動移行し、既存行は `legacy` になる。
数GBの鍵・元CSI・秘密鍵・トークンはGitに含めない。他の端末でGit pullだけをしても証明アーティファクトは揃わない。
同じ検証先を使うにはアーティファクトを別途配布する。新しく鍵生成する場合は両台帳も新しい鍵で配備する。

```bash
# 全列入力の整形
.venv/bin/python zkp/scripts/prepare_adaptive_csi.py --help
# ネイティブ鍵生成・証明器の手順
cat zkp/native-prover/README.md
# 新しい鍵でFabricを初回配備（既存test-networkを利用）
FABRIC_VKEY="$PWD/.local/circom-adaptive-4004/native/verification_key.json" \
  bash fabric/scripts/deploy-adaptive.sh
# 各プロセスを別ターミナルで起動
FABRIC_WORK_DIR="$PWD/.local/fabric-adaptive" FABRIC_BRIDGE_PORT=8811 bash fabric/scripts/bridge.sh reader
FABRIC_WORK_DIR="$PWD/.local/fabric-adaptive" FABRIC_BRIDGE_PORT=8812 bash fabric/scripts/bridge.sh writer
bash scripts/adaptive-observation-app.sh api
bash scripts/adaptive-observation-app.sh worker
cd frontend
NEXT_PUBLIC_API_URL=http://127.0.0.1:8011 npm run dev -- --port 3011
```

収集端末は既存の `scripts/capture_observation.py` に `CSI_PROOF_PROFILE=adaptive4004` を設定すれば同じ処理へ送信できる。
収集画面の運用者トークンは `.local/circom-adaptive-4004/operator.token` をこの端末で確認して設定する。第三者の患者一覧・検証画面はトークン不要。
方式の省略時は従来互換の `legacy`。4,004列を超える入力や64点未満の有効時刻は拒否する。

Fabric配備時、既存Org1 Peerのorderer接続が切れ、1時間の再接続待ちだったため、そのPeerのみ再起動して台帳同期を回復した。
初回approveはタイムアウトしていたが確定済みだったので、`FABRIC_RESUME=true` で既存承認を確認し、未実施の承認・commitだけを再開した。
既存の `csiobservations` を上書きせず、新しい `csiadaptive4004` を追加した。

## 運用上の条件

ネイティブ版はOS乱数による**単独・テストネット用trusted setup**。取得済みPowers of Tauを使うMPC方式ではない。
本番運用には回路・セットアップ手順の独立レビューが必要。公開信号には選択列などのデバッグ情報が含まれるため、それを非公開にする本番回路は別途作成・配備する。

患者と絶対時刻は記録者のメタデータであり、Circomが患者本人・センサーの真正性を証明するものではない。
今回のUI送信では指定期間を60秒としたが、回路に渡したCSIの最初と最後の時刻差は53.217秒。指定期間と実際のサンプル時刻範囲は区別する。
選択は振幅変動のヒューリスティックであり、呼吸・大きな体動・環境ノイズの識別性能は未評価。
Sepoliaの利用者側作業は[テストETHの準備](../../adaptive-sepolia-setup.md)を参照。
