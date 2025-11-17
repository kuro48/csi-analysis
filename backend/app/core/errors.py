"""
構造化エラーハンドリング

アプリケーション全体で一貫したエラー処理を提供
"""

from enum import Enum
from typing import Optional, Dict, Any
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
import uuid
import structlog


logger = structlog.get_logger()


class ErrorCode(str, Enum):
    """エラーコード定義"""

    # 認証関連 (AUTH_xxx)
    AUTH_FAILED = "AUTH_001"
    AUTH_INVALID_TOKEN = "AUTH_002"
    AUTH_TOKEN_EXPIRED = "AUTH_003"
    AUTH_INSUFFICIENT_PERMISSIONS = "AUTH_004"

    # バリデーション関連 (VAL_xxx)
    VAL_INVALID_INPUT = "VAL_001"
    VAL_MISSING_FIELD = "VAL_002"
    VAL_INVALID_FORMAT = "VAL_003"

    # データベース関連 (DB_xxx)
    DB_CONNECTION_ERROR = "DB_001"
    DB_QUERY_ERROR = "DB_002"
    DB_CONSTRAINT_VIOLATION = "DB_003"
    DB_NOT_FOUND = "DB_004"

    # ビジネスロジック関連 (BIZ_xxx)
    BIZ_DEVICE_OFFLINE = "BIZ_001"
    BIZ_ANALYSIS_FAILED = "BIZ_002"
    BIZ_INSUFFICIENT_DATA = "BIZ_003"

    # 外部サービス関連 (EXT_xxx)
    EXT_IPFS_ERROR = "EXT_001"
    EXT_BLOCKCHAIN_ERROR = "EXT_002"
    EXT_REDIS_ERROR = "EXT_003"

    # 内部エラー
    INTERNAL_ERROR = "INT_001"
    UNKNOWN_ERROR = "UNKNOWN"


class AppException(Exception):
    """アプリケーション基底例外クラス"""

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.request_id = str(uuid.uuid4())
        super().__init__(self.message)


class AuthenticationError(AppException):
    """認証エラー"""

    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            error_code=ErrorCode.AUTH_FAILED,
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
        )


class ValidationError(AppException):
    """バリデーションエラー"""

    def __init__(self, message: str = "Invalid input", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            error_code=ErrorCode.VAL_INVALID_INPUT,
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class NotFoundError(AppException):
    """リソース未検出エラー"""

    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            error_code=ErrorCode.DB_NOT_FOUND,
            message=f"{resource} not found",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"resource": resource, "id": resource_id},
        )


class DatabaseError(AppException):
    """データベースエラー"""

    def __init__(self, message: str = "Database error occurred", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            error_code=ErrorCode.DB_QUERY_ERROR,
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """アプリケーション例外ハンドラー"""

    # ログ記録（詳細情報含む）
    logger.error(
        "Application error",
        error_code=exc.error_code,
        message=exc.message,
        status_code=exc.status_code,
        request_id=exc.request_id,
        path=request.url.path,
        method=request.method,
        details=exc.details,
    )

    # クライアントには必要最小限の情報のみ返す
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            "request_id": exc.request_id,
            # 本番環境ではdetailsを返さない（セキュリティ対策）
            **({ "details": exc.details } if request.app.state.config.DEBUG else {}),
        },
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """一般例外ハンドラー（予期しないエラー用）"""

    request_id = str(uuid.uuid4())

    # ログ記録（詳細なエラー情報）
    logger.error(
        "Unexpected error",
        error=str(exc),
        error_type=type(exc).__name__,
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        exc_info=True,  # スタックトレースをログに記録
    )

    # クライアントには詳細を漏らさない
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error_code": ErrorCode.INTERNAL_ERROR,
            "message": "An internal error occurred. Please try again later.",
            "request_id": request_id,
        },
    )


def setup_error_handlers(app):
    """エラーハンドラーをアプリケーションに登録"""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
