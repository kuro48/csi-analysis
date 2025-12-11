# 推奨コマンド

## システム起動・停止

### 統合起動（推奨）
```bash
./start.sh                              # 全サービス一括起動（自動セットアップ）
```

### Docker操作
```bash
docker-compose up -d                    # バックグラウンド起動
docker-compose down                     # サービス停止
docker-compose down --volumes           # データ削除を含む完全停止
docker-compose restart                  # 全サービス再起動
docker-compose restart backend          # バックエンドのみ再起動
docker-compose logs -f                  # 全ログ監視
docker-compose logs -f backend          # バックエンドログ監視
docker-compose ps                       # サービス状態確認
```

### 個別サービス起動（手動開発）
```bash
# バックエンド
cd backend
python -m uvicorn app.main:app --reload

# フロントエンド
cd frontend
npm run dev
```

## バックエンド開発

### 依存関係管理
```bash
pip install -r requirements.txt         # 依存関係インストール
pip freeze > requirements.txt           # 依存関係更新
```

### コード品質
```bash
black app/                              # コードフォーマット
isort app/                              # import順序修正
flake8 app/                             # リンター実行
mypy app/                               # 型チェック
```

### テスト
```bash
pytest                                  # 全テスト実行
pytest tests/test_api.py                # 特定ファイルのテスト
pytest -v                               # 詳細表示
pytest --cov=app                        # カバレッジ測定
```

### データベース
```bash
alembic revision --autogenerate -m "変更内容"  # マイグレーション作成
alembic upgrade head                           # マイグレーション適用
alembic downgrade -1                           # 1つ前に戻す
alembic history                                # マイグレーション履歴
```

## フロントエンド開発

### 依存関係管理
```bash
npm install                             # 依存関係インストール
npm update                              # 依存関係更新
```

### 開発サーバー
```bash
npm run dev                             # 開発サーバー起動（Turbopack）
npm run build                           # 本番ビルド
npm run start                           # 本番サーバー起動
```

### コード品質
```bash
npm run lint                            # ESLint実行
npm run lint:fix                        # ESLint自動修正
npm run type-check                      # TypeScript型チェック
```

### テスト
```bash
npm run test                            # テスト実行
npm run test:ci                         # CI環境テスト（lint + type-check）
```

## ZKP開発

### 回路コンパイル・セットアップ
```bash
cd zkp
npm run compile                         # 回路コンパイル
npm run setup                           # Trusted Setup
npm run prove                           # 証明生成
npm run verify                          # 証明検証
npm run test                            # テスト実行
```

### 個別回路操作
```bash
npm run compile:csi_selector            # CSIサブキャリア選択回路コンパイル
npm run setup:csi_selector              # CSIサブキャリア選択回路セットアップ
node scripts/prove_from_all_subcarriers.js  # 全サブキャリア証明生成
```

## デバッグ・トラブルシューティング

### ヘルスチェック
```bash
./scripts/health_check.sh               # システム全体ヘルスチェック
curl http://localhost:8000/health       # バックエンドヘルスチェック
curl http://localhost:3000              # フロントエンドアクセス確認
```

### データベース接続確認
```bash
docker-compose exec postgres pg_isready -U csi_user -d csi_system
docker-compose exec postgres psql -U csi_user -d csi_system
```

### Redis接続確認
```bash
docker-compose exec redis redis-cli ping
docker-compose exec redis redis-cli
```

### コンテナ内シェル
```bash
docker-compose exec backend bash        # バックエンドコンテナ内シェル
docker-compose exec frontend sh         # フロントエンドコンテナ内シェル
docker-compose exec postgres bash       # PostgreSQLコンテナ内シェル
```

### 完全リセット
```bash
docker-compose down --volumes --remove-orphans
docker system prune -af
./start.sh
```

## API操作

### 認証
```bash
# ログイン
curl -X POST http://localhost:8000/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# ユーザー登録
curl -X POST http://localhost:8000/api/v2/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"newuser","password":"password123","email":"user@example.com"}'
```

### CSIデータ操作
```bash
# データアップロード（エッジデバイス専用）
curl -X POST http://localhost:8000/api/v2/csi-data/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@sample.pcap" \
  -F "device_id=test-device-001"

# データ一覧取得
curl -X GET http://localhost:8000/api/v2/csi-data/ \
  -H "Authorization: Bearer YOUR_TOKEN"

# データ詳細取得
curl -X GET http://localhost:8000/api/v2/csi-data/{id} \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Git操作

```bash
git status                              # 状態確認
git add .                               # 全変更ステージング
git commit -m "変更内容"                # コミット
git push                                # プッシュ
git pull                                # プル
```

## ユーティリティ

### Darwin（macOS）特有コマンド
```bash
ifconfig | grep "inet "                 # IPアドレス確認
lsof -i :8000                           # ポート8000使用状況確認
brew services list                      # Homebrewサービス一覧
```

### プロセス管理
```bash
ps aux | grep python                    # Pythonプロセス確認
ps aux | grep node                      # Nodeプロセス確認
kill -9 PID                             # プロセス強制終了
```
