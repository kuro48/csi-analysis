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
from app.services.pcap_analyzer import PcapAnalyzer

logger = logging.getLogger(__name__)


class BaseCSIService:
    """ベースCSI管理サービス"""

    @staticmethod
    async def register_base_csi(
        db: Session,
        pcap_file_data: bytes,
        pcap_filename: str,
        register_info: BaseCSIRegister,
        user_id: Optional[uuid.UUID] = None,
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

            # PCAP解析
            analyzer = PcapAnalyzer()
            fft_df = analyzer.analyze_pcap_file(str(pcap_path))

            # 呼吸周波数帯域から4次元ベクトルを抽出
            reference_vector, candidate_vectors = analyzer.prepare_zkp_vectors_from_fft(fft_df)

            # 呼吸解析結果の取得（簡易版 - 周波数帯域のピーク検出）
            breathing_freq_hz, confidence_score, best_subcarriers = BaseCSIService._analyze_breathing_pattern(
                fft_df
            )

            # 有効期限設定
            expires_at = None
            if register_info.expires_in_days is not None:
                expires_at = datetime.utcnow() + timedelta(days=register_info.expires_in_days)

            # ベースCSIレコード作成
            base_csi = BaseCSI(
                id=pcap_id,
                user_id=user_id,
                name=register_info.name,
                description=register_info.description,
                fft_dataframe=fft_df.to_dict(),
                breathing_frequency_hz=breathing_freq_hz,
                confidence_score=confidence_score,
                best_subcarrier_indices=best_subcarriers,
                reference_vector=reference_vector,
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
    def _analyze_breathing_pattern(fft_df) -> Tuple[float, float, List[int]]:
        """
        呼吸パターンを簡易解析

        Args:
            fft_df: FFT DataFrame

        Returns:
            (呼吸周波数Hz, 信頼度スコア, 最適サブキャリアインデックス[4])
        """
        import pandas as pd
        import numpy as np

        # 呼吸周波数帯域のフィルタ（0.15-0.4Hz）
        breathing_min = 0.15
        breathing_max = 0.4

        freq_col = 'frequency'
        breathing_mask = (fft_df[freq_col] >= breathing_min) & (fft_df[freq_col] <= breathing_max)
        breathing_df = fft_df[breathing_mask]

        if breathing_df.empty:
            return 0.0, 0.0, [0, 0, 0, 0]

        # サブキャリアごとのパワーを計算
        subcarrier_cols = [col for col in breathing_df.columns if col != freq_col]
        subcarrier_power = {}

        for sc in subcarrier_cols:
            power = breathing_df[sc].sum()
            subcarrier_power[sc] = power

        # 上位4つのサブキャリアを選択
        sorted_scs = sorted(subcarrier_power.items(), key=lambda x: x[1], reverse=True)[:4]
        best_subcarriers = [int(sc[0]) if sc[0].isdigit() else 0 for sc in sorted_scs]

        # 上位サブキャリアの平均振幅を計算
        top_sc_cols = [sc[0] for sc in sorted_scs]
        avg_amplitude = breathing_df[top_sc_cols].mean(axis=1)

        # ピーク周波数を検出
        peak_idx = avg_amplitude.idxmax()
        breathing_freq_hz = breathing_df.loc[peak_idx, freq_col]

        # 信頼度スコア（簡易版: ピーク/平均の比率）
        peak_amplitude = avg_amplitude.max()
        mean_amplitude = avg_amplitude.mean()
        confidence_score = min(peak_amplitude / (mean_amplitude + 1e-6), 1.0)

        return float(breathing_freq_hz), float(confidence_score), best_subcarriers

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

        if update_info.description is not None:
            base_csi.description = update_info.description

        if update_info.expires_in_days is not None:
            if update_info.expires_in_days > 0:
                base_csi.expires_at = datetime.utcnow() + timedelta(days=update_info.expires_in_days)
            else:
                base_csi.expires_at = None

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
