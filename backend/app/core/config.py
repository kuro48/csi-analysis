"""
アプリケーション設定管理
"""

import os
from typing import List
from dotenv import load_dotenv

# 環境変数読み込み
load_dotenv()


class Settings:
    """アプリケーション設定"""

    # アプリケーション基本設定
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "CSI Respiratory Monitoring System")
    VERSION: str = os.getenv("VERSION", "2.5.0")
    DESCRIPTION: str = os.getenv(
        "DESCRIPTION",
        "Wi-Fi CSI based respiratory monitoring platform"
    )
    API_V2_PREFIX: str = os.getenv("API_V2_PREFIX", "/api/v2")

    # デバッグ・開発設定
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"
    TESTING: bool = os.getenv("TESTING", "false").lower() == "true"

    # データベース設定
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://csi_user:csi_password@localhost:5432/csi_system"
    )
    DATABASE_USER: str = os.getenv("DATABASE_USER", "csi_user")
    DATABASE_PASSWORD: str = os.getenv("DATABASE_PASSWORD", "csi_password")
    DATABASE_HOST: str = os.getenv("DATABASE_HOST", "localhost")
    DATABASE_PORT: int = int(os.getenv("DATABASE_PORT", "5432"))
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "csi_system")

    # Redis設定
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")

    # キャッシュ設定
    CACHE_ENABLED: bool = os.getenv("CACHE_ENABLED", "true").lower() == "true"
    CACHE_DEFAULT_TTL: int = int(os.getenv("CACHE_DEFAULT_TTL", "300"))  # 5分
    CACHE_DEVICE_TTL: int = int(os.getenv("CACHE_DEVICE_TTL", "600"))    # 10分
    CACHE_ANALYSIS_TTL: int = int(os.getenv("CACHE_ANALYSIS_TTL", "120")) # 2分
    CACHE_SESSION_TTL: int = int(os.getenv("CACHE_SESSION_TTL", "1800"))  # 30分

    # JWT設定
    JWT_SECRET_KEY: str = os.getenv(
        "JWT_SECRET_KEY",
        "your-super-secret-jwt-key-change-in-production"
    )
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440")  # 24時間
    )

    # CORS設定
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://192.168.101.168:3000",
        "http://192.168.101.40:3000",
        "*"  # エッジデバイスからのアクセスを許可
    ]

    # IPFS設定（既存システム連携用）
    IPFS_HOST: str = os.getenv("IPFS_HOST", "localhost")
    IPFS_PORT: int = int(os.getenv("IPFS_PORT", "5001"))
    IPFS_GATEWAY_PORT: int = int(os.getenv("IPFS_GATEWAY_PORT", "8080"))

    # Blockchain設定（既存システム連携用）
    BLOCKCHAIN_NODE_HOST: str = os.getenv("BLOCKCHAIN_NODE_HOST", "localhost")
    BLOCKCHAIN_NODE_PORT: int = int(os.getenv("BLOCKCHAIN_NODE_PORT", "9000"))
    ETHEREUM_RPC_URL: str = os.getenv(
        "ETHEREUM_RPC_URL",
        "http://localhost:8545"
    )

    # セキュリティ・レート制限設定
    RATE_LIMIT_LOGIN: str = os.getenv("RATE_LIMIT_LOGIN", "5/minute")
    RATE_LIMIT_API: str = os.getenv("RATE_LIMIT_API", "100/minute")
    RATE_LIMIT_UPLOAD: str = os.getenv("RATE_LIMIT_UPLOAD", "10/minute")

    # ログ設定
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "WARNING")


# 設定インスタンス
settings = Settings()