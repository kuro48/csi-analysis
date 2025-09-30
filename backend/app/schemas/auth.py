"""
認証関連のPydanticスキーマ
"""

from pydantic import BaseModel
from typing import Optional
import uuid as uuid_pkg


class Token(BaseModel):
    """JWTトークンレスポンススキーマ"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒単位での有効期限
    user: 'UserResponse'


class TokenData(BaseModel):
    """JWTトークンペイロードスキーマ"""
    user_id: Optional[uuid_pkg.UUID] = None
    username: Optional[str] = None
    role: Optional[str] = None


# 循環インポートを防ぐための前方参照を解決
from .user import UserResponse
Token.model_rebuild()