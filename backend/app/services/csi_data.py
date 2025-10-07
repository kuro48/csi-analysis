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
from app.models.device import Device
from app.schemas.csi_data import (
    CSIDataUpload, CSIDataResponse, CSIDataFilter,
    SessionCreate, SessionUpdate, ProcessingStatus
)
from app.services.websocket import realtime_service
from app.services.ipfs import ipfs_service
from app.services.pcap_analyzer import pcap_analyzer
from app.services.realtime_csi_analyzer import realtime_analyzer

logger = logging.getLogger(__name__)


class CSIDataService:
    """CSIデータ管理サービス"""

    @staticmethod
    async def upload_csi_data(
        db: Session,
        device_id: str,
        file_data: bytes,
        upload_info: CSIDataUpload,
        user_id: uuid.UUID
    ) -> CSIData:
        """CSIデータアップロード処理"""

        # デバイスの存在確認と所有者チェック
        device = db.query(Device).filter(
            and_(
                Device.device_id == device_id,
                Device.owner_id == user_id
            )
        ).first()

        if not device:
            raise ValueError(f"デバイス '{device_id}' が見つからないか、アクセス権限がありません")

        # ファイル保存処理
        upload_dir = Path("uploads") / "csi_data" / device_id / datetime.now().strftime("%Y/%m/%d")
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

            # IPFSに統合アップロード（メタデータ含む）
            ipfs_hash = None
            try:
                # メタデータ構築
                csi_metadata = {
                    "device_id": device_id,
                    "session_id": upload_info.session_id,
                    "collection_start_time": upload_info.collection_start_time.isoformat() if upload_info.collection_start_time else None,
                    "collection_duration": upload_info.collection_duration,
                    "original_filename": upload_info.file_name,
                    "file_size": len(file_data),
                    "upload_timestamp": datetime.now().isoformat(),
                    "user_id": str(user_id),
                    "custom_metadata": upload_info.metadata
                }

                # IPFS統合アップロード
                ipfs_result = await ipfs_service.upload_csi_data_with_metadata(
                    file_data,
                    csi_metadata,
                    filename=upload_info.file_name
                )
                ipfs_hash = ipfs_result["combined_hash"]
                logger.info(f"CSI data package uploaded to IPFS: {ipfs_hash}")
            except Exception as e:
                logger.warning(f"IPFS upload failed, continuing without IPFS: {e}")

            # PCAPファイルの場合は解析処理を実行
            raw_data = None
            processed_data = None

            if file_extension.lower() == '.pcap':
                try:
                    logger.info(f"Analyzing PCAP file: {file_path}")
                    analysis_result = pcap_analyzer.analyze_pcap_file(str(file_path))
                    raw_data = analysis_result.get('csi_packets')
                    processed_data = analysis_result.get('time_series')

                    # 解析成功の通知
                    await realtime_service.broadcast_device_status_update(
                        device_id,
                        {
                            "type": "pcap_analysis_completed",
                            "csi_data_id": None,  # まだ作成前
                            "packets_found": len(raw_data) if raw_data else 0,
                            "analysis_metadata": analysis_result.get('metadata')
                        }
                    )
                    logger.info(f"PCAP analysis completed: {len(raw_data) if raw_data else 0} CSI packets found")

                except Exception as e:
                    logger.error(f"PCAP analysis failed: {e}")
                    # 解析失敗でも継続（ファイルは保存される）

            # データベースレコード作成
            csi_data = CSIData(
                device_id=device.id,
                session_id=upload_info.session_id,
                raw_data=raw_data,
                processed_data=processed_data,
                file_path=str(file_path),
                file_size=len(file_data),
                status="processed" if processed_data else "received",
                ipfs_hash=ipfs_hash
            )

            db.add(csi_data)
            db.commit()
            db.refresh(csi_data)

            # リアルタイムCSI解析を実行
            try:
                analysis_result = await realtime_analyzer.analyze_csi_data(device_id, file_data)
                if analysis_result:
                    logger.info(f"Real-time CSI analysis completed for device {device_id}")
            except Exception as e:
                logger.error(f"Real-time CSI analysis failed for device {device_id}: {e}")

            # WebSocketでアップロード完了を通知
            await realtime_service.broadcast_device_status_update(
                device_id,
                {
                    "type": "csi_data_uploaded",
                    "csi_data_id": str(csi_data.id),
                    "file_name": upload_info.file_name,
                    "file_size": len(file_data),
                    "status": "received",
                    "ipfs_hash": ipfs_hash
                }
            )

            logger.info(f"CSI data uploaded successfully: {csi_data.id} for device {device_id}")
            return csi_data

        except Exception as e:
            # エラー時はファイルを削除
            if file_path.exists():
                file_path.unlink()
            raise e

    @staticmethod
    def get_csi_data_list(
        db: Session,
        user_id: uuid.UUID,
        filters: CSIDataFilter = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[CSIData], int]:
        """CSIデータ一覧取得"""

        query = db.query(CSIData).join(Device).filter(Device.owner_id == user_id)

        # フィルター適用
        if filters:
            if filters.device_id:
                query = query.filter(Device.device_id == filters.device_id)
            if filters.session_id:
                query = query.filter(CSIData.session_id == filters.session_id)
            if filters.status and filters.status != "all":
                query = query.filter(CSIData.status == filters.status)
            if filters.start_date:
                query = query.filter(CSIData.created_at >= filters.start_date)
            if filters.end_date:
                query = query.filter(CSIData.created_at <= filters.end_date)

        # 総件数取得
        total_count = query.count()

        # ページネーション適用
        offset = (page - 1) * page_size
        csi_data_list = query.order_by(desc(CSIData.created_at)).offset(offset).limit(page_size).all()

        return csi_data_list, total_count

    @staticmethod
    def get_csi_data_by_id(
        db: Session,
        csi_data_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> Optional[CSIData]:
        """特定CSIデータ取得"""
        return db.query(CSIData).join(Device).filter(
            and_(
                CSIData.id == csi_data_id,
                Device.owner_id == user_id
            )
        ).first()

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

        # WebSocketで状態更新を通知
        device = db.query(Device).filter(Device.id == csi_data.device_id).first()
        if device:
            await realtime_service.broadcast_device_status_update(
                device.device_id,
                {
                    "type": "csi_data_processing_update",
                    "csi_data_id": str(csi_data.id),
                    "status": status,
                    "error_message": error_message
                }
            )

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

        # IPFSからCSIデータパッケージ削除
        if csi_data.ipfs_hash:
            try:
                await ipfs_service.delete_csi_data_package(csi_data.ipfs_hash)
                logger.info(f"CSI data package deleted from IPFS: {csi_data.ipfs_hash}")
            except Exception as e:
                logger.warning(f"Failed to delete IPFS package {csi_data.ipfs_hash}: {e}")

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

    @staticmethod
    def get_device_csi_stats(
        db: Session,
        device_id: str,
        user_id: uuid.UUID,
        days: int = 7
    ) -> Dict[str, Any]:
        """デバイスのCSI統計情報取得"""
        device = db.query(Device).filter(
            and_(
                Device.device_id == device_id,
                Device.owner_id == user_id
            )
        ).first()

        if not device:
            return {}

        # 期間指定
        start_date = datetime.utcnow() - timedelta(days=days)

        # 基本統計
        total_data = db.query(CSIData).filter(
            and_(
                CSIData.device_id == device.id,
                CSIData.created_at >= start_date
            )
        ).count()

        status_stats = db.query(
            CSIData.status,
            func.count(CSIData.id).label('count')
        ).filter(
            and_(
                CSIData.device_id == device.id,
                CSIData.created_at >= start_date
            )
        ).group_by(CSIData.status).all()

        # セッション統計
        total_sessions = db.query(DataSession).filter(
            and_(
                DataSession.device_id == device.id,
                DataSession.created_at >= start_date
            )
        ).count()

        return {
            "device_id": device_id,
            "period_days": days,
            "total_csi_data": total_data,
            "total_sessions": total_sessions,
            "status_breakdown": {stat.status: stat.count for stat in status_stats},
            "last_upload": db.query(func.max(CSIData.created_at)).filter(
                CSIData.device_id == device.id
            ).scalar()
        }


class SessionService:
    """データ収集セッション管理サービス"""

    @staticmethod
    async def create_session(
        db: Session,
        session_data: SessionCreate,
        user_id: uuid.UUID
    ) -> DataSession:
        """セッション作成"""
        # デバイス存在確認
        device = db.query(Device).filter(
            and_(
                Device.device_id == session_data.device_id,
                Device.owner_id == user_id
            )
        ).first()

        if not device:
            raise ValueError(f"デバイス '{session_data.device_id}' が見つかりません")

        session = DataSession(
            device_id=device.id,
            session_name=session_data.session_name,
            start_time=session_data.start_time,
            status="active",
            metadata=session_data.metadata
        )

        db.add(session)
        db.commit()
        db.refresh(session)

        # WebSocketで新セッション開始を通知
        await realtime_service.broadcast_device_status_update(
            session_data.device_id,
            {
                "type": "session_started",
                "session_id": str(session.id),
                "session_name": session.session_name,
                "start_time": session.start_time.isoformat()
            }
        )

        return session

    @staticmethod
    async def end_session(
        db: Session,
        session_id: uuid.UUID,
        user_id: uuid.UUID
    ) -> Optional[DataSession]:
        """セッション終了"""
        session = db.query(DataSession).join(Device).filter(
            and_(
                DataSession.id == session_id,
                Device.owner_id == user_id
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

        # WebSocketでセッション終了を通知
        device = db.query(Device).filter(Device.id == session.device_id).first()
        if device:
            await realtime_service.broadcast_device_status_update(
                device.device_id,
                {
                    "type": "session_ended",
                    "session_id": str(session.id),
                    "duration": session.duration,
                    "end_time": end_time.isoformat()
                }
            )

        return session

    @staticmethod
    def get_device_sessions(
        db: Session,
        device_id: str,
        user_id: uuid.UUID,
        limit: int = 10
    ) -> List[DataSession]:
        """デバイスのセッション一覧取得"""
        return db.query(DataSession).join(Device).filter(
            and_(
                Device.device_id == device_id,
                Device.owner_id == user_id
            )
        ).order_by(desc(DataSession.created_at)).limit(limit).all()