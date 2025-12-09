"""
認証関連のサービス機能
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.schemas.user import UserCreate


class AuthService:
    """認証サービス"""

    @staticmethod
    def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
        """ユーザー認証"""
        user = db.query(User).filter(and_(User.username == username, User.is_active == True)).first()

        if not user:
            return None
        if not verify_password(password, user.password_hash):
            return None

        return user

    @staticmethod
    def create_user(db: Session, user_create: UserCreate) -> User:
        """新規ユーザー作成"""
        # パスワードをハッシュ化
        hashed_password = get_password_hash(user_create.password)

        # ユーザーオブジェクト作成
        db_user = User(
            username=user_create.username,
            email=user_create.email,
            password_hash=hashed_password,
            is_active=True,
            is_superuser=False,
        )

        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        return db_user

    @staticmethod
    def get_user_by_username(db: Session, username: str) -> Optional[User]:
        """ユーザー名でユーザーを取得"""
        return db.query(User).filter(User.username == username).first()

    @staticmethod
    def get_user_by_email(db: Session, email: str) -> Optional[User]:
        """メールアドレスでユーザーを取得"""
        return db.query(User).filter(User.email == email).first()

    @staticmethod
    def update_last_login(db: Session, user: User) -> User:
        """最終ログイン時刻を更新"""
        user.last_login_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        return user
