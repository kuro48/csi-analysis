from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime
import re
import uuid as uuid_pkg


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    email: str = Field(..., max_length=255)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=100)

    @validator('username')
    def username_alphanumeric(cls, v):
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('ユーザー名は英数字とアンダースコアのみ使用可能です')
        return v

    @validator('password')
    def password_strength(cls, v):
        if not re.search(r'[A-Z]', v):
            raise ValueError('パスワードには大文字を含めてください')
        if not re.search(r'[a-z]', v):
            raise ValueError('パスワードには小文字を含めてください')
        if not re.search(r'\d', v):
            raise ValueError('パスワードには数字を含めてください')
        return v


class UserLogin(BaseModel):
    username: str
    password: str


class UserUpdate(BaseModel):
    email: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, min_length=8, max_length=100)
    is_active: Optional[bool] = None

    @validator('password', pre=True)
    def password_strength(cls, v):
        if v is not None:
            if not re.search(r'[A-Z]', v):
                raise ValueError('パスワードには大文字を含めてください')
            if not re.search(r'[a-z]', v):
                raise ValueError('パスワードには小文字を含めてください')
            if not re.search(r'\d', v):
                raise ValueError('パスワードには数字を含めてください')
        return v


class UserResponse(UserBase):
    id: uuid_pkg.UUID
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime]

    class Config:
        from_attributes = True
