# タスク完了時チェックリスト

## コード変更後の必須タスク

### バックエンド変更時

#### 1. コード品質チェック
```bash
cd backend
black app/                # フォーマット
isort app/                # import順序
flake8 app/               # リンター
mypy app/                 # 型チェック
```

#### 2. テスト実行
```bash
pytest                    # 全テスト実行
pytest --cov=app          # カバレッジ確認
```

#### 3. データベースマイグレーション
モデル変更がある場合：
```bash
alembic revision --autogenerate -m "変更内容"
alembic upgrade head
```

#### 4. API動作確認
```bash
# ヘルスチェック
curl http://localhost:8000/health

# 変更したエンドポイントのテスト
curl -X GET http://localhost:8000/api/v2/... -H "Authorization: Bearer TOKEN"
```

### フロントエンド変更時

#### 1. コード品質チェック
```bash
cd frontend
npm run lint              # ESLint
npm run type-check        # TypeScript型チェック
```

#### 2. ビルド確認
```bash
npm run build             # 本番ビルド成功確認
```

#### 3. 動作確認
- ブラウザで該当ページにアクセス
- コンソールエラーがないか確認（F12 → Console）
- ネットワークエラーがないか確認（F12 → Network）

### ZKP変更時

#### 1. 回路コンパイル
```bash
cd zkp
npm run compile           # 回路コンパイル成功確認
```

#### 2. Trusted Setup
```bash
npm run setup             # セットアップ成功確認
```

#### 3. 証明生成・検証テスト
```bash
npm run prove             # 証明生成テスト
npm run verify            # 証明検証テスト
npm run test              # 全テスト実行
```

## Git操作前チェック

### コミット前
- [ ] 不要なコメント・デバッグコード削除
- [ ] console.log / print文の削除
- [ ] 機密情報（APIキー、パスワード）が含まれていないか確認
- [ ] .gitignore に除外ファイルが正しく設定されているか

### コミットメッセージ
```
種類: 簡潔な説明（50文字以内）

詳細な説明（必要に応じて）
- 変更点1
- 変更点2
```

## 環境別チェック

### 開発環境
- [ ] Docker コンテナが正常起動
- [ ] データベース接続正常
- [ ] Redis接続正常
- [ ] バックエンドAPI正常応答（http://localhost:8000/health）
- [ ] フロントエンド正常表示（http://localhost:3000）

### 本番環境（デプロイ前）
- [ ] 環境変数が本番用に設定（DEBUG=false など）
- [ ] JWT_SECRET_KEY が安全な値に変更
- [ ] データベースマイグレーション完了
- [ ] 本番ビルドが成功
- [ ] セキュリティスキャン実施
- [ ] パフォーマンステスト実施

## ドキュメント更新

### 機能追加時
- [ ] API仕様書更新（OpenAPI/Swagger）
- [ ] README.md 更新（必要に応じて）
- [ ] CLAUDE.md 更新（重要な変更の場合）
- [ ] コメント・Docstring追加

### 設定変更時
- [ ] 環境変数のサンプルファイル更新（.env.example）
- [ ] docker-compose.yml 更新（必要に応じて）
- [ ] デプロイ手順更新（必要に応じて）

## レビュー観点

### コードレビュー
- [ ] コーディング規約準拠
- [ ] セキュリティ脆弱性なし
- [ ] パフォーマンス問題なし
- [ ] エラーハンドリング適切
- [ ] テストカバレッジ十分

### API設計
- [ ] RESTful設計原則準拠
- [ ] 適切なHTTPステータスコード使用
- [ ] エラーレスポンス統一
- [ ] 認証・認可適切

### データベース
- [ ] インデックス適切
- [ ] 外部キー制約設定
- [ ] マイグレーションロールバック可能
- [ ] パフォーマンス影響確認

## トラブルシューティング

### エラー発生時
1. ログ確認
```bash
docker-compose logs -f backend
docker-compose logs -f frontend
```

2. サービス状態確認
```bash
docker-compose ps
./scripts/health_check.sh
```

3. 必要に応じてサービス再起動
```bash
docker-compose restart backend
docker-compose restart frontend
```

### データベース問題
```bash
# データベース接続確認
docker-compose exec postgres pg_isready -U csi_user -d csi_system

# マイグレーション状態確認
cd backend && alembic current

# マイグレーション再適用
alembic downgrade -1
alembic upgrade head
```

### Redis問題
```bash
# Redis接続確認
docker-compose exec redis redis-cli ping

# キャッシュクリア
docker-compose exec redis redis-cli FLUSHALL
```
