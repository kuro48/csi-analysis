"""Protect research data and expensive operations when serving a public UI."""
import secrets

from fastapi import Header, HTTPException

from app.core.config import settings


def require_operator(authorization: str = Header(default="")):
    if not settings.PUBLIC_MODE and not settings.OPERATOR_API_TOKEN:
        return  # Explicit local research deployment only.
    expected = settings.OPERATOR_API_TOKEN
    if not expected or not secrets.compare_digest(authorization, f"Bearer {expected}"):
        raise HTTPException(401, "解析には運用者アクセストークンが必要です", headers={"WWW-Authenticate": "Bearer"})
