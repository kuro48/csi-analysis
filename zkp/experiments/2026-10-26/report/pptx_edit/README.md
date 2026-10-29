# 10月26日PowerPointの直接編集

ユーザー指定の `/Users/ryunosukekurokawa/Documents/class/lab/M2/進捗/2026_10_26/2026_10_26_進捗_黒川.pptx` を、今回の10枚の報告内容へ更新。

- 編集前版は同じフォルダの `2026_10_26_進捗_黒川_編集前バックアップ.pptx`。
- 4:3、元テーマ・スライドマスター・レイアウトを保持。本文と見出しはテキストボックス。表示フォントは簡潔版PDFと同じNoto Sans JPを指定。
- 初期中心比較・LS本数比較・LS証明時間の3点はデータ編集可能なネイティブグラフ。各グラフにXLSXを埋め込み。
- ヒートマップ、複数段の波形、コード抜粋は差し替え・拡縮できる画像。図の生成元は `../brief/`。
- 接続済みPowerPointセッション、Artifact Toolローカルランタイムが利用できず、OOXMLを直接編集する代替手段で作成。python-pptxは不使用。
- PowerPointのUI操作は未許可。PowerPoint本体での表示確認は未実施。macOS Quick Lookで1枚ずつプレビューを生成し、Chromeで全10枚を描画確認。全体一括Quick Lookでは画像参照の表示が不正確になるため個別スライドを検査した。
- XML、全内部relationship、3埋め込みworkbook、元テーマ保持、変更前SHA256を検査してから指定パスへ反映。validation.jsonに証跡。

`edit_deck.py` はバックアップから候補を再作成、`preview_deck.py` はプレビュー検査用、`finalize.py` は変更前ファイル一致を確認してコピーする初回適用用。適用済みのファイルへ無確認で繰り返し上書きしない。
