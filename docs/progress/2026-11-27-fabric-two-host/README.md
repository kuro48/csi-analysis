# 2026-11-27：GMKtec・Macの2ホストFabric配備

Piの準備を待たず、実機2台へFabric 2.5.16を配備した。実CSIの保存済みGroth16証明2件をGMKtecから記録し、MacのResearch peer内で検証した。患者選択WebUIからもtrue/falseを表示できる。

閲覧先：**http://100.110.182.121:8085/patients**（同じTailscaleネットワークに参加したPC）。GMKtecからMacの画面・APIへアクセスし、trueの検証成功を確認済み。一般インターネット向け公開URLは今回発行していない。

## 配置と確認した事実

| 項目 | 結果 |
| --- | --- |
| GMKtec | HospitalMSP peer、writer HTTPS bridge。既存PicoScenesの稼働継続 |
| Mac | ResearchMSP peer、reader HTTPS bridge、OrderingMSPのorderer 1台、API、WebUI |
| 書込承認 | 両組織peerのAND。block 4の実トランザクションからHospitalMSP・ResearchMSPの2署名者を確認 |
| 台帳同期 | 両peerのheight 7、current/previous block hashが一致 |
| 検証 | chaincode内のsnarkjs Groth16 pairing検証。閲覧evaluateは新規ブロックを生成しない |
| 改変拒否 | true実証明のpublicSignals[1]だけを0へ変更した確認用記録は閲覧検証でHTTP 503、isNormalを返さない |
| 公開入口の制限 | 患者作成POSTは403、CSIアップロードと/capture画面は404 |
| 画面 | 検証前に判定を表示せず、成功後のみ表示。390px幅の横はみ出しなし |

記録metadataからはisNormal・proof・publicSignalsを返さないことも実機で確認した：[metadata応答](metadata-response.json)。

証拠：[endorsements](record-endorsements.json)、[Mac台帳](mac-ledger.txt)、[GMKtec台帳](gmktec-ledger.txt)、[別PCからのHTTP確認](gmktec-viewer-check.json)、[改変の拒否](tampered-verify.json)。改変テストは実証明の負例であり、合成CSIや選択精度評価に使用したデータではない。負例を患者一覧へ登録していない。

## 実測値

| 項目 | trueケース | falseケース |
| --- | ---: | ---: |
| writer Gatewayのendorse開始からVALID commitまで | 2.195秒 | 2.112秒 |
| reader bridgeの検証HTTP応答・最初の成功測定 | 565.57 ms | 36.89 ms |
| WebUIの検証ボタン操作からHTTP応答完了まで | 125.61 ms | 85.77 ms |
| 記録block | 4 | 5 |
| 記録・閲覧のgas支払 | なし | なし |

各ケース1回の書込と、各測定箇所1回の読出し。trueの最初の成功読出しには検証処理の初回初期化が含まれ得る。falseや後続UIとの速度差を判定値の違いによるものと解釈しない。HTTPにはTLS・通信・bridge処理等が含まれ、pairingだけの実行時間ではない。UI値はMacのPlaywrightからTailscale IP入口を操作した値で、GMKtecからのHTTP値は別JSONに保存した。

今回は新しい証明を生成していないため、CSI取得・証明生成を含むworker全体の時間は未測定。Sepoliaと揃えた繰返し統計・同時負荷・消費電力・運用費の比較もまだ行っていない。gasがないこととサーバー運用費がないことは別。実データに正解ラベルはなく、ここで確認したのは記録・検証機能で、呼吸判定の医学的な正確性ではない。

生の測定値：[summary.json](summary.json)、[true記録](true-record.json)、[true検証](true-verify.json)、[false記録](false-record.json)、[false検証](false-verify.json)、[ブラウザー測定](browser-verification.json)。

## 変更した実装

- `prepare-external.mjs`：明示的なtwo-host-bootstrapのみ1 ordererを許容。従来の3-host検査を維持。manifestに実orderer数と故障許容数を記録。
- `render-channel.mjs`：公開MSPのルートを引数で指定でき、Macのnative CLIでchannel blockを生成可能。
- `bootstrap_fabric_identity.py`：各ホストで組織別offline CA・MSP・TLS・role別identityを生成。公開情報だけを交換する。
- `compose.peer.yml`：内部chaincodeの名前をpeerに分離。同じ実ホストDNSをordererと共有してもコンテナaliasが誤配送しない。
- `bridge.Dockerfile`：CommonJSのproof helperを正しく読み込むためchaincode/package.jsonを含める。
- `compose.bridge.yml`：鍵所有者のUID/GIDで実行。Linuxで0600鍵を読めない問題を解消し、権限を緩めない。
- `request_fabric_bridge.py`：ホスト内tokenと信頼CAでHTTPS要求、応答と処理時間だけ出力。
- `fabric-consortium-mac.sh` / `import_fabric_observation.py`：reader専用APIと、チェーン検証・payload一致後の既存記録のカタログ登録。
- `compose.fabric-viewer.yml` / `nginx/fabric-viewer.conf`：Tailscale IP限定の閲覧入口。書込APIは公開しない。
- `PatientResults.tsx`：FabricをSepoliaと誤表示せず、検証先・記録transaction IDを表示。

## スクリーンショット

- [検証前](viewer-before-verification.png)
- [trueの検証成功](viewer-true.png)
- [falseの検証成功](viewer-false.png)
- [モバイル幅](viewer-mobile.png)
- [実装コード](implementation-code.png)

## 検証と残る範囲

FabricのNodeテスト20件、frontendの患者画面テスト7件、backendの観測関連テスト39件が成功。frontend build / lint / type-checkも成功。backendは既存環境のWeb3 pytest pluginとeth_typingの不整合があるため、自動plugin読込を無効化しpytest_asyncioを明示して実行した。パッケージの入替は行っていない。

```bash
npm --prefix fabric test
npm --prefix frontend run lint
npm --prefix frontend run type-check
npm --prefix frontend run test:unit -- src/__tests__/PatientResults.test.tsx
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend .venv/bin/pytest -p pytest_asyncio.plugin -o addopts='' backend/tests/unit/test_fabric_observations.py backend/tests/unit/test_adaptive_observations.py backend/tests/unit/test_observations.py -q
```

**orderer 1台で故障許容なし。** CA更新・失効・復旧訓練、Mac API/UIのOS起動時の自動起動、新CSIの継続収集からFabric記録までのworker接続、新回路のGMKtec移行、Piを含む3 orderer化は未実施。現在の実装は2ホスト実証環境。

MATLAB入力画面は既存matlab-supportの設定待ち。Docker/Composeとグループ設定は完了し、Fabricは動作している。MATLAB関連パッケージは削除・再設定していない。

再起動・配置・鍵管理の説明：[2ホスト運用手順](../../fabric-two-host-setup.md)。
