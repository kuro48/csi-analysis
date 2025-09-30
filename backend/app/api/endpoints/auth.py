"""
認証関連エンドポイント
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import timedelta

from app.core.database import get_db
from app.core.security import create_access_token
from app.core.deps import get_current_user
from app.services.auth import AuthService
from app.schemas.user import UserCreate, UserLogin, UserResponse
from app.schemas.auth import Token
from app.core.config import settings

router = APIRouter()


@router.post("/register", response_model=UserResponse)
async def register(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    """
    ユーザー登録
    """
    # ユーザー名の重複チェック
    if AuthService.get_user_by_username(db, user_data.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="このユーザー名は既に使用されています"
        )

    # メールアドレスの重複チェック
    if AuthService.get_user_by_email(db, user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="このメールアドレスは既に使用されています"
        )

    # ユーザー作成
    user = AuthService.create_user(db, user_data)

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role="user",  # デフォルトロール
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at
    )


@router.post("/login", response_model=Token)
async def login(
    user_credentials: UserLogin,
    db: Session = Depends(get_db)
):
    """
    ユーザーログイン
    """
    # ユーザー認証
    user = AuthService.authenticate_user(
        db, user_credentials.username, user_credentials.password
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ユーザー名またはパスワードが正しくありません",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 最終ログイン時刻を更新
    AuthService.update_last_login(db, user)

    # アクセストークン生成
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=str(user.id), expires_delta=access_token_expires
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # 秒単位
        user=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            role="superuser" if user.is_superuser else "user",
            is_active=user.is_active,
            created_at=user.created_at,
            last_login_at=user.last_login_at
        )
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    トークン更新
    """
    # 新しいアクセストークン生成
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=str(current_user.id), expires_delta=access_token_expires
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # 秒単位
        user=UserResponse(
            id=current_user.id,
            username=current_user.username,
            email=current_user.email,
            role="superuser" if current_user.is_superuser else "user",
            is_active=current_user.is_active,
            created_at=current_user.created_at,
            last_login_at=current_user.last_login_at
        )
    )


@router.post("/logout")
async def logout(current_user = Depends(get_current_user)):
    """
    ユーザーログアウト
    """
    # JWTトークンはステートレスなので、クライアント側でトークンを削除
    # より高度な実装では、ブラックリストやRedisを使用してトークンを無効化
    return {"message": "正常にログアウトしました"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user = Depends(get_current_user)):
    """
    現在のユーザー情報を取得
    """
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role="superuser" if current_user.is_superuser else "user",
        is_active=current_user.is_active,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at
    )