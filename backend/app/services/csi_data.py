import uuid
from typing import List, Optional, Tuple, Any, Dict
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import desc
import logging
import tempfile

from app.models.csi_data import CSIData
from app.schemas.csi_data import CSIDataUpload, CSIDataFilter
from app.core.config import settings

logger = logging.getLogger(__name__)


class CSIDataService:

    @staticmethod
    async def upload_csi_data(
        db: Session,
        file_data: bytes,
        upload_info: CSIDataUpload,
    ) -> CSIData:
        """
        RESEARCH_MODE=true: 永続ディレクトリにファイルを保存（研究・分析用）
        RESEARCH_MODE=false: 一時ファイルとして保持し、バックグラウンド処理後に削除（本番環境）
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_extension = Path(upload_info.file_name).suffix
        unique_filename = f"{timestamp}_{uuid.uuid4().hex[:8]}{file_extension}"

        if settings.RESEARCH_MODE:
            upload_dir = Path("uploads") / "csi_data" / datetime.now().strftime("%Y/%m/%d")
            upload_dir.mkdir(parents=True, exist_ok=True)
            file_path = upload_dir / unique_filename
            logger.info(f"RESEARCH MODE: Saving CSI data to {file_path}")
        else:
            temp_file = tempfile.NamedTemporaryFile(
                mode='wb',
                suffix=file_extension,
                prefix=f"csi_{timestamp}_",
                delete=False,
            )
            file_path = Path(temp_file.name)
            logger.info(f"PRODUCTION MODE: Using temporary file {file_path}")

        try:
            with open(file_path, 'wb') as f:
                f.write(file_data)

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
        error_message: str = None,
    ) -> Optional[CSIData]:
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
    def get_csi_data_by_id(db: Session, csi_data_id: uuid.UUID) -> Optional[CSIData]:
        return db.query(CSIData).filter(CSIData.id == csi_data_id).first()

    @staticmethod
    def get_csi_data_list(
        db: Session,
        filters: CSIDataFilter,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[CSIData], int]:
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
        csi_data_list = (
            query.order_by(desc(CSIData.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return csi_data_list, total_count

    @staticmethod
    async def delete_csi_data(db: Session, csi_data_id: uuid.UUID) -> bool:
        csi_data = CSIDataService.get_csi_data_by_id(db, csi_data_id)
        if not csi_data:
            return False

        if csi_data.file_path and Path(csi_data.file_path).exists():
            try:
                Path(csi_data.file_path).unlink()
            except Exception as e:
                logger.warning(f"Failed to delete file {csi_data.file_path}: {e}")

        db.delete(csi_data)
        db.commit()
        return True
