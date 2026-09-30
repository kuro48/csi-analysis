# Lomb–Scargle完全回路 エッジ配布結果

実施日: 2026-09-30  
パッケージバージョン: `csi-lomb-scargle-e2e-edge-v1`

## 1. 結果

生CSIからLomb–Scargle呼吸推定のGroth16証明を生成する自己完結パッケージを作成し、
Tailscale上のLinuxエッジ候補 `infonetworking-csi` へTaildropで送信した。

送信ファイル:

```text
csi-lomb-scargle-e2e-edge-v1.tar.gz
```

アーカイブ情報:

| 項目 | 値 |
|---|---|
| 圧縮サイズ | 263 MB |
| 展開サイズ | 448 MB |
| SHA-256 | `5d079fc900f57f499d6aa4854ff67a67c02519e33c033db25d98882f19358d91` |
| 内部manifest検査対象 | 1,611ファイル |

Tailscale疎通:

```text
infonetworking-csi (100.111.253.60): online
direct path: 192.168.11.4:41641
ping: 5 ms
```

Taildrop送信コマンドはexit code 0で完了した。

## 2. パッケージ内容

ローカル作業ツリー上の配置:

```text
edge/lomb_scargle_e2e/
├── README.md
├── VERSION
├── MANIFEST.sha256
├── install.sh
├── artifacts/
│   ├── csi_lomb_scargle_end_to_end.wasm
│   ├── csi_lomb_scargle_end_to_end_final.zkey
│   ├── verification_key.json
│   ├── generate_witness.js
│   └── witness_calculator.js
├── bin/
│   ├── prepare_input.py
│   ├── make_self_test_input.py
│   ├── build_result.py
│   ├── prove.sh
│   ├── verify.sh
│   ├── self_test.sh
│   └── verify_manifest.py
└── vendor/runtime/
    └── snarkjsと実行時依存
```

端末側でCircom、ptau、npm install、Trusted Setupを実行する必要はない。

## 3. Groth16鍵の準備

回路規模:

| 項目 | 値 |
|---|---:|
| 制約数 | 807,453 |
| 非線形制約 | 570,079 |
| 線形制約 | 237,374 |
| 秘密入力 | 1,025 |
| 公開入力 | 64 |
| 公開出力 | 5 |

`powersOfTau28_hez_final_24.ptau` を使って初期zkeyを生成し、暗号学的乱数による追加
contributionを適用した。

検証結果:

```text
ZKey Ok!
```

配布物には最終proving keyとverification keyだけを含める。R1CS、ptau、初期zkeyは
エッジ実行に不要なため含めていない。

## 4. エッジ用入力変換

`prepare_input.py` はPicoScenes `.csi` を次の手順で固定回路入力へ変換する。

1. CSIと`systemns`の両方を持つフレームを読む。
2. 最頻CSI幅のフレームを採用する。
3. 全サブキャリア幅から等間隔に8本を選ぶ。
4. タイムスタンプ順へ整列する。
5. 1 ms量子化後の重複タイムスタンプを除く。
6. 全収録区間から64観測を選ぶ。
7. 全I/Qへ1つの共通スケールを適用する。
8. 12-bit、offset 2048形式へ変換する。
9. 秘密Poseidon nonceを生成する。

`.npz` 入力にも対応する。

```text
csi: complex[samples, subcarriers]
timestamps_ns または timestamps_ms
```

## 5. プライバシー動作

次の秘密データは一時ディレクトリにだけ作成される。

- 量子化後I/Q
- commitment nonce
- 回路入力JSON
- witness
- snarkjs内部のproof生成中間ファイル

`prove.sh` は `mktemp` で専用ディレクトリを作り、成功・失敗・割り込みのいずれでも
終了時に削除する。

公開結果JSONに含むもの:

- Poseidon CSIコミットメント
- Groth16 proof
- 公開相対タイムスタンプ
- 選択サブキャリア番号
- 推定bin、Hz、BPM
- グローバルピーク
- 正常判定

公開結果JSONに含めないもの:

- 生CSI
- 量子化後I/Q
- nonce
- witness
- 入力スケール
- 入力振幅統計
- Lomb–Scargleスペクトル

元の `.csi` は既定では残す。証明成功後に削除する運用では明示的に次を指定する。

```bash
DELETE_SOURCE_AFTER_PROOF=1 ./bin/prove.sh capture.csi proof_result.json
```

## 6. 実行検証

### 6.1 自己診断

検証環境:

```text
CPU: Intel Core i5-8500B 3.00 GHz
RAM: 16 GB
Node.js: v20.20.2 / v26.3.1
```

合成0.25 Hz呼吸信号で、Node 20とNode 26の双方から次を完走した。

```text
witness生成
→ Groth16 proof生成
→ ローカルverify
→ 結果JSON生成
→ 結果JSONからの再verify
```

代表結果:

| 工程 | 時間 |
|---|---:|
| witness生成 | 0～1秒 |
| Groth16 proof生成 | 24～27秒 |
| verification | 0～1秒 |

出力:

```text
isNormal: true
selectedSubcarrier: 0
estimatedFrequencyBin: 18
estimatedBpm: 15.3307086614
globalPeakFrequencyBin: 18
globalPeakBpm: 15.3307086614
snarkjs verify: OK
```

### 6.2 NPZ入力変換経路

128サンプル・16サブキャリアの合成complex CSIをNPZとして作り、次を検証した。

```text
NPZ読込
→ 8サブキャリア選択
→ 64サンプル選択
→ I/Q量子化
→ witness生成
→ proof生成
→ verify
```

結果:

```text
witness_seconds=1
proof_seconds=25
verify_seconds=0
estimatedBpm=15.3307086614
isNormal=true
verify=OK
```

公開結果に `csiI`、`csiQ`、`commitmentNonce`、入力変換メタデータが含まれないことも
確認した。

### 6.3 配布アーカイブ再展開試験

送信したものと同一のtar.gzを新しい一時ディレクトリへ展開し、リポジトリや元の
`node_modules` を参照せず次を実行した。

```bash
./install.sh --self-test
```

結果:

```text
manifest OK: 1611 files
Groth16 proof: generated
snarkjs verify: OK
self-test passed
```

したがって、アーカイブには証明生成に必要な実行物が自己完結している。

## 7. エッジ端末での開始手順

Taildrop受信箱から取得する。

```bash
mkdir -p ~/received-csi-prover
tailscale file get ~/received-csi-prover
cd ~/received-csi-prover
sha256sum csi-lomb-scargle-e2e-edge-v1.tar.gz
```

期待値:

```text
5d079fc900f57f499d6aa4854ff67a67c02519e33c033db25d98882f19358d91
```

展開して自己診断する。

```bash
tar -xzf csi-lomb-scargle-e2e-edge-v1.tar.gz
cd lomb_scargle_e2e
./install.sh --self-test
```

実CSIを証明する。

```bash
./bin/prove.sh /path/to/capture.csi ./proof_result.json
./bin/verify.sh ./proof_result.json
```

## 8. 実機確認上の制限

`infonetworking-csi` はTailscale上でオンラインだったが、この作業環境のSSH公開鍵は
許可されていなかった。

```text
Permission denied (publickey,password)
```

そのため、Taildropへのパッケージ配置までは完了しているが、対象Linux端末上での展開、
PicoScenes実ファイルによる証明、ARM/x86実機の処理時間・最大メモリ測定は未確認である。

「アーカイブ単体で証明生成できること」は再展開試験で確認済みだが、対象端末固有の
Node/Python/PicoScenes環境と実データ互換性は、端末側で `./install.sh --self-test` と
実CSI 1件を実行して最終確認する必要がある。

## 9. アルゴリズム上の制限

- 64サンプル、8サブキャリア、32周波数binのfeasibility版。
- 探索範囲は約3～24 BPM。
- 正常帯域はbin量子化により約6.43～21.50 BPM。
- `.csi` のバイナリ解析と64×8への選択・量子化は回路外。
- 回路は選択後の64×8 I/Q全体をPoseidonコミットメントで拘束する。
- 現行PythonのSNR上位256選択、Butterworth、PCAは再現しない。
- 実CSI精度、異常呼吸精度、端末上の電力・温度・最大RSSは今後の実測項目。
