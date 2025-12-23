"""Alembic環境設定"""

import os
from logging.config import fileConfig

from sqlalchemy import create_engine
from sqlalchemy import pool
from alembic import context

# CSIモデルのインポート
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.models.base import BaseModel
from app.models.user import User
from app.models.csi_data import CSIData, Session

# Alembic Config オブジェクト
config = context.config

# ログ設定
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# メタデータターゲット
target_metadata = BaseModel.metadata

def get_url():
    """データベースURLを環境変数から取得"""
    return os.getenv("DATABASE_URL", "postgresql://csi_user:csi_password@localhost:5432/csi_system")

def run_migrations_offline() -> None:
    """オフラインマイグレーション実行"""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """オンラインマイグレーション実行"""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    connectable = create_engine(
        get_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
