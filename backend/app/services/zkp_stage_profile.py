"""実測した段階プロファイルを使い、証明生成時間を処理段階ごとに按分する。

Groth16は回路全体を一括で証明するため、1回の証明から段階別の所要時間を
直接取り出すことはできない。一方で証明生成時間は入力値に依存せず回路構造
だけで決まるので、段階別回路で一度実測したプロファイル（段階ごとの制約数と
固定オーバーヘッド）は以降のすべての解析に対して有効になる。

実行時は総時間だけを実測し、固定オーバーヘッドを差し引いた実処理時間を
制約数比で各段階へ配分する。
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

PROFILE_RELATIVE_PATH = Path("profiles") / "stage_profile.json"


def load_profile(zkp_dir: Union[Path, str], circuit_name: str) -> Optional[Dict[str, Any]]:
    """回路名に対応する段階プロファイルを読む。無い・壊れている場合は None。

    内訳表示は付加情報なので、読めなくても証明生成は止めない。
    """
    path = Path(zkp_dir) / PROFILE_RELATIVE_PATH
    try:
        profile = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        logger.warning("段階プロファイルを読めませんでした %s: %s", path, exc)
        return None

    if profile.get("circuitName") != circuit_name:
        return None
    if not profile.get("stages") or not profile.get("totalConstraints"):
        return None
    return profile


def build_stage_breakdown(
    zkp_dir: Union[Path, str],
    circuit_name: str,
    proof_generation_ms: float,
    constraint_count: Optional[int],
) -> Optional[Dict[str, Any]]:
    """証明生成時間を段階別に按分した内訳を返す。作れない場合は None。

    Args:
        zkp_dir: ZKPディレクトリ（プロファイルの探索基点）
        circuit_name: 対象回路名
        proof_generation_ms: その回の実測証明生成時間
        constraint_count: 現在コンパイルされている回路の制約数（陳腐化検出用）
    """
    profile = load_profile(zkp_dir, circuit_name)
    if profile is None:
        return None

    total = profile["totalConstraints"]

    # プロファイル作成後に回路が変わっていたら按分は無意味になる。
    # 今回の T=150→300 のように、成果物と実装がずれる事故を表示側にも波及させない。
    if constraint_count is not None and constraint_count != total:
        logger.warning(
            "段階プロファイルが回路と不一致のため内訳を省略します "
            "(profile=%s, compiled=%s)。scripts/measure_stage_profile.py を再実行してください",
            total,
            constraint_count,
        )
        return None

    overhead_ms = profile.get("fixedOverheadMs")
    # 固定費を引いた残りが制約数に比例する実処理時間。
    # 実測値が固定費を下回る場合（別マシンで測ったプロファイル等）は按分を諦める。
    if overhead_ms is None or proof_generation_ms <= overhead_ms:
        work_ms = proof_generation_ms
        overhead_ms = 0.0
    else:
        work_ms = proof_generation_ms - overhead_ms

    stages: List[Dict[str, Any]] = []
    for stage in profile["stages"]:
        share = stage["constraints"] / total
        stages.append({
            "key": stage["key"],
            "label": stage["label"],
            "description": stage.get("description"),
            "constraints": stage["constraints"],
            "constraintShare": round(share, 6),
            "estimatedMs": round(work_ms * share, 3),
        })

    return {
        "stages": stages,
        "fixedOverheadMs": round(overhead_ms, 3),
        "attributedWorkMs": round(work_ms, 3),
        "totalConstraints": total,
        "profileMeasuredAt": profile.get("measuredAt"),
        # 直接計測ではなく按分値であることを、表示側が明示できるようにする。
        "method": "constraint_share_attribution",
    }
