"""証明書検証方式（案A）ZKP 証明生成サービス。

docs/ZKP_PIPELINE_EXTENSION_IDEAS.md テーマ1・案A の実装。

回路: csi_breathing_certificate.circom (BreathingCertificateCheck)
  秘密入力:
    vmdInput[T]   : VMD 入力信号（呼吸PC, 中心化・共通スケール整数）
    modes[K][T]   : VMD 出力 K モード（vmdInput と同一スケール整数）
    sel[K]        : 呼吸モードを指す one-hot
  公開出力:
    [isNormal]    : 正常帯域内 かつ 狭帯域 = 1 / それ以外 = 0

既存の csi_breathing_normality は「与えられた単一モードのピーク判定」しか
証明しないが、本回路は再構成性 Σ_k modes ≈ vmdInput を回路内で強制するため、
証明者が都合のよいモードを捏造する余地を狭める。
"""

import logging
import time
from typing import Any, Dict, List, Optional

from app.services.zkp_circuit_service import ZKPCircuitService

logger = logging.getLogger(__name__)


class BreathingCertificateService(ZKPCircuitService):
    """VMD 証明書検証回路の ZKP 証明生成サービス。"""

    CIRCUIT_NAME = "csi_breathing_certificate"

    # 回路パラメータ（csi_breathing_certificate.circom の component main と一致させること）
    T = 150
    K = 5

    def __init__(self, zkp_dir: Optional[str] = None, auto_compile: bool = True) -> None:
        super().__init__(self.CIRCUIT_NAME, zkp_dir=zkp_dir, auto_compile=auto_compile)

    async def generate_proof(  # type: ignore[override]
        self,
        vmd_input: Optional[List[int]] = None,
        modes: Optional[List[List[int]]] = None,
        sel: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """証明書回路の ZKP 証明を生成する。

        Args:
            vmd_input: VMD 入力信号 [T]（整数）
            modes:     VMD 出力モード [K][T]（整数）
            sel:       呼吸モードを指す one-hot [K]

        Returns:
            {proof, publicSignals, isNormal, isValid, method}
        """
        if vmd_input is None or modes is None or sel is None:
            raise ValueError("vmd_input, modes, sel are required for BreathingCertificateCheck")

        wasm = self.build_dir / f"{self.circuit_name}_js" / f"{self.circuit_name}.wasm"
        zkey = self.keys_dir / f"{self.circuit_name}_final.zkey"
        if not wasm.exists() or not zkey.exists():
            raise FileNotFoundError(
                f"{self.label} ZKP circuit files not found. "
                f"Run: cd zkp && npm run compile:breathing_certificate && npm run setup:breathing_certificate"
            )

        input_data = self._prepare_input(vmd_input, modes, sel)

        logger.info(
            "[%s] Generating certificate ZKP proof: T=%d, K=%d",
            self.label,
            len(input_data["vmdInput"]),
            len(input_data["modes"]),
        )
        start = time.time()
        witness_file = await self._generate_witness(input_data)
        proof, public_signals = await self._generate_groth16_proof(witness_file)
        is_valid = await self.verify_proof(proof, public_signals)
        if not is_valid:
            raise RuntimeError(f"{self.label} proof failed local verification")

        is_normal = bool(int(public_signals[0])) if public_signals else False
        logger.info(
            "[%s] Certificate ZKP proof done in %.3fs — isNormal=%s",
            self.label,
            time.time() - start,
            is_normal,
        )
        return {
            "proof": proof,
            "publicSignals": public_signals,
            "isNormal": is_normal,
            # 正常/異常という公開判定と、証明の妥当性は別の状態。
            "isValid": is_valid,
            "method": "breathing_certificate",
        }

    def _prepare_input(  # type: ignore[override]
        self,
        vmd_input: List[int],
        modes: List[List[int]],
        sel: List[int],
    ) -> Dict[str, Any]:
        """回路が期待する固定長 [T]/[K][T]/[K] へ整形する。

        入力形状は breathing_pipeline.prepare_breathing_certificate_input が
        既に満たしているが、防御的に固定長へ丸める。
        """

        def fit_1d(arr: List[int], length: int) -> List[int]:
            vals = [int(v) for v in arr[:length]]
            vals.extend([0] * (length - len(vals)))
            return vals

        if len(modes) != self.K:
            raise ValueError(f"modes は {self.K} 本である必要があります（実際: {len(modes)}）")
        if len(sel) != self.K:
            raise ValueError(f"sel は長さ {self.K} である必要があります（実際: {len(sel)}）")
        if sum(int(v) for v in sel) != 1 or any(int(v) not in (0, 1) for v in sel):
            raise ValueError("sel は one-hot（各要素0/1・総和1）である必要があります")

        return {
            "vmdInput": fit_1d(vmd_input, self.T),
            "modes": [fit_1d(modes[k], self.T) for k in range(self.K)],
            "sel": [int(v) for v in sel],
        }
