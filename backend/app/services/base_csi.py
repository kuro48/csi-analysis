"""
ベースCSI管理サービス
"""

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
    """ベースCSI管理サービス"""

    @staticmethod
    async def register_base_csi(
        db: Session,
        pcap_file_data: bytes,
        pcap_filename: str,
        register_info: BaseCSIRegister,
        storage_dir: str = "/data/base_csi"
    ) -> BaseCSI:
        """
        PCAPファイルからベースCSIを登録

        Args:
            db: データベースセッション
            pcap_file_data: PCAPファイルデータ
            pcap_filename: PCAPファイル名
            register_info: 登録情報
            user_id: ユーザーID
            storage_dir: 保存ディレクトリ

        Returns:
            登録されたベースCSI

        Raises:
            ValueError: PCAP解析に失敗した場合
        """
        try:
            # 保存ディレクトリ作成
            storage_path = Path(storage_dir)
            storage_path.mkdir(parents=True, exist_ok=True)

            # PCAPファイル保存
            pcap_id = uuid.uuid4()
            pcap_path = storage_path / f"base_{pcap_id}.pcap"

            with open(pcap_path, "wb") as f:
                f.write(pcap_file_data)

            logger.info(f"Base CSI PCAP saved: {pcap_path}")

            # PCAP解析（FFT + ウェーブレット変換）
            analyzer = PCAPAnalyzer()
            analysis_result = analyzer.analyze_pcap_file(str(pcap_path))
            fft_df = analysis_result["fft"]

            # freq_interval列をJSON化可能な形式に変換
            fft_df_copy = fft_df.copy()
            if 'freq_interval' in fft_df_copy.columns:
                fft_df_copy['freq_interval'] = fft_df_copy['freq_interval'].astype(str)

            # NaN値をNoneに変換（JSONのnullになる）
            import numpy as np
            fft_df_copy = fft_df_copy.replace({np.nan: None})

            # 有効期限設定（常に30日）
            expires_at = datetime.utcnow() + timedelta(days=30)

            # ベースCSIレコード作成
            base_csi = BaseCSI(
                id=pcap_id,
                name=register_info.name,
                fft_dataframe=fft_df_copy.to_dict(),
                source_pcap_path=str(pcap_path),
                source_pcap_size=len(pcap_file_data),
                expires_at=expires_at
            )

            db.add(base_csi)
            db.commit()
            db.refresh(base_csi)

            logger.info(f"Base CSI registered: {base_csi.id}, name={base_csi.name}")

            return base_csi

        except Exception as e:
            logger.error(f"Failed to register base CSI: {e}", exc_info=True)
            raise ValueError(f"ベースCSI登録に失敗しました: {str(e)}")

    @staticmethod
    def get_base_csi_list(
        db: Session,
        user_id: Optional[uuid.UUID] = None,
        include_expired: bool = False,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[BaseCSI], int]:
        """
        ベースCSI一覧取得

        Args:
            db: データベースセッション
            user_id: ユーザーID（Noneの場合は全ユーザー）
            include_expired: 有効期限切れを含めるか
            page: ページ番号
            page_size: ページサイズ

        Returns:
            (ベースCSIリスト, 総数)
        """
        query = db.query(BaseCSI)

        # ユーザーフィルタ
        if user_id is not None:
            query = query.filter(BaseCSI.user_id == user_id)

        # 有効期限フィルタ
        if not include_expired:
            query = query.filter(
                (BaseCSI.expires_at.is_(None)) | (BaseCSI.expires_at > datetime.utcnow())
            )

        # 総数取得
        total_count = query.count()

        # ページネーション
        offset = (page - 1) * page_size
        base_csis = query.order_by(BaseCSI.created_at.desc()).offset(offset).limit(page_size).all()

        return base_csis, total_count

    @staticmethod
    def get_base_csi_by_id(
        db: Session,
        base_csi_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None
    ) -> Optional[BaseCSI]:
        """
        ベースCSIをIDで取得

        Args:
            db: データベースセッション
            base_csi_id: ベースCSI ID
            user_id: ユーザーID（権限チェック用、Noneの場合はチェックしない）

        Returns:
            ベースCSI（見つからない場合はNone）
        """
        query = db.query(BaseCSI).filter(BaseCSI.id == base_csi_id)

        if user_id is not None:
            query = query.filter(BaseCSI.user_id == user_id)

        return query.first()

    @staticmethod
    def update_base_csi(
        db: Session,
        base_csi_id: uuid.UUID,
        update_info: BaseCSIUpdate,
        user_id: Optional[uuid.UUID] = None
    ) -> Optional[BaseCSI]:
        """
        ベースCSI情報を更新

        Args:
            db: データベースセッション
            base_csi_id: ベースCSI ID
            update_info: 更新情報
            user_id: ユーザーID

        Returns:
            更新されたベースCSI（見つからない場合はNone）
        """
        base_csi = BaseCSIService.get_base_csi_by_id(db, base_csi_id, user_id)

        if base_csi is None:
            return None

        # 更新
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
        user_id: Optional[uuid.UUID] = None
    ) -> bool:
        """
        ベースCSIを削除

        Args:
            db: データベースセッション
            base_csi_id: ベースCSI ID
            user_id: ユーザーID

        Returns:
            削除成功したかどうか
        """
        base_csi = BaseCSIService.get_base_csi_by_id(db, base_csi_id, user_id)

        if base_csi is None:
            return False

        # PCAPファイルを削除
        try:
            if base_csi.source_pcap_path:
                pcap_path = Path(base_csi.source_pcap_path)
                if pcap_path.exists():
                    pcap_path.unlink()
                    logger.info(f"Deleted base CSI PCAP file: {pcap_path}")
        except Exception as e:
            logger.warning(f"Failed to delete PCAP file: {e}")

        # データベースから削除
        db.delete(base_csi)
        db.commit()

        logger.info(f"Base CSI deleted: {base_csi_id}")

        return True

    @staticmethod
    def cleanup_expired_base_csis(db: Session) -> int:
        """
        有効期限切れのベースCSIを削除

        Args:
            db: データベースセッション

        Returns:
            削除したベースCSI数
        """
        expired_base_csis = db.query(BaseCSI).filter(
            BaseCSI.expires_at.isnot(None),
            BaseCSI.expires_at < datetime.utcnow()
        ).all()

        count = 0
        for base_csi in expired_base_csis:
            if BaseCSIService.delete_base_csi(db, base_csi.id):
                count += 1

        logger.info(f"Cleaned up {count} expired base CSIs")

        return count
