"""
データベース設定・接続管理
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 環境変数読み込み
load_dotenv()

# データベースURL構築
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://csi_user:csi_password@localhost:5432/csi_system")

# SQLAlchemy エンジン作成
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=os.getenv("DEBUG", "false").lower() == "true",  # DEBUGモードでSQL表示
)

# セッション作成
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ベースクラス
Base = declarative_base()


def get_db():
    """
    データベースセッション取得（FastAPI Dependency用）
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    データベース初期化（テーブル作成）
    """
    import app.models  # モデルをインポートしてテーブル作成

    Base.metadata.create_all(bind=engine)
