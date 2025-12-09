#!/bin/bash
set -e

echo "Waiting for PostgreSQL to be ready..."

# PostgreSQLが利用可能になるまで待機
until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$DATABASE_HOST" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c '\q' 2>/dev/null; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done

echo "PostgreSQL is ready!"

# SQLAlchemyでテーブルを作成
echo "Creating database tables..."
python -c "
from app.core.database import Base, engine
# クラスを明示的にインポート
from app.models import User, CSIData, Session, BreathingAnalysis, Alert

# 全てのテーブルを作成
Base.metadata.create_all(bind=engine)
print('Tables created successfully!')
"

# Alembicマイグレーションテーブルをスタンプ（既存のマイグレーションをスキップ）
echo "Stamping Alembic migrations..."
alembic stamp head

echo "Database setup completed successfully!"

# Uvicornサーバーを起動
echo "Starting Uvicorn server..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
