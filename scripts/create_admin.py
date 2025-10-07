#!/usr/bin/env python3
"""
初期管理者アカウント作成スクリプト
"""

import asyncio
import sys
import os
from pathlib import Path

# プロジェクトルートを追加
sys.path.append(str(Path(__file__).parent.parent / "backend"))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal, engine
from app.models.user import User
from app.core.security import get_password_hash
import uuid


def create_admin_user():
    """初期管理者アカウントを作成"""
    db = SessionLocal()

    try:
        # 既存の管理者をチェック
        existing_admin = db.query(User).filter(User.username == "admin").first()
        if existing_admin:
            print("❌ 管理者アカウント 'admin' は既に存在します")
            return False

        # 管理者アカウントの作成
        admin_user = User(
            id=uuid.uuid4(),
            username="admin",
            email="admin@csi-platform.local",
            hashed_password=get_password_hash("admin123"),
            is_active=True,
            role="superuser"
        )

        db.add(admin_user)
        db.commit()
        db.refresh(admin_user)

        print("✅ 管理者アカウントが作成されました:")
        print(f"   ユーザー名: {admin_user.username}")
        print(f"   パスワード: admin123")
        print(f"   メール: {admin_user.email}")
        print(f"   ロール: {admin_user.role}")
        print(f"   ID: {admin_user.id}")
        print()
        print("⚠️ セキュリティのため、初回ログイン後にパスワードを変更してください")

        return True

    except Exception as e:
        print(f"❌ 管理者アカウントの作成に失敗しました: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def create_sample_users():
    """サンプルユーザーアカウントを作成（開発/テスト用）"""
    db = SessionLocal()

    sample_users = [
        {
            "username": "user1",
            "email": "user1@example.com",
            "password": "user123",
            "role": "user"
        },
        {
            "username": "researcher1",
            "email": "researcher1@example.com",
            "password": "research123",
            "role": "researcher"
        }
    ]

    try:
        created_count = 0

        for user_data in sample_users:
            # 既存ユーザーをチェック
            existing_user = db.query(User).filter(User.username == user_data["username"]).first()
            if existing_user:
                print(f"⚠️ ユーザー '{user_data['username']}' は既に存在します")
                continue

            # ユーザーアカウントの作成
            user = User(
                id=uuid.uuid4(),
                username=user_data["username"],
                email=user_data["email"],
                hashed_password=get_password_hash(user_data["password"]),
                is_active=True,
                role=user_data["role"]
            )

            db.add(user)
            created_count += 1

            print(f"✅ ユーザー '{user_data['username']}' を作成しました")

        if created_count > 0:
            db.commit()
            print(f"📊 {created_count}件のサンプルユーザーを作成しました")

        return True

    except Exception as e:
        print(f"❌ サンプルユーザーの作成に失敗しました: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def main():
    """メイン処理"""
    print("🔧 初期アカウント作成スクリプト")
    print("=" * 40)

    # データベース接続テスト
    try:
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        print("✅ データベース接続: OK")
    except Exception as e:
        print(f"❌ データベース接続エラー: {e}")
        sys.exit(1)

    # 管理者アカウント作成
    print("\n👑 管理者アカウントの作成...")
    admin_created = create_admin_user()

    # 開発環境の場合はサンプルユーザーも作成
    env = os.getenv("NODE_ENV", "development")
    if env == "development":
        print("\n👥 サンプルユーザーの作成...")

        response = input("サンプルユーザーを作成しますか？ [y/N]: ").lower()
        if response in ['y', 'yes']:
            create_sample_users()
        else:
            print("⚠️ サンプルユーザーの作成をスキップしました")

    print("\n🎉 初期アカウント作成が完了しました！")

    if admin_created:
        print("\n🔗 次のステップ:")
        print("1. ブラウザで http://localhost:3000 にアクセス")
        print("2. ユーザー名 'admin'、パスワード 'admin123' でログイン")
        print("3. プロフィール設定でパスワードを変更")


if __name__ == "__main__":
    main()