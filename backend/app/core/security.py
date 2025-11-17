"""
セキュリティ関連のユーティリティ機能
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Union, Optional
import hashlib
from passlib.context import CryptContext
from jose import JWTError, jwt
from app.core.config import settings

# パスワードハッシュ化用のcontext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _prehash_password(password: str) -> str:
    """
    パスワードをSHA-256でプリハッシュ化
    bcryptの72バイト制限を回避し、任意の長さのパスワードをサポート
    """
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def create_access_token(
    subject: Union[str, Any], expires_delta: timedelta = None
) -> str:
    """JWTアクセストークンを生成"""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def verify_token(token: str) -> Optional[str]:
    """JWTトークンを検証してsubject（ユーザーID）を取得"""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
        return user_id
    except JWTError:
        return None


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    平文パスワードとハッシュ化パスワードの照合

    まずSHA-256でプリハッシュ化してから検証を試み、
    失敗した場合は後方互換性のため従来の方式も試みる
    """
    # 新方式: SHA-256プリハッシュ + bcrypt
    prehashed = _prehash_password(plain_password)
    try:
        if pwd_context.verify(prehashed, hashed_password):
            return True
    except Exception:
        pass

    # 後方互換性: 従来の方式（72バイト制限対応）
    if len(plain_password.encode('utf-8')) > 72:
        plain_password = plain_password.encode('utf-8')[:72].decode('utf-8', errors='ignore')
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    パスワードのハッシュ化

    SHA-256でプリハッシュ化してからbcryptを適用することで、
    bcryptの72バイト制限を回避し、任意の長さのパスワードをサポート
    """
    prehashed = _prehash_password(password)
    return pwd_context.hash(prehashed)