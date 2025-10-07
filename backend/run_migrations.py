"""
データベースマイグレーション実行スクリプト
"""

import os
import sys
from alembic.config import Config
from alembic import command

def run_migrations():
    """マイグレーション実行"""
    # 現在のディレクトリをbackendに設定
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # Alembic設定
    alembic_cfg = Config("alembic.ini")

    # 環境変数からデータベースURLを設定
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://csi_user:csi_password@postgres:5432/csi_system"
    )
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)

    print(f"Running migrations with database URL: {database_url}")

    try:
        # マイグレーション実行
        command.upgrade(alembic_cfg, "head")
        print("✅ Migration completed successfully!")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migrations()