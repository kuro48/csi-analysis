"""
IPFS関連エンドポイント
"""

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services.csi_data import CSIDataService
from app.services.ipfs import ipfs_service

router = APIRouter()


@router.get("/status")
async def get_ipfs_status():
    """
    IPFS接続状態確認
    """
    try:
        is_connected = await ipfs_service.is_connected()
        return {
            "status": "connected" if is_connected else "disconnected",
            "ipfs_node": f"http://{ipfs_service._connection_url}",
            "connected": is_connected,
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "connected": False}


@router.post("/upload")
async def upload_to_ipfs(
    file: UploadFile = File(..., description="アップロードするファイル"), current_user: User = Depends(get_current_user)
):
    """
    ファイルを直接IPFSにアップロード
    """
    try:
        # ファイルデータ読み取り
        file_data = await file.read()

        if len(file_data) == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="アップロードファイルが空です")

        # IPFSにアップロード
        ipfs_hash = await ipfs_service.upload_file(file_data, filename=file.filename)

        # ファイル情報取得
        file_info = await ipfs_service.get_file_info(ipfs_hash)

        return {
            "ipfs_hash": ipfs_hash,
            "filename": file.filename,
            "size": len(file_data),
            "content_type": file.content_type,
            "file_info": file_info,
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"IPFSアップロードに失敗しました: {str(e)}"
        )


@router.get("/download/{ipfs_hash}")
async def download_from_ipfs(ipfs_hash: str, current_user: User = Depends(get_current_user)):
    """
    IPFSからファイルをダウンロード
    """
    try:
        # IPFSからファイル取得
        file_data = await ipfs_service.get_file(ipfs_hash)

        # ファイル情報取得
        file_info = await ipfs_service.get_file_info(ipfs_hash)

        return {
            "ipfs_hash": ipfs_hash,
            "size": len(file_data),
            "file_info": file_info,
            "data": file_data.hex(),  # バイナリデータを16進数文字列として返す
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"IPFSファイル取得に失敗しました: {str(e)}"
        )


@router.get("/info/{ipfs_hash}")
async def get_ipfs_file_info(ipfs_hash: str, current_user: User = Depends(get_current_user)):
    """
    IPFSファイル情報取得
    """
    try:
        file_info = await ipfs_service.get_file_info(ipfs_hash)

        if not file_info:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IPFSファイルが見つかりません")

        return file_info

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"IPFSファイル情報取得に失敗しました: {str(e)}"
        )


@router.post("/pin/{ipfs_hash}")
async def pin_ipfs_file(ipfs_hash: str, current_user: User = Depends(get_current_user)):
    """
    IPFSファイルをピン留め（永続保存）
    """
    try:
        success = await ipfs_service.pin_file(ipfs_hash)

        if not success:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ピン留めに失敗しました")

        return {"ipfs_hash": ipfs_hash, "pinned": True, "message": "ファイルが正常にピン留めされました"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"IPFSピン留めに失敗しました: {str(e)}"
        )


@router.delete("/pin/{ipfs_hash}")
async def unpin_ipfs_file(ipfs_hash: str, current_user: User = Depends(get_current_user)):
    """
    IPFSファイルのピン留め解除
    """
    try:
        success = await ipfs_service.unpin_file(ipfs_hash)

        if not success:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ピン留め解除に失敗しました")

        return {"ipfs_hash": ipfs_hash, "pinned": False, "message": "ファイルのピン留めが正常に解除されました"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"IPFSピン留め解除に失敗しました: {str(e)}"
        )


@router.get("/csi-data/{csi_data_id}/ipfs")
async def get_csi_data_from_ipfs(
    csi_data_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """
    CSIデータをIPFSから取得
    """
    try:
        # CSIデータ取得
        csi_data = CSIDataService.get_csi_data_by_id(db, csi_data_id, current_user.id)
        if not csi_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CSIデータが見つかりません")

        if not csi_data.ipfs_hash:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="このCSIデータはIPFSに保存されていません")

        # IPFSから統合パッケージ取得
        package = await ipfs_service.retrieve_csi_data_package(csi_data.ipfs_hash)

        return {
            "csi_data_id": str(csi_data_id),
            "ipfs_combined_hash": csi_data.ipfs_hash,
            "ipfs_hashes": package["ipfs_hashes"],
            "metadata": package["metadata"],
            "combined_info": package["combined_info"],
            "file_size": len(package["file_data"]),
            "data": package["file_data"].hex(),  # バイナリデータを16進数文字列として返す
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"CSIデータのIPFS取得に失敗しました: {str(e)}"
        )
