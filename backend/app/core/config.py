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
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    TESTING: bool = os.getenv("TESTING", "false").lower() == "true"
    ENABLE_TEST_ENDPOINTS: bool = os.getenv("ENABLE_TEST_ENDPOINTS", "false").lower() == "true"

    # 研究モード設定
    # RESEARCH_MODE=true: CSIデータを保存（研究・分析用）
    # RESEARCH_MODE=false: CSIデータを保存せず、ZKP証明のみ保存（本番環境・プライバシー重視）
    RESEARCH_MODE: bool = os.getenv("RESEARCH_MODE", "true").lower() == "true"

    # ZKP設定
    ZKP_AUTO_GENERATE: bool = os.getenv("ZKP_AUTO_GENERATE", "true").lower() == "true"  # 自動ZKP証明生成
    # zkp_auto_compile は常に有効（環境変数を無視して強制ON）
    ZKP_AUTO_COMPILE: bool = True  # 自動コンパイル（初回起動時のみ）
    ZKP_DATA_RETENTION_HOURS: int = int(os.getenv("ZKP_DATA_RETENTION_HOURS", "0"))  # 0=即削除、>0=時間後削除

    # ブロックチェーン設定
    BLOCKCHAIN_AUTO_RECORD: bool = os.getenv("BLOCKCHAIN_AUTO_RECORD", "true").lower() == "true"  # CSIアップロード時に自動的にZKP証明をブロックチェーンに記録
    ETHEREUM_RPC_URL: str = os.getenv("ETHEREUM_RPC_URL", "http://localhost:8545")
    ZKPROOF_CONTRACT_ADDRESS: str = os.getenv("ZKPROOF_CONTRACT_ADDRESS", "")
    BLOCKCHAIN_PRIVATE_KEY: str = os.getenv("BLOCKCHAIN_PRIVATE_KEY", "")

    # データベース設定
    # SECURITY: DATABASE credentials must be set via environment variables
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    DATABASE_USER: str = os.getenv("DATABASE_USER", "")
    DATABASE_PASSWORD: str = os.getenv("DATABASE_PASSWORD", "")
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
    # SECURITY: JWT_SECRET_KEY must be set via environment variable
    # Never use default values in production
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440")  # 24時間
    )

    # CORS設定
    # 環境変数から読み込み、未設定時は開発環境用のローカルホストのみ許可
    ALLOWED_ORIGINS: List[str] = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",") if os.getenv("ALLOWED_ORIGINS") else [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # セキュリティ・レート制限設定
    RATE_LIMIT_LOGIN: str = os.getenv("RATE_LIMIT_LOGIN", "5/minute")
    RATE_LIMIT_API: str = os.getenv("RATE_LIMIT_API", "100/minute")
    RATE_LIMIT_UPLOAD: str = os.getenv("RATE_LIMIT_UPLOAD", "10/minute")

    # ログ設定
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


# 設定インスタンス
settings = Settings()

# セキュリティ検証: 本番環境では必須環境変数をチェック
def validate_security_settings():
    """
    セキュリティ上重要な環境変数が適切に設定されているかを検証
    本番環境では必須、開発環境では警告のみ
    """
    import sys

    required_vars = {
        "JWT_SECRET_KEY": settings.JWT_SECRET_KEY,
        "DATABASE_URL": settings.DATABASE_URL,
    }

    missing_vars = []
    for var_name, var_value in required_vars.items():
        if not var_value:
            missing_vars.append(var_name)

    if missing_vars:
        error_msg = f"🚨 SECURITY ERROR: Missing required environment variables: {', '.join(missing_vars)}"

        if not settings.DEBUG:
            # 本番環境では起動を停止
            print(error_msg)
            print("Set these environment variables before starting the application.")
            sys.exit(1)
        else:
            # 開発環境では警告のみ
            print(f"⚠️ WARNING: {error_msg}")
            print("This is acceptable in development, but MUST be fixed for production.")
    else:
        print("✅ Security settings validated successfully")

# アプリケーション起動時に検証を実行
validate_security_settings()
