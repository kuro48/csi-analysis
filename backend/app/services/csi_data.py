"""
CSIデータ管理サービス
"""

import os
import uuid
from typing import List, Optional, Tuple, Any, Dict
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, func
import logging
import tempfile

from app.models.csi_data import CSIData, Session as DataSession
from app.schemas.csi_data import (
    CSIDataUpload, CSIDataResponse, CSIDataFilter,
    SessionCreate
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class CSIDataService:
    """CSIデータ管理サービス"""

    @staticmethod
    async def upload_csi_data(
        db: Session,
        file_data: bytes,
        upload_info: CSIDataUpload,
    ) -> CSIData:
        """
        CSIデータアップロード処理

        RESEARCH_MODE=true: CSIデータをファイルとして保存（研究・分析用）
        RESEARCH_MODE=false: CSIデータを保存せず、解析とZKP証明のみ保存（本番環境・プライバシー重視）
        """

        # ファイル名とパス設定
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_extension = Path(upload_info.file_name).suffix
        unique_filename = f"{timestamp}_{uuid.uuid4().hex[:8]}{file_extension}"

        # 研究モードの場合は永続的なディレクトリ、本番モードは一時ディレクトリ
        if settings.RESEARCH_MODE:
            # 研究モード: データを永続的に保存
            upload_dir = Path("uploads") / "csi_data" / datetime.now().strftime("%Y/%m/%d")
            upload_dir.mkdir(parents=True, exist_ok=True)
            file_path = upload_dir / unique_filename
            logger.info(f"RESEARCH MODE: Saving CSI data to {file_path}")
        else:
            # 本番モード: 一時ファイルとして保持し、バックグラウンド処理後に削除
            temp_file = tempfile.NamedTemporaryFile(
                mode='wb',
                suffix=file_extension,
                prefix=f"csi_{timestamp}_",
                delete=False
            )
            file_path = Path(temp_file.name)
            logger.info(f"PRODUCTION MODE: Using temporary file {file_path} (will be deleted after background processing)")

        try:
            # ファイル保存
            with open(file_path, 'wb') as f:
                f.write(file_data)

            # データベースレコード作成
            device_id = None
            if isinstance(upload_info.metadata, dict):
                device_id = upload_info.metadata.get("device_id")

            csi_data = CSIData(
                session_id=upload_info.session_id,
                raw_data=None,
                processed_data=None,
                file_path=str(file_path),
                file_size=len(file_data),
                device_id=device_id,
                status="uploaded",
            )

            db.add(csi_data)
            db.commit()
            db.refresh(csi_data)

            logger.info(f"CSI data uploaded successfully: {csi_data.id} (RESEARCH_MODE={settings.RESEARCH_MODE})")
            return csi_data

        except Exception as e:
            # エラー時はファイルを削除
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup file {file_path}: {cleanup_error}")
            raise e

    @staticmethod
    async def update_processing_status(
        db: Session,
        csi_data_id: uuid.UUID,
        status: str,
        processed_data: Dict[str, Any] = None,
        error_message: str = None
    ) -> Optional[CSIData]:
        """処理状態更新"""
        csi_data = db.query(CSIData).filter(CSIData.id == csi_data_id).first()
        if not csi_data:
            return None

        csi_data.status = status
        if processed_data:
            csi_data.processed_data = processed_data

        db.commit()
        db.refresh(csi_data)

        return csi_data

    @staticmethod
    def get_csi_data_by_id(
        db: Session,
        csi_data_id: uuid.UUID
    ) -> Optional[CSIData]:
        """CSIデータをIDで取得"""
        return db.query(CSIData).filter(CSIData.id == csi_data_id).first()

    @staticmethod
    def get_csi_data_list(
        db: Session,
        filters: CSIDataFilter,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[CSIData], int]:
        """CSIデータ一覧取得（簡易フィルタのみ）"""
        query = db.query(CSIData)

        if filters.session_id:
            query = query.filter(CSIData.session_id == filters.session_id)
        if filters.status and filters.status != "all":
            query = query.filter(CSIData.status == filters.status)
        if filters.start_date:
            query = query.filter(CSIData.created_at >= filters.start_date)
        if filters.end_date:
            query = query.filter(CSIData.created_at <= filters.end_date)

        total_count = query.count()
        csi_data_list = query.order_by(desc(CSIData.created_at)).offset((page - 1) * page_size).limit(page_size).all()
        return csi_data_list, total_count

    @staticmethod
    async def delete_csi_data(
        db: Session,
        csi_data_id: uuid.UUID
    ) -> bool:
        """CSIデータ削除"""
        csi_data = CSIDataService.get_csi_data_by_id(db, csi_data_id)
        if not csi_data:
            return False

        # ローカルファイル削除
        if csi_data.file_path and Path(csi_data.file_path).exists():
            try:
                Path(csi_data.file_path).unlink()
            except Exception as e:
                logger.warning(f"Failed to delete file {csi_data.file_path}: {e}")

        # データベースレコード削除
        db.delete(csi_data)
        db.commit()
        return True
class SessionService:
    """データ収集セッション管理サービス"""

    @staticmethod
    async def create_session(
        db: Session,
        session_data: SessionCreate
    ) -> DataSession:
        """セッション作成"""

        session = DataSession(
            session_name=session_data.session_name,
            start_time=session_data.start_time,
            status="active",
            metadata=session_data.metadata
        )

        db.add(session)
        db.commit()
        db.refresh(session)


        return session

    @staticmethod
    async def end_session(
        db: Session,
        session_id: uuid.UUID
    ) -> Optional[DataSession]:
        """セッション終了"""
        session = db.query(DataSession).filter(
            and_(
                DataSession.id == session_id,
            )
        ).first()

        if not session:
            return None

        end_time = datetime.utcnow()
        session.end_time = end_time
        session.status = "completed"

        if session.start_time:
            session.duration = int((end_time - session.start_time).total_seconds())

        db.commit()
        db.refresh(session)

        return session
