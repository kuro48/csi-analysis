# 実験の状態（2026-10-26 同期時点）

## 同じ比較証明の公開値による再測定

remeasure_public/report.html が最新集計、remeasure_public/index.html が各 proof の波形。
VMD 5構成・50証明、LS 1/2/4/8/16本・50証明、計100証明が検証済み。
全段階の公開値照合と改変拒否を確認。43構成430証明は当初計画であり、完了数ではない。
VMD残り設定と新公開回路LS32本は未実測。容量超過VMD4構成は resource_limit。
旧LS32本のsetup失敗を、新公開回路32本の結果と混同しない。

Gitにはコード・集計・図・公開証明を保存。Git対象外の入力・中間データ・ログ・大容量生成物はSSHで別途同期。
仮想環境・Pythonキャッシュは端末ごとに再構築する。環境変数・認証情報は同期しない。

## 以前の比較（以下は旧結果）

報告資料と旧診断ビューアを保存・検証済み。

- 本編はRaw実データ8収録のみ。正解呼吸数なしのため、手法間一致度と計算時間を報告。
- VMD：8件×36設定の整数参照スイープ、代表4回路×8件の実witness全最終係数・中心・出力照合を完了。
- LS：8件×6本数の実witness照合を完了。1/2/4/8/16本は各3回、計15証明すべて検証成功。
- LS 32本：8 GiB Node heapでsetup OOM。12 GiB再試行は1,800秒上限で未完了。prove/verify未実施、時間はnull。失敗ログを保存し、無効な途中鍵は削除。
- VMD/LS診断回路：代表Rawで公開中間値を追加。両回路ともGroth16 proof検証、公開値と表示データの完全一致、中間値改変時の検証拒否を確認。
- report/trace_viewer.html：旧・別診断実行の波形ビューア。VMD逆DFT・LSスコア除算等の回路外表示変換を明記。
- report/report.html、summary.html/png、図PNG/PDF、コード抜粋HTML/PNG、波形撮影PNGを保存。
- report/validation.json：実データ限定、15通常証明、2診断証明、80件の通常witness照合記録、コードhash・リンク・描画検査PASS。

元Raw、本番backend/frontend/zkp、参考PowerPointは未変更。

## 次の研究課題

同期GT、64秒以上の実測記録、未使用収録での初期中心候補評価。32本のGroth16計時には別の資源条件または長いsetup上限での再試行が必要。今回の資料には未取得として明示。
