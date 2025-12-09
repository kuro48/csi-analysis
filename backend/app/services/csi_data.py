"""
CSIデータ管理サービス
"""

import os
import uuid
from typing import List, Optional, Tuple, Any, Dict
from datetime import datetime, timedelta
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, asc, func
import json
import logging

from app.models.csi_data import CSIData, Session as DataSession
from app.schemas.csi_data import (
    CSIDataUpload, CSIDataResponse, CSIDataFilter,
    SessionCreate, SessionUpdate, ProcessingStatus
)
from app.services.pcap_analyzer import pcap_analyzer

logger = logging.getLogger(__name__)


class CSIDataService:
    """CSIデータ管理サービス"""

    @staticmethod
    async def upload_csi_data(
        db: Session,
        file_data: bytes,
        upload_info: CSIDataUpload,
        user_id: uuid.UUID
    ) -> CSIData:
        """CSIデータアップロード処理"""

        # ファイル保存処理
        upload_dir = Path("uploads") / "csi_data"  / datetime.now().strftime("%Y/%m/%d")
        upload_dir.mkdir(parents=True, exist_ok=True)

        # ユニークなファイル名生成
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_extension = Path(upload_info.file_name).suffix
        unique_filename = f"{timestamp}_{uuid.uuid4().hex[:8]}{file_extension}"
        file_path = upload_dir / unique_filename

        try:
            # ファイル保存
            with open(file_path, 'wb') as f:
                f.write(file_data)

            # PCAPファイルの場合は解析処理を実行
            raw_data = None
            processed_data = None

            if file_extension.lower() == '.pcap':
                try:
                    logger.info(f"Analyzing PCAP file: {file_path}")
                    analysis_result = pcap_analyzer.analyze_pcap_file(str(file_path))
                    raw_data = analysis_result.get('csi_packets')
                    processed_data = analysis_result.get('time_series')

                    logger.info(f"PCAP analysis completed: {len(raw_data) if raw_data else 0} CSI packets found")

                except Exception as e:
                    logger.error(f"PCAP analysis failed: {e}")
                    # 解析失敗でも継続（ファイルは保存される）

            # データベースレコード作成
            csi_data = CSIData(
                session_id=upload_info.session_id,
                raw_data=raw_data if raw_data is None else json.dumps(raw_data) if not isinstance(raw_data, str) else raw_data,
                processed_data=processed_data if processed_data is None else json.dumps(processed_data) if not isinstance(processed_data, str) else processed_data,
                file_path=str(file_path),
                file_size=len(file_data),
                status="processed" if processed_data else "received",
            )

            db.add(csi_data)
            db.commit()
            db.refresh(csi_data)

            # 呼吸解析タスクをキューに登録
            from app.services.task_queue import task_queue, TaskPriority
            try:
                task_id = await task_queue.enqueue_task(
                    "csi_breathing_analysis",
                    {
                        "csi_data_id": str(csi_data.id),
                        "analysis_params": {}
                    },
                    priority=TaskPriority.NORMAL
                )
                logger.info(f"Breathing analysis task queued: {task_id} for CSI data {csi_data.id}")
            except Exception as e:
                logger.warning(f"Failed to queue breathing analysis task: {e}")

            logger.info(f"CSI data uploaded successfully: {csi_data.id}")
            return csi_data

        except Exception as e:
            # エラー時はファイルを削除
            if file_path.exists():
                file_path.unlink()
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
    async def delete_csi_data(
        db: Session,
        csi_data_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> bool:
        """CSIデータ削除"""
        csi_data = CSIDataService.get_csi_data_by_id(db, csi_data_id, user_id)
        if not csi_data:
            return False

        # IPFS削除処理（現在無効化 - 再有効化する場合は csi_data_ipfs.py を参照）
        # --- IPFS削除処理をコメントアウト（将来の再利用のため保持） ---
        # if csi_data.ipfs_hash:
        #     from app.services.csi_data_ipfs import delete_csi_data_from_ipfs
        #     await delete_csi_data_from_ipfs(csi_data.ipfs_hash)
        # --- ここまで ---

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
        session_data: SessionCreate,
        user_id: uuid.UUID
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
        session_id: uuid.UUID,
        user_id: uuid.UUID
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