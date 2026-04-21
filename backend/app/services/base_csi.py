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
    def _serialize_dataframe(df):
        """DataFrame を JSON 保存可能な dict に変換"""
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
        storage_dir: str = "/data/base_csi"
    ) -> BaseCSI:
        """
        ベースCSIの初期レコードを作成し、PCAPファイルを保存する

        Args:
            db: データベースセッション
            pcap_file_data: PCAPファイルデータ
            pcap_filename: PCAPファイル名
            register_info: 登録情報
            user_id: ユーザーID
            storage_dir: 保存ディレクトリ

        Returns:
            作成されたベースCSI

        Raises:
            ValueError: 初期登録に失敗した場合
        """
        try:
            # 保存ディレクトリ作成
            storage_path = Path(storage_dir)
            storage_path.mkdir(parents=True, exist_ok=True)

            # 元の拡張子を保って保存し、後段のパーサ選択に使う
            pcap_id = uuid.uuid4()
            extension = Path(pcap_filename).suffix.lower() or ".pcap"
            pcap_path = storage_path / f"base_{pcap_id}{extension}"

            with open(pcap_path, "wb") as f:
                f.write(pcap_file_data)

            logger.info(f"Base CSI PCAP saved: {pcap_path}")

            # 有効期限設定（常に30日）
            expires_at = datetime.utcnow() + timedelta(days=30)

            base_csi = BaseCSI(
                id=pcap_id,
                name=register_info.name,
                fft_dataframe={},
                wavelet_dataframe=None,
                music_dataframe=None,
                source_pcap_path=str(pcap_path),
                source_pcap_size=len(pcap_file_data),
                status="processing",
                expires_at=expires_at
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
    async def register_base_csi(
        db: Session,
        pcap_file_data: bytes,
        pcap_filename: str,
        register_info: BaseCSIRegister,
        storage_dir: str = "/data/base_csi"
    ) -> BaseCSI:
        """
        後方互換のために残す同期登録ヘルパー。
        初期レコード作成後に、その場で解析まで完了させる。
        """
        base_csi = BaseCSIService.create_base_csi_record(
            db=db,
            pcap_file_data=pcap_file_data,
            pcap_filename=pcap_filename,
            register_info=register_info,
            storage_dir=storage_dir,
        )
        return BaseCSIService.process_base_csi_registration(db, base_csi.id)

    @staticmethod
    def process_base_csi_registration(
        db: Session,
        base_csi_id: uuid.UUID,
        parser_mode: str = "standard",
    ) -> Optional[BaseCSI]:
        """
        保存済みPCAPからベースCSI解析を実行し、レコードを完成させる
        """
        base_csi = db.query(BaseCSI).filter(BaseCSI.id == base_csi_id).first()

        if base_csi is None:
            logger.error(f"Base CSI not found for processing: {base_csi_id}")
            return None

        try:
            if not base_csi.source_pcap_path:
                raise ValueError("PCAPファイルパスが未設定です")

            analyzer = PCAPAnalyzer()
            source_path = base_csi.source_pcap_path
            inferred_parser_mode = parser_mode
            if Path(source_path).suffix.lower() == ".csi":
                inferred_parser_mode = "picoscenes"

            if inferred_parser_mode == "picoscenes":
                analysis_result = analyzer.analyze_csi_file_with_picoscenes(source_path)
            else:
                analysis_result = analyzer.analyze_pcap_file(source_path)
            fft_df = analysis_result["fft"]
            wavelet_df = analysis_result["wavelet"]
            music_df = analysis_result["music"]

            if fft_df.empty:
                raise ValueError("PCAP解析結果が空です")

            base_csi.fft_dataframe = BaseCSIService._serialize_dataframe(fft_df) or {}
            base_csi.wavelet_dataframe = BaseCSIService._serialize_dataframe(wavelet_df)
            base_csi.music_dataframe = BaseCSIService._serialize_dataframe(music_df)
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

        if status is not None:
            query = query.filter(BaseCSI.status == status)

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
        user_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
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

        if status is not None:
            query = query.filter(BaseCSI.status == status)

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
