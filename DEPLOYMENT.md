# 本番環境デプロイメントガイド

## 本番環境の準備

### 1. SSL証明書の準備

SSL証明書を取得し、適切な場所に配置してください：

```bash
# SSL証明書ディレクトリの作成
mkdir -p nginx/ssl

# 証明書ファイルを配置
# cert.pem - SSL証明書
# key.pem - プライベートキー
```

### 2. 環境変数の設定

本番環境用の環境変数ファイルを作成：

```bash
# .env.prod ファイルを作成（.env.prod.example をベースに）
cp .env.prod.example .env.prod

# 以下の項目を必ず変更してください：
# - DATABASE_PASSWORD: 強力なパスワードに変更
# - REDIS_PASSWORD: 強力なパスワードに変更
# - JWT_SECRET_KEY: ランダムで強力なキーに変更
# - FRONTEND_URL: 実際のドメインに変更
# - BACKEND_URL: 実際のAPIドメインに変更
```

### 3. データベースバックアップの設定

```bash
# バックアップディレクトリの作成
mkdir -p backup

# バックアップスクリプトの実行権限を設定
chmod +x scripts/backup.sh
```

## 本番環境デプロイ

### Docker Composeでのデプロイ

```bash
# 本番環境用のコンテナ起動
docker-compose -f docker-compose.prod.yml up -d

# ログの確認
docker-compose -f docker-compose.prod.yml logs -f
```

### 初回セットアップ

```bash
# データベースマイグレーション
docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head

# 初期管理者アカウントの作成
docker-compose -f docker-compose.prod.yml exec backend python scripts/create_admin.py
```

### ヘルスチェック

```bash
# サービスの状態確認
docker-compose -f docker-compose.prod.yml ps

# APIの動作確認
curl -f https://api.yourdomain.com/health

# フロントエンドの動作確認
curl -f https://yourdomain.com
```

## セキュリティ設定

### ファイアウォール設定

```bash
# UFWでファイアウォール設定（Ubuntu/Debian）
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

### SSL設定の確認

```bash
# SSL証明書の有効期限確認
openssl x509 -in nginx/ssl/cert.pem -noout -dates

# SSL設定テスト
curl -I https://yourdomain.com
```

## 監視・メンテナンス

### ログ監視

```bash
# アプリケーションログ
docker-compose -f docker-compose.prod.yml logs -f backend
docker-compose -f docker-compose.prod.yml logs -f frontend

# Nginxログ
docker-compose -f docker-compose.prod.yml logs -f nginx
```

### データベースバックアップ

```bash
# 手動バックアップ
./scripts/backup.sh

# crontabでの自動バックアップ設定
0 2 * * * /path/to/project/scripts/backup.sh
```

### システムリソース監視

```bash
# Docker統計情報
docker stats

# ディスク使用量
df -h

# メモリ使用量
free -h
```

## トラブルシューティング

### コンテナが起動しない

```bash
# コンテナの状態確認
docker-compose -f docker-compose.prod.yml ps

# エラーログの確認
docker-compose -f docker-compose.prod.yml logs [service_name]

# コンテナの再起動
docker-compose -f docker-compose.prod.yml restart [service_name]
```

### データベース接続エラー

```bash
# PostgreSQL接続確認
docker-compose -f docker-compose.prod.yml exec postgres pg_isready -U csi_user -d csi_system

# データベースコンテナの再起動
docker-compose -f docker-compose.prod.yml restart postgres
```

### SSL証明書エラー

```bash
# 証明書の確認
openssl x509 -in nginx/ssl/cert.pem -text -noout

# Nginxコンテナの再起動
docker-compose -f docker-compose.prod.yml restart nginx
```

## アップデート手順

### アプリケーションのアップデート

```bash
# 最新コードの取得
git pull origin main

# イメージの再ビルド
docker-compose -f docker-compose.prod.yml build

# コンテナの再起動
docker-compose -f docker-compose.prod.yml up -d

# データベースマイグレーション（必要に応じて）
docker-compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

### 緊急時のロールバック

```bash
# 前のバージョンに戻す
git checkout [previous_commit_hash]

# イメージの再ビルドと起動
docker-compose -f docker-compose.prod.yml build
docker-compose -f docker-compose.prod.yml up -d
```

## パフォーマンス最適化

### Nginxキャッシュ設定

Nginx設定でキャッシュを有効化：

```nginx
# 静的ファイルのキャッシュ
location ~* \.(jpg|jpeg|png|gif|ico|css|js)$ {
    expires 1y;
    add_header Cache-Control "public";
}
```

### データベース最適化

```sql
-- PostgreSQLのクエリ性能確認
EXPLAIN ANALYZE SELECT * FROM csi_data WHERE device_id = 'device_001';

-- インデックスの確認
\d+ csi_data
```

### Redis設定最適化

```bash
# Redis設定の確認
docker-compose -f docker-compose.prod.yml exec redis redis-cli CONFIG GET "*"

# メモリ使用量の確認
docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO memory
```

## 本番環境チェックリスト

- [ ] SSL証明書が正しく設定されている
- [ ] 環境変数が適切に設定されている
- [ ] データベースパスワードが変更されている
- [ ] JWT秘密鍵が変更されている
- [ ] ファイアウォールが設定されている
- [ ] バックアップ戦略が実装されている
- [ ] 監視システムが設定されている
- [ ] ログローテーションが設定されている
- [ ] アップデート手順が文書化されている
- [ ] 緊急時連絡先が明記されている