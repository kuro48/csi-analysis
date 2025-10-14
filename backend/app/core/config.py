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

    # Blockchain設定（拡張版）
    BLOCKCHAIN_ENABLED: bool = os.getenv("BLOCKCHAIN_ENABLED", "true").lower() == "true"
    BLOCKCHAIN_NODE_HOST: str = os.getenv("BLOCKCHAIN_NODE_HOST", "ganache")
    BLOCKCHAIN_NODE_PORT: int = int(os.getenv("BLOCKCHAIN_NODE_PORT", "8545"))
    ETHEREUM_RPC_URL: str = os.getenv(
        "ETHEREUM_RPC_URL",
        "http://ganache:8545"  # Docker環境用
    )

    # スマートコントラクト設定
    CONTRACT_ADDRESS: str = os.getenv(
        "CONTRACT_ADDRESS",
        "0x0000000000000000000000000000000000000000"  # デプロイ後に更新
    )
    CONTRACT_ABI_PATH: str = os.getenv(
        "CONTRACT_ABI_PATH",
        "/app/contracts/build/CSIDataRegistry.json"
    )

    # アカウント設定（注意: 本番環境では環境変数から読み込む）
    BLOCKCHAIN_ACCOUNT_ADDRESS: str = os.getenv(
        "BLOCKCHAIN_ACCOUNT_ADDRESS",
        "0x90F8bf6A479f320ead074411a4B0e7944Ea8c9C1"  # Ganache default account
    )
    BLOCKCHAIN_PRIVATE_KEY: str = os.getenv(
        "BLOCKCHAIN_PRIVATE_KEY",
        "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d"  # Ganache default private key (開発用のみ)
    )

    # ガス設定
    GAS_LIMIT: int = int(os.getenv("GAS_LIMIT", "3000000"))
    GAS_PRICE: int = int(os.getenv("GAS_PRICE", "20000000000"))  # 20 Gwei

    # トランザクションタイムアウト
    TX_TIMEOUT: int = int(os.getenv("TX_TIMEOUT", "120"))  # 秒

    # セキュリティ・レート制限設定
    RATE_LIMIT_LOGIN: str = os.getenv("RATE_LIMIT_LOGIN", "5/minute")
    RATE_LIMIT_API: str = os.getenv("RATE_LIMIT_API", "100/minute")
    RATE_LIMIT_UPLOAD: str = os.getenv("RATE_LIMIT_UPLOAD", "10/minute")

    # ログ設定
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


# 設定インスタンス
settings = Settings()