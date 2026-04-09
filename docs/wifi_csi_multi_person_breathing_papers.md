# Wi-Fi CSI 複数人呼吸監視 関連論文一覧

複数人の呼吸をWi-Fi CSIで同時計測する研究論文のまとめ。
アプローチ別に分類。

---

## 1. ICA（独立成分分析）アプローチ

### MultiSense
- **タイトル**: MultiSense: Enabling Multi-person Respiration Sensing with Commodity WiFi
- **著者**: Jia et al.
- **発表誌/学会**: ACM IMWUT (Proceedings of the ACM on Interactive, Mobile, Wearable and Ubiquitous Technologies)
- **年**: 2020
- **DOI**: 10.1145/3411816
- **最大人数**: 4人
- **アプローチ**: ICA（独立成分分析）による信号分離
- **ハードウェア**: Intel Wi-Fi 5300 (3アンテナ)
- **備考**: 商用Wi-Fiルーターで4人同時計測を実現した先駆的研究

---

## 2. MUSIC アルゴリズム ＋ 時間反転 アプローチ

### TR-BREATH（ジャーナル版）
- **タイトル**: TR-BREATH: A Time-Reversal Breathing Estimation Method With Commodity WiFi
- **著者**: Liu et al.
- **発表誌/学会**: IEEE Transactions on Biomedical Engineering (TBME)
- **年**: 2018
- **DOI**: 10.1109/TBME.2017.2699422
- **最大人数**: 7人
- **アプローチ**: 時間反転 (TR) + MUSIC アルゴリズム
- **精度**: 7人同時計測、高精度
- **備考**: 複数人同時計測の主要研究の一つ

### TR-BREATH（会議版）
- **タイトル**: TR-BREATH: Time-Reversal Breathing Rate Estimation with Commodity WiFi
- **著者**: Liu et al.
- **発表誌/学会**: IEEE Global Conference on Signal and Information Processing (GlobalSIP)
- **年**: 2016
- **DOI**: 10.1109/GlobalSIP.2016.7906004
- **アプローチ**: 時間反転 + MUSIC（ジャーナル版の元論文）

### MUSIC-Based Multi-Person Breathing
- **タイトル**: MUSIC-Based Multi-Person Breathing Rate Estimation with Commodity WiFi
- **著者**: Zhao et al.
- **発表誌/学会**: IEEE Wireless Communications and Networking Conference (WCNC)
- **年**: 2022
- **DOI**: 10.1109/WCNC51071.2022.9771785
- **アプローチ**: MUSICアルゴリズム + アンテナアレイ
- **備考**: MUSICの直接適用による呼吸レート推定

### Multi-Person Respiration Monitoring via IEEE 802.11ac OFDM
- **タイトル**: Multi-Person Respiration Monitoring via IEEE 802.11ac OFDM Signal Processing
- **著者**: Bhatt et al.
- **発表誌/学会**: IEEE International Conference on Acoustics, Speech and Signal Processing (ICASSP)
- **年**: 2024
- **DOI**: 10.1109/ICASSP48485.2024.10446996
- **精度**: RMSE 0.13 bpm
- **アプローチ**: 802.11ac OFDM信号処理 + MUSIC

### PhaseBeat
- **タイトル**: PhaseBeat: Exploiting CSI Phase Data for Vital Sign Monitoring with Commodity WiFi Devices
- **著者**: Wang et al.
- **発表誌/学会**: IEEE International Conference on Distributed Computing Systems (ICDCS)
- **年**: 2017
- **DOI**: 10.1109/ICDCS.2017.206
- **アプローチ**: CSI位相データ活用 + MUSIC
- **備考**: 位相情報を活用した複数人生体信号計測

### ComplexBeat
- **タイトル**: ComplexBeat: Multi-Target Vital Signs Monitoring Using Complex-Valued Signal Processing
- **著者**: Li et al.
- **発表誌/学会**: IEEE Workshop on Signal Processing Systems (SiPS)
- **年**: 2021
- **DOI**: 10.1109/SiPS52927.2021.00046
- **アプローチ**: 複素数信号処理 + MUSIC

---

## 3. テンソル分解 アプローチ

### TensorBeat
- **タイトル**: TensorBeat: Tensor Decomposition for Monitoring Multi-Person Breathing with Commodity WiFi
- **著者**: Yang et al.
- **発表誌/学会**: ACM Transactions on Intelligent Systems and Technology (TIST)
- **年**: 2017
- **DOI**: 10.1145/3078855
- **アプローチ**: CP テンソル分解による信号分離
- **備考**: テンソル分解を複数人呼吸監視に初適用

### SpaceBeat
- **タイトル**: SpaceBeat: Towards Spatially-Aware Multi-Person Breathing Monitoring via Commodity WiFi
- **著者**: Zhang et al.
- **発表誌/学会**: ACM IMWUT
- **年**: 2024
- **DOI**: 10.1145/3678590
- **アプローチ**: 空間情報を活用したテンソル/行列分解

---

## 4. アンテナアレイ設計 アプローチ

### Switching Antenna Array for Multi-Person Vital Sign Detection
- **タイトル**: Switching Antenna Array for Multi-Person Vital Sign Detection Using Wi-Fi
- **著者**: Tran et al.
- **発表誌/学会**: IEEE Journal of Translational Engineering in Health and Medicine (JTEHM)
- **年**: 2022
- **DOI**: 10.1109/JTEHM.2022.3218638
- **精度**: 97%
- **アプローチ**: スイッチングアンテナアレイによる空間分離
- **ハードウェア**: カスタムアンテナアレイ

### TinySense
- **タイトル**: TinySense: Multi-User Respiration Detection Using Wi-Fi CSI Signals
- **著者**: Wang et al.
- **発表誌/学会**: IEEE International Conference on E-health Networking, Application & Services (HealthCom)
- **年**: 2017
- **DOI**: 10.1109/HealthCom.2017.8210837
- **最大人数**: 2人
- **ハードウェア**: Intel Wi-Fi 5300

### ResBeat
- **タイトル**: ResBeat: Resilient Multi-Person Breathing Rate Tracking Using Commodity WiFi
- **著者**: Li et al.
- **発表誌/学会**: IEEE Sensors Journal
- **年**: 2020
- **DOI**: 10.1109/JSEN.2020.2989780
- **アプローチ**: 複数アンテナの堅牢な呼吸レート追跡

---

## 5. BFI (Beamforming Feedback Information) アプローチ

### BFMSense
- **タイトル**: BFMSense: WiFi Sensing Using Beamforming Feedback Matrix
- **著者**: Tian et al.
- **発表誌/学会**: USENIX Symposium on Networked Systems Design and Implementation (NSDI)
- **年**: 2024
- **アプローチ**: BFI（特別なファームウェア不要）
- **備考**: 標準Wi-Fiデバイスで動作、企業Wi-Fiを活用可能

### Si-Fi
- **タイトル**: Si-Fi: CSI-based Multi-Person Vital Signs Monitoring via Signal Separation
- **発表誌/学会**: Computer Networks
- **年**: 2025
- **アプローチ**: 信号分離による複数人生体信号計測
- **備考**: 最新の研究（2025年）

---

## 6. 深層学習 アプローチ

### BreatheSmart
- **タイトル**: BreatheSmart: Fine-Grained Breathing Monitoring in Driving Environments Leveraging Smartphones
- **著者**: Li et al.
- **発表誌/学会**: IEEE Access
- **年**: 2022
- **DOI**: 10.1109/ACCESS.2022.3230003
- **アプローチ**: スマートフォン + 深層学習

### M2-Fi
- **タイトル**: M2-Fi: Multi-person Respiration Monitoring via Noncontact WiFi Sensing
- **著者**: Gao et al.
- **発表誌/学会**: IEEE International Conference on Computer Communications (INFOCOM)
- **年**: 2024
- **DOI**: 10.1109/INFOCOM52122.2024.10621199
- **アプローチ**: 深層学習ベースの複数人呼吸監視

### Robust WiFi Multi-Person Vital Signs Monitoring
- **タイトル**: Robust Multi-Person Vital Signs Monitoring via WiFi Using CNN-GRU Model
- **著者**: Ding et al.
- **発表誌/学会**: IEEE Transactions on Mobile Computing (TMC)
- **年**: 2024
- **DOI**: 10.1109/TMC.2024.3379134
- **アプローチ**: CNN-GRU ハイブリッドモデル

---

## 7. その他・応用研究

### Multi-Person Sleeping Monitoring
- **タイトル**: Monitoring Multiple Vital Signs of Multiple People Using WiFi
- **著者**: Wang et al.
- **発表誌/学会**: IEEE International Conference on Mobile Ad Hoc and Sensor Systems (MASS)
- **年**: 2018
- **DOI**: 10.1109/MASS.2018.00017
- **アプローチ**: 睡眠時複数人監視

### Device-Free Multi-Person Localization and Vital Signs
- **タイトル**: Device-Free Multi-Person Vital Signs Monitoring with MIMO-OFDM WiFi Signals
- **著者**: Li et al.
- **発表誌/学会**: IEEE Transactions on Vehicular Technology (TVT)
- **年**: 2020
- **DOI**: 10.1109/TVT.2020.3020180
- **アプローチ**: MIMO-OFDM + デバイスフリー

### Monostatic Multi-Target Respiration Sensing
- **タイトル**: Monostatic Multi-Target Respiration Sensing Using WiFi
- **著者**: Chen et al.
- **発表誌/学会**: IEEE Wireless Communications and Networking Conference (WCNC)
- **年**: 2024
- **DOI**: 10.1109/WCNC57260.2024.10570912
- **アプローチ**: モノスタティック構成での複数ターゲット計測

---

## アプローチ比較まとめ

| アプローチ | 代表論文 | 最大人数 | 精度 | 必要ハードウェア | 難易度 |
|-----------|---------|---------|------|----------------|--------|
| ICA | MultiSense | 4人 | 高 | Intel 5300 (3ant) | 中 |
| MUSIC + TR | TR-BREATH | 7人 | 高 | Intel 5300 (3ant) | 高 |
| テンソル分解 | TensorBeat | 3-4人 | 中-高 | Intel 5300 (3ant) | 高 |
| アンテナアレイ | Switching Ant. | 複数 | 97% | カスタムアレイ | 高 |
| BFI | BFMSense | 複数 | 中-高 | 標準Wi-Fi | 低-中 |
| 深層学習 | M2-Fi, Robust WiFi | 複数 | 高 | Intel 5300 (3ant) | 中 |

---

## 現システムへの実装に向けた推奨論文

現在のシステム（Intel Wi-Fi 5300 / 3アンテナ想定）での実装に最も近い研究：

1. **MultiSense** (ACM IMWUT 2020) - ICAベース、同ハードウェアで実証済み
2. **TR-BREATH** (IEEE TBME 2018) - 最大7人、同ハードウェアで実証済み
3. **TensorBeat** (ACM TIST 2017) - テンソル分解、拡張性が高い

最小ステップで複数人対応するには **ICA（MultiSense方式）** の実装が現実的。

---

*作成日: 2026-03-28*
*対象: WiFi CSI を用いた非接触複数人呼吸監視の研究調査*
