# CSI 呼吸数推定 参考論文まとめ

Wi-Fi CSI を用いた呼吸数推定において、FFT の代替・改善手法として有力な
**MUSIC / ESPRIT（超解像スペクトル推定）** と **PCA + FFT（多サブキャリア統合）**
に関する論文をまとめる。

---

## なぜ FFT の代替を検討するか

| 問題 | 影響 |
|------|------|
| 周波数分解能 ∝ 1/計測時間 | 短い計測 → 低精度 |
| 定常性の仮定 | 呼吸は微妙に揺らぐので不向き |
| スペクトルリーケージ | ピーク位置がずれる |
| 全サブキャリアを独立に処理 | 複数サブキャリアの相関を無視 |

---

## 1. MUSIC / ESPRIT（超解像スペクトル推定）

固有値分解でノイズ部分空間と信号部分空間を分離し、FFT より高い周波数分解能を得る。
サンプル数が同じでも 0.001 Hz 以下の分解能が可能で、短時間計測に強い。

### 論文一覧

#### [1] MUSIC-Based Breathing Rate Monitoring Using Wi-Fi CSI
- **著者**: P.-J. Lai, Y.-S. Zhan, W.-L. Yeh, M.-L. Ku, C.-M. Yu
- **掲載**: IEEE UEMCON 2022
- **URL**: https://ieeexplore.ieee.org/document/9965699/
- **概要**: Intel Wi-Fi Link 5300 + Linux 802.11n CSI Tool でデータ収集し、MUSIC を CSI 振幅・位相に適用。FFT ベース MLE との比較あり。サブキャリア選択との組み合わせも示す。
- **推奨度**: ★★★★★ 最初に読むべき一本。

#### [2] Contactless Respiration Monitoring Via Off-the-Shelf WiFi Devices
- **著者**: Xuefeng Liu, Jiannong Cao, Shaojie Tang, Jiaqi Wen, Peng Guo
- **掲載**: IEEE Transactions on Mobile Computing, Vol. 15, 2016
- **DOI**: 10.1109/TMC.2015.2504935
- **URL**: https://ieeexplore.ieee.org/document/7345587/
- **概要**: COTS デバイスを使い CSI から胸部運動を抽出。スペクトル推定（MUSIC 含む）で呼吸数を検出。Blind Spot 問題への対処も議論。
- **推奨度**: ★★★★★ 高被引用の基礎論文。全体像の把握に最適。

#### [3] Resilient Respiration Rate Monitoring With Realtime Bimodal CSI Data
- **著者**: Xuyu Wang, Chao Yang, Shiwen Mao
- **掲載**: IEEE Sensors Journal, Vol. 20, No. 17, 2020
- **DOI**: 10.1109/JSEN.2020.2989780
- **URL**: https://ieeexplore.ieee.org/abstract/document/9076681/
- **概要**: CSI 振幅と位相差の両方（Bimodal CSI）を活用する ResBeat を提案。DWT + **Root-MUSIC** で呼吸と心拍を分離。適応的信号選択でリアルタイム長時間モニタリングに対応。
- **推奨度**: ★★★★★ Root-MUSIC + 位相差という実装に直結する手法を詳述。

#### [4] Device-Free Multi-Person Respiration Monitoring Using WiFi
- **著者**: Qinghua Gao, Jingyu Tong, Jie Wang ら
- **掲載**: IEEE Transactions on Vehicular Technology, Vol. 69, No. 11, 2020
- **DOI**: 10.1109/TVT.2020.3020180
- **URL**: https://ieeexplore.ieee.org/document/9179993/
- **概要**: ドップラー領域と AoA 領域を組み合わせ、MUSIC 系スペクトル推定を多人数シナリオへ拡張。複数アンテナの空間多様性を活用して個人別に呼吸数を推定。
- **推奨度**: ★★★★ 多人数対応への拡張参考として重要。

#### [5] Multi-Person Respiration Monitoring Leveraging Commodity Wi-Fi Devices
- **著者**: EZ. Yi, K. Niu, FS. Zhang ら
- **掲載**: Journal of Computer Science and Technology (Springer), 2025
- **DOI**: 10.1007/s11390-023-2722-z
- **URL**: https://link.springer.com/article/10.1007/s11390-023-2722-z
- **概要**: WiMUSE を提案し、多人数の混合呼吸信号を BSS 問題として定式化。FFT・MUSIC との定量比較で RMSE を 60% 以上削減。
- **推奨度**: ★★★ MUSIC の限界と改善方向を理解するためのベースライン論文。

---

## 2. PCA + FFT（多サブキャリア統合）

複数サブキャリアを主成分分析で統合し、呼吸に最も相関する方向の時系列信号に FFT を適用。
ノイズを他の主成分に押し込めて SNR を最大化する。

### 論文一覧

#### [6] Monitoring Respiratory Motion With Wi-Fi CSI: BreatheSmart
- **著者**: Susanna Mosleh, Jason B. Coder, Christopher G. Scully, Keith Forsyth, Mohamad Omar Al Kalaa
- **掲載**: **IEEE Access**, Vol. 10, 2022（オープンアクセス）
- **DOI**: 10.1109/ACCESS.2022.3230003
- **URL**: https://ieeexplore.ieee.org/document/9989347/
- **概要**: PCA 前処理 + 全サブキャリア活用で呼吸パターン分類精度 99.54%、呼吸数推定精度 98.69% を達成。NIST 共同研究で信頼性が高い。
- **推奨度**: ★★★★★ IEEE Access で全文無料。PCA 前処理の定量評価が充実。

#### [7] BreatheBand: A Fine-grained and Robust Respiration Monitor System Using WiFi Signals
- **著者**: （ACM TOSN 2023）
- **掲載**: ACM Transactions on Sensor Networks, 2023
- **DOI**: 10.1145/3582079
- **URL**: https://dl.acm.org/doi/10.1145/3582079
- **概要**: RER（Respiration Energy Ratio）でサブキャリアをスコアリングして選択し、**MRC-PCA + ICA + FFT** で呼吸数を推定。呼吸モニタリングベルトと同等の精度を実現。
- **推奨度**: ★★★★★ MRC-PCA パイプラインの実装詳細が豊富で、現システムへの応用がしやすい。

#### [8] MultiSense: Enabling Multi-person Respiration Sensing with Commodity WiFi
- **著者**: Youwei Zeng, Dan Wu, Jie Xiong, Jinyi Liu, Zhaopeng Liu, Daqing Zhang
- **掲載**: ACM IMWUT (UbiComp), Vol. 4, Issue 3, 2020
- **DOI**: 10.1145/3411816
- **URL**: https://dl.acm.org/doi/10.1145/3411816
- **概要**: 多人数呼吸監視を BSS 問題として定式化。**PCA → ICA** で個人別呼吸信号を分離し、3 アンテナで最大 4 人を平均誤差 0.73 bpm で推定。
- **推奨度**: ★★★★ PCA を多サブキャリア・多アンテナの前処理として位置づけた先駆的論文。

#### [9] Hybrid Subcarrier Selection Method for Vital Sign Monitoring
- **著者**: R. Zhang, Z. Wang, G. Li, Y. Wang, J. Shuai, J. Zheng
- **掲載**: IEEE Sensors Journal, 2022
- **URL**: https://ieeexplore.ieee.org/document/9928535/
- **概要**: 長期・短期データの不均一性を考慮したハイブリッドサブキャリア選択を提案。CSI 振幅と位相を組み合わせてサブキャリアを選択し、FFT でバイタルサインを推定。
- **推奨度**: ★★★★ 実環境での信号長変動という実用的課題に対応した論文。

---

## 3. 補足：両手法に関連する基礎論文

| タイトル | 著者 | 年 | 掲載誌 | DOI / URL |
|----------|------|----|--------|-----------|
| FarSense: Pushing the Range Limit of WiFi-based Respiration Sensing | Zeng, Wu ら | 2019 | ACM IMWUT (UbiComp) | https://dl.acm.org/doi/10.1145/3351279 |
| TinySense: Multi-user respiration detection using Wi-Fi CSI signals | Wang P. ら | 2017 | IEEE Healthcom | https://ieeexplore.ieee.org/document/8210837/ |
| Contactless respiration rate estimation using MUSIC algorithm | C. Uysal, T. Filik | 2018 | IEEE | https://ieeexplore.ieee.org/document/8266269 |

---

## 読む順の推奨

```
Step 1: CSI 呼吸検知の全体像
  └─ [2] TMC 2016（Liu ら）

Step 2: MUSIC の直接適用を理解
  └─ [1] IEEE UEMCON 2022
  └─ [3] IEEE Sensors Journal 2020（Root-MUSIC + 位相差）

Step 3: PCA + FFT パイプラインの実装
  └─ [6] IEEE Access 2022（全文無料、PCA 前処理の定量評価）
  └─ [7] ACM TOSN 2023（MRC-PCA パイプラインの実装詳細）
```

---

## 手法比較サマリー

| 手法 | 精度 | 計算コスト | 短時間計測 | 多人数対応 | 現システムへの導入難度 |
|------|------|-----------|-----------|-----------|----------------------|
| FFT（現在） | 中 | 低 | 弱 | 弱 | — |
| PCA + FFT | 中〜高 | 低〜中 | 普通 | 普通 | 低（FFT の前に PCA を挟むだけ） |
| MUSIC / ESPRIT | 高 | 高 | **強** | **強** | 中（固有値分解の実装が必要） |

---

*作成日: 2026-04-07*
