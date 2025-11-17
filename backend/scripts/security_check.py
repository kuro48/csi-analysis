#!/usr/bin/env python3
"""
セキュリティ設定チェックスクリプト

本番環境デプロイ前に実行して、必須の環境変数が適切に設定されているかを検証します。

Usage:
    python scripts/security_check.py
"""

import os
import sys
from typing import List, Dict, Tuple


# 必須環境変数の定義
REQUIRED_ENV_VARS = [
    "JWT_SECRET_KEY",
    "DATABASE_URL",
]

# 危険なデフォルト値の定義
DANGEROUS_DEFAULTS: Dict[str, List[str]] = {
    "JWT_SECRET_KEY": [
        "your-super-secret-jwt-key-change-in-production",
        "CHANGE_ME_TO_RANDOM_32_CHAR_STRING_IN_PRODUCTION",
        "",
    ],
    "DATABASE_URL": [
        "postgresql://csi_user:csi_password@localhost:5432/csi_system",
        "",
    ],
    "DATABASE_PASSWORD": [
        "csi_password",
        "password",
        "",
    ],
}

# セキュリティ推奨事項
SECURITY_RECOMMENDATIONS: Dict[str, str] = {
    "JWT_SECRET_KEY": "Generate with: python -c \"import secrets; print(secrets.token_urlsafe(32))\"",
    "DATABASE_PASSWORD": "Use a strong password with at least 16 characters",
    "BLOCKCHAIN_PRIVATE_KEY": "Never commit private keys to version control",
}


def check_env_var_exists(var_name: str) -> Tuple[bool, str]:
    """
    環境変数が設定されているかをチェック

    Returns:
        (is_ok, message): チェック結果とメッセージ
    """
    value = os.getenv(var_name)

    if not value:
        return False, f"❌ {var_name} is not set"

    return True, f"✅ {var_name} is set"


def check_dangerous_default(var_name: str) -> Tuple[bool, str]:
    """
    危険なデフォルト値が使用されていないかをチェック

    Returns:
        (is_ok, message): チェック結果とメッセージ
    """
    value = os.getenv(var_name, "")

    if var_name not in DANGEROUS_DEFAULTS:
        return True, f"✅ {var_name} has no known dangerous defaults"

    dangerous_values = DANGEROUS_DEFAULTS[var_name]

    if value in dangerous_values:
        return False, f"🚨 {var_name} is using a DANGEROUS default value: '{value}'"

    return True, f"✅ {var_name} is not using a dangerous default"


def check_jwt_secret_strength(secret: str) -> Tuple[bool, str]:
    """
    JWT秘密鍵の強度をチェック

    Returns:
        (is_ok, message): チェック結果とメッセージ
    """
    if len(secret) < 32:
        return False, f"⚠️ JWT_SECRET_KEY is too short ({len(secret)} chars). Recommended: 32+ chars"

    return True, f"✅ JWT_SECRET_KEY has sufficient length ({len(secret)} chars)"


def check_debug_mode() -> Tuple[bool, str]:
    """
    本番環境でDEBUGモードが無効になっているかをチェック

    Returns:
        (is_ok, message): チェック結果とメッセージ
    """
    debug = os.getenv("DEBUG", "false").lower() == "true"

    if debug:
        return False, "⚠️ WARNING: DEBUG mode is enabled. Disable for production!"

    return True, "✅ DEBUG mode is disabled"


def run_security_checks() -> bool:
    """
    すべてのセキュリティチェックを実行

    Returns:
        bool: すべてのチェックがパスした場合True
    """
    print("=" * 60)
    print("🔐 CSI Web Platform - Security Settings Check")
    print("=" * 60)
    print()

    all_passed = True
    warnings = []
    errors = []

    # 1. 必須環境変数の存在チェック
    print("📋 Checking required environment variables...")
    for var_name in REQUIRED_ENV_VARS:
        is_ok, message = check_env_var_exists(var_name)
        print(f"  {message}")

        if not is_ok:
            errors.append(message)
            all_passed = False

    print()

    # 2. 危険なデフォルト値のチェック
    print("🚨 Checking for dangerous default values...")
    for var_name in DANGEROUS_DEFAULTS.keys():
        is_ok, message = check_dangerous_default(var_name)
        print(f"  {message}")

        if not is_ok:
            errors.append(message)
            all_passed = False

    print()

    # 3. JWT秘密鍵の強度チェック
    print("🔑 Checking JWT secret key strength...")
    jwt_secret = os.getenv("JWT_SECRET_KEY", "")
    if jwt_secret:
        is_ok, message = check_jwt_secret_strength(jwt_secret)
        print(f"  {message}")

        if not is_ok:
            warnings.append(message)
    else:
        print("  ⏭️ Skipping (JWT_SECRET_KEY not set)")

    print()

    # 4. DEBUGモードのチェック
    print("🐛 Checking DEBUG mode...")
    is_ok, message = check_debug_mode()
    print(f"  {message}")

    if not is_ok:
        warnings.append(message)

    print()

    # 5. セキュリティ推奨事項の表示
    if errors or warnings:
        print("=" * 60)
        print("💡 Security Recommendations:")
        print("=" * 60)

        for var_name, recommendation in SECURITY_RECOMMENDATIONS.items():
            if var_name in [e.split()[1] for e in errors] or var_name in [w.split()[1] for w in warnings]:
                print(f"  • {var_name}: {recommendation}")

        print()

    # 6. 結果サマリー
    print("=" * 60)
    if all_passed and not warnings:
        print("✅ All security checks PASSED!")
        print("=" * 60)
        return True
    elif all_passed and warnings:
        print("⚠️ Security checks PASSED with WARNINGS")
        print("=" * 60)
        print("\nWarnings:")
        for warning in warnings:
            print(f"  {warning}")
        print("\nRecommendation: Address warnings before production deployment")
        return True
    else:
        print("❌ Security checks FAILED")
        print("=" * 60)
        print("\nCritical Errors:")
        for error in errors:
            print(f"  {error}")

        if warnings:
            print("\nWarnings:")
            for warning in warnings:
                print(f"  {warning}")

        print("\n🚨 Fix all errors before deploying to production!")
        return False


def main():
    """メイン関数"""
    # .envファイルを読み込む（python-dotenvがインストールされている場合）
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("📁 Loaded environment variables from .env file")
        print()
    except ImportError:
        print("⚠️ python-dotenv not installed. Using system environment variables only.")
        print("   Install with: pip install python-dotenv")
        print()

    # セキュリティチェック実行
    passed = run_security_checks()

    # 終了コードを設定
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
