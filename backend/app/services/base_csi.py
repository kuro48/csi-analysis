import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from pathlib import Path
from sqlalchemy.orm import Session

from app.models.base_csi import BaseCSI
from app.schemas.base_csi import BaseCSIRegister, BaseCSIUpdate
from app.services.pcap_analyzer import PCAPAnalyzer

logger = logging.getLogger(__name__)


class BaseCSIService:

    @staticmethod
    def _serialize_dataframe(df):
        if df is None or df.empty:
            return None
        df_copy = df.copy()
        if 'freq_interval' in df_copy.columns:
            df_copy['freq_interval'] = df_copy['freq_interval'].astype(str)
        import numpy as np
        df_copy = df_copy.replace({np.nan: None})
        return df_copy.to_dict()

    @staticmethod
    def create_base_csi_record(
        db: Session,
        pcap_file_data: bytes,
        pcap_filename: str,
        register_info: BaseCSIRegister,
        storage_dir: str = "/data/base_csi",
    ) -> BaseCSI:
        try:
            storage_path = Path(storage_dir)
            storage_path.mkdir(parents=True, exist_ok=True)

            # 拡張子を保って保存し、後段のパーサ選択に使う
            pcap_id = uuid.uuid4()
            extension = Path(pcap_filename).suffix.lower() or ".pcap"
            pcap_path = storage_path / f"base_{pcap_id}{extension}"

            with open(pcap_path, "wb") as f:
                f.write(pcap_file_data)

            logger.info(f"Base CSI PCAP saved: {pcap_path}")

            base_csi = BaseCSI(
                id=pcap_id,
                name=register_info.name,
                fft_dataframe={},
                wavelet_dataframe=None,
                music_dataframe=None,
                subcarrier_medians=None,
                source_pcap_path=str(pcap_path),
                source_pcap_size=len(pcap_file_data),
                status="processing",
                expires_at=datetime.utcnow() + timedelta(days=30),
            )

            db.add(base_csi)
            db.commit()
            db.refresh(base_csi)

            logger.info(f"Base CSI record created: {base_csi.id}, name={base_csi.name}")
            return base_csi

        except Exception as e:
            logger.error(f"Failed to create base CSI record: {e}", exc_info=True)
            raise ValueError(f"ベースCSI登録の初期化に失敗しました: {str(e)}")

    @staticmethod
    def process_base_csi_registration(
        db: Session,
        base_csi_id: uuid.UUID,
    ) -> Optional[BaseCSI]:
        base_csi = db.query(BaseCSI).filter(BaseCSI.id == base_csi_id).first()

        if base_csi is None:
            logger.error(f"Base CSI not found for processing: {base_csi_id}")
            return None

        try:
            if not base_csi.source_pcap_path:
                raise ValueError("CSIファイルパスが未設定です")

            analyzer = PCAPAnalyzer()
            analysis_result = analyzer.analyze_file(
                base_csi.source_pcap_path,
                include_wavelet=False,
                include_music=False,
                include_breathing=False,
            )

            fft_df = analysis_result["fft"]
            if fft_df.empty:
                raise ValueError("CSI解析結果が空です")

            base_csi.fft_dataframe = BaseCSIService._serialize_dataframe(fft_df) or {}
            base_csi.wavelet_dataframe = BaseCSIService._serialize_dataframe(analysis_result["wavelet"])
            base_csi.music_dataframe = BaseCSIService._serialize_dataframe(analysis_result["music"])
            base_csi.subcarrier_medians = analysis_result.get("subcarrier_medians") or {}
            base_csi.raw_signal_dataframe = analysis_result.get("raw_signal")
            base_csi.filtered_signal_dataframe = analysis_result.get("filtered_signal")
            base_csi.status = "completed"
            base_csi.error_message = None
            db.commit()
            db.refresh(base_csi)

            logger.info(f"Base CSI registered: {base_csi.id}, name={base_csi.name}")
            return base_csi

        except Exception as e:
            logger.error(f"Failed to process base CSI: {e}", exc_info=True)
            base_csi.status = "error"
            base_csi.error_message = str(e)[:1000]
            db.commit()
            db.refresh(base_csi)
            return base_csi

    @staticmethod
    def get_base_csi_list(
        db: Session,
        user_id: Optional[uuid.UUID] = None,
        include_expired: bool = False,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[BaseCSI], int]:
        query = db.query(BaseCSI)

        if user_id is not None:
            query = query.filter(BaseCSI.user_id == user_id)

        if not include_expired:
            query = query.filter(
                (BaseCSI.expires_at.is_(None)) | (BaseCSI.expires_at > datetime.utcnow())
            )

        if status is not None:
            query = query.filter(BaseCSI.status == status)

        total_count = query.count()
        base_csis = query.order_by(BaseCSI.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return base_csis, total_count

    @staticmethod
    def get_base_csi_by_id(
        db: Session,
        base_csi_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
    ) -> Optional[BaseCSI]:
        query = db.query(BaseCSI).filter(BaseCSI.id == base_csi_id)

        if user_id is not None:
            query = query.filter(BaseCSI.user_id == user_id)

        if status is not None:
            query = query.filter(BaseCSI.status == status)

        return query.first()

    @staticmethod
    def update_base_csi(
        db: Session,
        base_csi_id: uuid.UUID,
        update_info: BaseCSIUpdate,
        user_id: Optional[uuid.UUID] = None,
    ) -> Optional[BaseCSI]:
        base_csi = BaseCSIService.get_base_csi_by_id(db, base_csi_id, user_id)
        if base_csi is None:
            return None

        if update_info.name is not None:
            base_csi.name = update_info.name

        db.commit()
        db.refresh(base_csi)
        logger.info(f"Base CSI updated: {base_csi.id}")
        return base_csi

    @staticmethod
    def delete_base_csi(
        db: Session,
        base_csi_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
    ) -> bool:
        base_csi = BaseCSIService.get_base_csi_by_id(db, base_csi_id, user_id)
        if base_csi is None:
            return False

        try:
            if base_csi.source_pcap_path:
                pcap_path = Path(base_csi.source_pcap_path)
                if pcap_path.exists():
                    pcap_path.unlink()
                    logger.info(f"Deleted base CSI PCAP file: {pcap_path}")
        except Exception as e:
            logger.warning(f"Failed to delete PCAP file: {e}")

        db.delete(base_csi)
        db.commit()
        logger.info(f"Base CSI deleted: {base_csi_id}")
        return True

    @staticmethod
    def cleanup_expired_base_csis(db: Session) -> int:
        expired_base_csis = db.query(BaseCSI).filter(
            BaseCSI.expires_at.isnot(None),
            BaseCSI.expires_at < datetime.utcnow(),
        ).all()

        count = sum(1 for bc in expired_base_csis if BaseCSIService.delete_base_csi(db, bc.id))
        logger.info(f"Cleaned up {count} expired base CSIs")
        return count
