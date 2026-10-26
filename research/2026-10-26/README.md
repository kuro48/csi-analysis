# CSI呼吸推定回路の比較実験 — 2026-10-26

進捗報告は **[目的・実施内容・結果を図と交互に読むレポート](report/report.html)** をブラウザで開く。全測定表とコード画像は [詳細版](report/report_details.html) に保存。元の10月19日PowerPointは変更していない。

## 主な結果

- VMD：実CSI8件で、既定K=3/R=4と同じ入力のLSとの平均絶対差は10.657 BPM。K=4/R=4では1.108 BPM。K=3/R=32では11.145 BPMで、反復増だけでは改善しなかった。
- 初期中心だけを `[8,24,48]` → `[8,16,24]` に変えても1.108 BPM。制約数は同じ340,734。低域への設定変更なので、高い周波数を含む別の実測記録での検証が必要。変更候補の一律優位は示していない。
- LS：1/2/4/8/16/32本を比較。同じ入力・同じ周波数gridの浮動小数点LSと、実データ48条件で推定binが一致。全サブキャリアLSとの差は本数増に対し非単調。
- 今回は正解データなしで評価する。実データ表は**手法間一致度**であり、呼吸数の正解誤差ではない。本編はRaw実データに限定した。
- VMD表のLSは「同じPCA・量子化波形上のSciPy LS」、LS回路表は「生CSI振幅二乗上のE2E LS」。前処理・サンプル数・探索帯域・選択規則が違う。

証明生成時間は [LS測定JSON](lomb/proof_summary.json) と図付きレポートに、compile/setup/witness/prove/verifyを分けて保存する。**ローカルApple M4 Proの実測であり、エッジ端末の時間ではない。** 通常VMDの比較はwitness照合までで、Groth16証明時間は測定していない。公開中間値を追加する診断回路の証明は別実験として扱う。

LS通常回路の1/2/4/8/16本は各3回、計15証明が検証成功。32本は推定値・witness照合を完了したが、鍵生成が8 GiB Node heapでOOM、12 GiB再試行でも1,800秒上限で未完了となった。32本の証明生成時間は未取得として表示する。失敗試行も `lomb/failures/attempts.json` に保存した。

## 公開中間値の波形

[処理段階を切り替える波形ビューア](report/trace_viewer.html) をブラウザで開く。代表Raw収録 `csi_20260526_034004` について、VMD K3/R4とLS 8本の独立診断回路を作成した。

- VMD：入力・DFT・全4反復の各モード係数・中心を公開（公開入力込み1,786値）。
- LS：I/Q・振幅二乗・平均除去・sin/cos基底・射影・スコアの分子/分母等を公開（公開入力込み7,389値）。
- 両回路でGroth16証明の正常検証、証明公開値と表示データの完全一致、中間値改変時の検証拒否を確認。
- VMDモードの時間波形は公開係数から回路外で逆DFTした表示。LSスコアの割り算も回路外の表示変換。
- 診断回路は入力情報を公開する。通常回路・鍵は変更せず、ローカルの診断用回路・鍵へ分離した。

診断回路の証明時間は各1回の参考値でVMD 4.282秒、LS 9.905秒。通常回路の3回中央値と混ぜて比較しない。正確な公開整数値、配列定義、証明・検証鍵は `diagnostics/vmd/` と `diagnostics/lomb/` に保存した。

## 発表で使うファイル

10月19日の参考PDFに合わせた、説明を絞った10ページ版：[進捗報告PDF](../../output/pdf/2026_10_26_進捗_黒川.pdf)。白背景・4:3で比較グラフ、コード画像、中間値波形を掲載。再生成コードは `report/brief/`。

| 用途 | ファイル |
|---|---|
| 段階・反復・SCを切替える波形 | [report/trace_viewer.html](report/trace_viewer.html) |
| 波形ビューアの撮影済み画像 | [VMD](report/trace_vmd.png)、[LS](report/trace_lomb.png) |
| 公開出力追加の回路コード画像 | [VMD](report/code_debug_vmd.png)、[LS](report/code_debug_lomb.png) |
| 詳細な図付き報告 | [report/report.html](report/report.html) |
| 1枚で報告する要約（4:3） | [report/summary.png](report/summary.png)、[HTML](report/summary.html) |
| VMD K/R比較 | [report/figures/vmd_real.png](report/figures/vmd_real.png) |
| VMD初期中心比較 | [report/figures/vmd_initialization.png](report/figures/vmd_initialization.png) |
| LS本数と一致度 | [report/figures/lomb_agreement.png](report/figures/lomb_agreement.png) |
| LS証明生成時間 | [report/figures/lomb_proof_time.png](report/figures/lomb_proof_time.png) |
| VMDコード撮影用 | [report/code_vmd.html](report/code_vmd.html)、[PNG](report/code_vmd.png) |
| LSコード撮影用 | [report/code_lomb.html](report/code_lomb.html)、[PNG](report/code_lomb.png) |

各グラフには拡大用PDFもある。コードHTMLは元ファイルの抜粋・行番号・ファイル名付き。PNGはそのHTMLをChromeで実際に描画した画像で、PowerPointへそのまま貼れる。対応JSONは抜粋元のSHA256を記録している。

## 保存と再現

- [common/README.md](common/README.md)：Raw一覧・入力条件・正解ラベル・共通データ再現
- [vmd/README.md](vmd/README.md)：36条件スイープ・初期化/padding診断・実回路照合
- [lomb/README.md](lomb/README.md)：物理サブキャリア選択・6サイズ回路・実証明測定
- [common/REVIEW.md](common/REVIEW.md)：独立レビューと比較の限界
- `report/make_figures.py` / `report/make_report.py`：測定JSON/CSVから図とHTMLを再生成

```sh
python3 research/2026-10-26/report/make_figures.py
python3 research/2026-10-26/report/make_trace_viewer.py
python3 research/2026-10-26/report/make_report.py
python3 research/2026-10-26/report/render_summary.py
python3 research/2026-10-26/report/render_trace.py
python3 research/2026-10-26/report/verify_report.py
```

本番のbackend/frontend/zkp回路ソースは未変更。研究コードはこのディレクトリに分離し、Raw原本も変更していない。8収録は独立8被験者の評価ではない。各冒頭48秒1窓で、VMDは96観測点＋32点ゼロ埋めを使う。

生成NPZ・秘密入力・witness・巨大ビルド/鍵はローカル保存しGit除外。原本SHA256、乱数seed、パラメータ、環境、コマンドを残す。鍵のダウンロード元とSHA256は `.cache/ptau21_metadata.json` に保存する。

次の評価は、同期呼吸GT・64秒以上の記録・未知の収録で初期中心候補を検証すること。高域の呼吸と帯域外ノイズを分け、サブキャリア数を選ぶ際には実測証明コストと正解付き精度の両方を使う。

作業途中に計算した合成対照は各実験ディレクトリに補足として残しているが、本編の図・表・結論には使用しない。
