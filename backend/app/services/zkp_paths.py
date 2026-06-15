"""
ZKP ディレクトリ解決ヘルパー
"""

import os
from pathlib import Path
from typing import Optional


def resolve_zkp_dir(zkp_dir: Optional[str] = None) -> Path:
    """ZKP ディレクトリのパスを解決する。

    優先順位:
    1. 引数 zkp_dir が指定されていればそれを使う
    2. 環境変数 ZKP_DIR があればそれを使う
    3. Docker 環境では /zkp
    4. ローカル環境ではプロジェクトルート / zkp
    """
    if zkp_dir is not None:
        return Path(zkp_dir)

    env_dir = os.getenv("ZKP_DIR")
    if env_dir:
        return Path(env_dir)

    docker_zkp = Path("/zkp")
    if docker_zkp.exists():
        return docker_zkp

    # ローカル環境: backend/app/services -> backend -> project_root
    return Path(__file__).resolve().parent.parent.parent.parent / "zkp"
