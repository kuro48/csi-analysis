# GMKtecの役割訂正とSSH確認

利用者の補足に従い、GMKtecをCSI取得・証明生成端末、このMacを常時運用対象外とする方針に修正した。前回の3台配置・追加PC不要という説明は訂正した。

`infonetworking@100.111.253.60`へ既存のホスト鍵検査を有効にしたSSHで接続成功。最初のMacユーザー名を使った接続は認証失敗だったが、リポジトリ内の既存配備記録から正しい小文字ユーザー名を確認して接続した。

[確認結果JSON](host-inventory.json)にはCPU・メモリ・空き容量・専用ランタイム・PicoScenesの稼働有無を記録した。GMKtec上の変更・新しい証明生成・CSIファイル読み取り・サービス停止は行っていない。

変更対象：

- [現行配置手順](../../distributed-staging.md)：GMKtecに取得・生成を集約し、台帳・閲覧側は別ホスト候補とした。
- [GMKtec移行手順](../../gmktec-edge-migration.md)：旧環境との差、移すファイル、API/worker分離の未実装部分、同時収録試験の順序を整理した。
- `deploy/staging/app.env.example`・`compose.app.yml`：Mac向けという記述を取り除き、GMKtecでの移行途中の同一ホスト構成であることを明示した。サービスの動作定義は変更していない。
- `scripts/staging/inspect_edge.py`：機器情報だけを収集する読み取り専用の検査を追加し、実際のGMKtecで実行した。

現段階で新しい配備設定をGMKtecへ適用していない。4,004候補版の移行、連続取得との負荷試験、API分離、分散Fabric実配備、Sepolia実配備は今後の作業。
