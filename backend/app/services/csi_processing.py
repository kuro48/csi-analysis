"""
CSIデータバックグラウンド処理サービス

解析・ZKP証明生成・ブロックチェーン記録のオーケストレーションを
エンドポイント層から分離する。
"""

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Optional

import pandas as pd

from app.core.config import settings
from app.models.csi_data import CSIData
from app.services.base_csi import BaseCSIService
from app.services.blockchain_service import BlockchainService
from app.services.csi_visualizer import (
    save_combined_graph,
    save_fft_graph,
    save_music_graph,
    save_wavelet_graph,
)
from app.services.pcap_analyzer import PCAPAnalyzer
from app.services.zkp_circuit_service import ZKPMusicService, ZKPWaveletService
from app.services.zkp_service import ZKPService

logger = logging.getLogger(__name__)


def _get_blockchain_service() -> BlockchainService:
    """BlockchainService を設定から直接生成する（エンドポイント層に依存しない）。"""
    return BlockchainService(
        rpc_url=settings.ETHEREUM_RPC_URL,
        contract_address=settings.ZKPROOF_CONTRACT_ADDRESS,
        account_private_key=settings.BLOCKCHAIN_PRIVATE_KEY or None,
    )


def parse_json_field(value) -> Optional[dict]:
    """JSONB列の値をdictに正規化（str/dict/None対応）。"""
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value) if value else None
    return value


def serialize_fft_dataframe(fft_df) -> dict:
    """FFTデータフレームからフロントエンド表示用サマリーをJSON化する。

    全サブキャリア列（60×1942）の代わりに frequency と magnitude_avg の
    2列だけを返すことでペイロードを大幅に削減する。
    """
    if not hasattr(fft_df, "to_dict"):
        return {}

    import numpy as np

    df = fft_df.copy()

    if "freq_interval" in df.columns:
        from app.services.pcap_analyzer_common import _interval_midpoint
        df["frequency"] = df["freq_interval"].apply(_interval_midpoint).astype(float)
    elif "frequency" not in df.columns:
        return {}

    exclude = {"frequency", "freq_interval", "freq_mid", "_mean"}
    data_cols = [
        c for c in df.columns
        if c not in exclude and str(c).lstrip("-").replace(".", "", 1).isdigit()
    ]
    if data_cols:
        df["magnitude_avg"] = df[data_cols].replace([np.inf, -np.inf], np.nan).mean(axis=1)
    elif "_mean" in df.columns:
        df["magnitude_avg"] = df["_mean"]
    else:
        df["magnitude_avg"] = np.nan

    summary = df[["frequency", "magnitude_avg"]].copy()
    summary = summary.replace([np.nan, np.inf, -np.inf], None)
    return summary.to_dict()


async def record_zkp_proof_on_chain(
    csi_data: CSIData,
    base_csi_comparison: dict,
    csi_data_id: uuid.UUID,
    db,
) -> None:
    """ZKP証明をブロックチェーンに自動記録する。"""
    try:
        blockchain_service = _get_blockchain_service()

        if not blockchain_service.is_available():
            logger.warning(
                f"Blockchain service not available for CSI data {csi_data_id}. "
                "Skipping automatic blockchain recording."
            )
            return

        device_id = getattr(csi_data, "device_id", None)
        if not device_id:
            logger.warning(f"CSI data {csi_data_id} has no device_id; skipping blockchain record")
            return

        zkp_proof = base_csi_comparison["zkp_proof"]
        public_signals = base_csi_comparison["public_signals"]

        proof_id = await blockchain_service.record_zkp_proof(
            device_id=device_id,
            proof=zkp_proof,
            public_signals=public_signals,
            proof_type="full_similarity",
        )

        if not proof_id:
            logger.warning(
                f"Failed to record ZKP proof on blockchain for CSI data {csi_data_id}"
            )
            return

        logger.info(
            f"ZKP proof automatically recorded on blockchain: "
            f"CSI data {csi_data_id}, proof ID {proof_id}"
        )

        csi_data.processed_data["blockchain_proof_id"] = proof_id
        csi_data.processed_data["blockchain_proof_data"] = {
            "proof": zkp_proof,
            "public_signals": public_signals,
        }
        db.commit()
    except Exception as e:
        logger.warning(
            f"Failed to record ZKP proof on blockchain for CSI data {csi_data_id}: {e}",
            exc_info=True,
        )


async def run_base_csi_comparison(
    db,
    analyzer: PCAPAnalyzer,
    zkp_service: ZKPService,
    fft_dataframe,
    wavelet_dataframe,
    music_dataframe,
    base_csi_id: Optional[uuid.UUID],
    user_id: Optional[uuid.UUID],
) -> Optional[dict]:
    """ベースCSIとのコサイン類似度比較・ZKP証明生成を実行する。

    Returns:
        比較結果の辞書。ベースCSIが存在しない場合は None。
    """
    if base_csi_id:
        base_csi = BaseCSIService.get_base_csi_by_id(db, base_csi_id, user_id=None, status="completed")
    else:
        base_csis, _ = BaseCSIService.get_base_csi_list(
            db=db, user_id=None, include_expired=False, status="completed", page=1, page_size=1
        )
        base_csi = base_csis[0] if base_csis else None

    if not base_csi:
        logger.warning("No base CSI found for comparison")
        return None

    logger.info(f"Comparing with base CSI: {base_csi.id} ({base_csi.name})")

    extract_kwargs = dict(
        freq_col="freq_interval", use_binned=True,
        freq_min=analyzer.ZKP_FREQ_START, freq_max=analyzer.ZKP_FREQ_END,
    )

    def subcarrier_entry(indices, sims):
        return [
            {"index": idx, "similarity": sim, "rank": i + 1}
            for i, (idx, sim) in enumerate(zip(indices, sims))
        ]

    async def load_base_dataframe(method: str):
        stored = getattr(base_csi, f"{method}_dataframe", None)
        if stored:
            return await asyncio.to_thread(pd.DataFrame, stored)
        source_path = getattr(base_csi, "source_pcap_path", None)
        if not source_path:
            return pd.DataFrame()
        try:
            fallback_result = await asyncio.to_thread(analyzer.analyze_pcap_file, source_path)
            return fallback_result.get(method, pd.DataFrame())
        except Exception as e:
            logger.warning(f"Failed to rebuild {method} dataframe from base PCAP: {e}", exc_info=True)
            return pd.DataFrame()

    async def compare_method(method: str, base_df, upload_df) -> Optional[dict]:
        if base_df is None or base_df.empty or upload_df is None or upload_df.empty:
            logger.warning(f"Skipping {method} ZKP comparison because dataframe is empty")
            return None

        base_data, upload_data = await asyncio.gather(
            asyncio.to_thread(analyzer.extract_full_subcarrier_vectors, base_df, **extract_kwargs),
            asyncio.to_thread(analyzer.extract_full_subcarrier_vectors, upload_df, **extract_kwargs),
        )

        if base_data["num_freq_points"] == 0 or upload_data["num_freq_points"] == 0:
            logger.warning(f"Skipping {method} ZKP comparison because extracted vectors are empty")
            return None

        reference_matrix = base_data["csi_matrix"]
        candidate_matrix = upload_data["csi_matrix"]

        similarity_result = await zkp_service.generate_proof(
            reference_matrix=reference_matrix,
            candidate_matrix=candidate_matrix,
        )
        python_similarity, python_top_n_result = await asyncio.gather(
            asyncio.to_thread(zkp_service.compute_python_similarity, reference_matrix, candidate_matrix),
            asyncio.to_thread(zkp_service.select_top_n_subcarriers, reference_matrix, candidate_matrix, 5),
        )
        zkp_top_n_result = await asyncio.to_thread(
            zkp_service.extract_top_n_from_similarities,
            similarity_result.get("similarities", []), 10000, 5,
        )

        selected_similarity = similarity_result.get("selectedSubcarrierSimilarity")
        if selected_similarity is None:
            selected_similarity = python_top_n_result.get("lowest_similarity")

        logger.info(
            f"Base CSI {method} comparison completed: "
            f"similarity={similarity_result['normalizedSimilarity']:.4f}, "
            f"dimensions={base_data['num_freq_points']}×{base_data['num_subcarriers']}"
        )

        return {
            "method": method,
            "similarity_score": similarity_result["normalizedSimilarity"],
            "zkp_proof": similarity_result.get("proof", {}),
            "public_signals": similarity_result.get("publicSignals", []),
            "is_valid": similarity_result.get("isValid", False),
            "python_similarity": python_similarity.get("cosine_similarity"),
            "selected_subcarrier": {
                "index": similarity_result.get("selectedSubcarrierIndex"),
                "similarity": selected_similarity,
            },
            "lowest_similarity_subcarrier": {
                "index": similarity_result.get("selectedSubcarrierIndex"),
                "similarity": selected_similarity,
            },
            "zkp_top_5_lowest_subcarriers": subcarrier_entry(
                zkp_top_n_result["top_n_indices"], zkp_top_n_result["top_n_similarities"]
            ),
            "python_top_5_lowest_subcarriers": subcarrier_entry(
                python_top_n_result["top_n_indices"], python_top_n_result["top_n_similarities"]
            ),
            "data_dimensions": {
                "num_freq_points": base_data["num_freq_points"],
                "num_subcarriers": base_data["num_subcarriers"],
                "total_dimensions": base_data["num_freq_points"] * base_data["num_subcarriers"],
            },
        }

    method_results = {}
    for method_name, upload_df in {
        "fft": fft_dataframe,
        "wavelet": wavelet_dataframe,
        "music": music_dataframe,
    }.items():
        base_df = await load_base_dataframe(method_name)
        result = await compare_method(method_name, base_df, upload_df)
        if result:
            method_results[method_name] = result

    if not method_results:
        logger.warning("No method-specific ZKP comparison could be generated")
        return None

    primary_method = "fft" if "fft" in method_results else next(iter(method_results))
    primary_result = method_results[primary_method]
    similarity_delta = None
    if "fft" in method_results and "wavelet" in method_results:
        similarity_delta = abs(
            method_results["fft"]["similarity_score"] - method_results["wavelet"]["similarity_score"]
        )

    return {
        "base_csi_id": str(base_csi.id),
        "base_csi_name": base_csi.name,
        "primary_method": primary_method,
        "methods": method_results,
        "comparison_summary": {
            "generated_methods": list(method_results.keys()),
            "primary_method": primary_method,
            "similarity_delta": similarity_delta,
        },
        # 後方互換: 既存のトップレベルは primary_method の結果を流用する
        "similarity_score": primary_result["similarity_score"],
        "zkp_proof": primary_result["zkp_proof"],
        "public_signals": primary_result["public_signals"],
        "is_valid": primary_result["is_valid"],
        "python_similarity": primary_result["python_similarity"],
        "selected_subcarrier": primary_result["selected_subcarrier"],
        "lowest_similarity_subcarrier": primary_result["lowest_similarity_subcarrier"],
        "zkp_top_5_lowest_subcarriers": primary_result["zkp_top_5_lowest_subcarriers"],
        "python_top_5_lowest_subcarriers": primary_result["python_top_5_lowest_subcarriers"],
        "data_dimensions": primary_result["data_dimensions"],
    }


async def generate_transform_zkp_proofs(
    analyzer: PCAPAnalyzer,
    db,
    upload_wavelet_df: pd.DataFrame,
    upload_music_df: pd.DataFrame,
    base_csi_id: Optional[uuid.UUID],
    user_id: Optional[uuid.UUID],
    wavelet_service: ZKPWaveletService,
    music_service: ZKPMusicService,
    device_id: Optional[str],
    csi_data_id: uuid.UUID,
) -> dict:
    """ウェーブレット・MUSIC 専用 ZKP 証明を生成してブロックチェーンに記録する。

    Returns:
        {"wavelet": {"is_normal": bool, "proof_id": str|None}, "music": {...}}
    """
    results: dict = {"wavelet": None, "music": None}

    if base_csi_id:
        base_csi = BaseCSIService.get_base_csi_by_id(db, base_csi_id, user_id=None, status="completed")
    else:
        base_csis, _ = BaseCSIService.get_base_csi_list(
            db=db, user_id=None, include_expired=False, status="completed", page=1, page_size=1
        )
        base_csi = base_csis[0] if base_csis else None

    if not base_csi:
        logger.warning("[TransformZKP] No base CSI found; skipping wavelet/music ZKP proofs")
        return results

    async def load_base_df(method: str) -> pd.DataFrame:
        stored = getattr(base_csi, f"{method}_dataframe", None)
        if stored:
            return pd.DataFrame(stored)
        source_path = getattr(base_csi, "source_pcap_path", None)
        if not source_path:
            return pd.DataFrame()
        try:
            result = await asyncio.to_thread(analyzer.analyze_pcap_file, source_path)
            return result.get(method, pd.DataFrame())
        except Exception as exc:
            logger.warning(f"[TransformZKP] Failed to rebuild {method} base DF: {exc}")
            return pd.DataFrame()

    async def run_proof(method: str, base_df: pd.DataFrame, upload_df: pd.DataFrame, service):
        if base_df.empty or upload_df.empty:
            logger.warning(f"[TransformZKP] Skipping {method}: empty dataframe")
            return None
        if method == "music":
            ref_matrix = analyzer.extract_music_matrix_for_zkp(base_df)
            cand_matrix = analyzer.extract_music_matrix_for_zkp(upload_df)
        else:
            ref_matrix = analyzer.extract_matrix_for_zkp(base_df)
            cand_matrix = analyzer.extract_matrix_for_zkp(upload_df)
        if not ref_matrix or not cand_matrix:
            logger.warning(f"[TransformZKP] Skipping {method}: empty matrix after extraction")
            return None
        try:
            result = await service.generate_proof(
                reference_matrix=ref_matrix,
                candidate_matrix=cand_matrix,
            )
            return result
        except Exception as exc:
            logger.error(f"[TransformZKP] {method} proof failed: {exc}", exc_info=True)
            return None

    base_wavelet_df, base_music_df = await asyncio.gather(
        load_base_df("wavelet"),
        load_base_df("music"),
    )
    wavelet_result, music_result = await asyncio.gather(
        run_proof("wavelet", base_wavelet_df, upload_wavelet_df, wavelet_service),
        run_proof("music", base_music_df, upload_music_df, music_service),
    )

    blockchain_service = _get_blockchain_service()

    for method_name, proof_result in (("wavelet", wavelet_result), ("music", music_result)):
        if proof_result is None:
            continue
        is_normal = proof_result.get("isNormal", False)
        proof_id = None
        if blockchain_service.is_available() and device_id:
            try:
                proof_id = await blockchain_service.record_zkp_proof(
                    device_id=device_id,
                    proof=proof_result["proof"],
                    public_signals=proof_result["publicSignals"],
                    proof_type=method_name,
                )
                logger.info(
                    f"[TransformZKP] {method_name} proof recorded on blockchain: "
                    f"CSI {csi_data_id}, proof_id={proof_id}, isNormal={is_normal}"
                )
            except Exception as exc:
                logger.warning(f"[TransformZKP] blockchain record failed for {method_name}: {exc}")
        results[method_name] = {"is_normal": is_normal, "proof_id": proof_id}

    return results


async def process_csi_in_background(
    csi_data_id: uuid.UUID,
    file_path: str,
    db_session_maker,
    user_id: Optional[uuid.UUID] = None,
    base_csi_id: Optional[uuid.UUID] = None,
) -> None:
    """バックグラウンドでCSI解析・ZKP証明生成・DB保存・ブロックチェーン記録を実行する。

    ファイル形式（.pcap / .csi など）は拡張子から自動判定する。
    """
    db = None
    csi_data = None
    try:
        db = db_session_maker()
        logger.info(f"Starting background processing for CSI data {csi_data_id}")

        csi_data = db.query(CSIData).filter_by(id=csi_data_id).first()
        if csi_data:
            csi_data.status = "processing"
            await asyncio.to_thread(db.commit)

        analyzer = PCAPAnalyzer()
        zkp_service = ZKPService(auto_compile=settings.ZKP_AUTO_COMPILE)
        wavelet_zkp_service = ZKPWaveletService(auto_compile=settings.ZKP_AUTO_COMPILE)
        music_zkp_service = ZKPMusicService(auto_compile=settings.ZKP_AUTO_COMPILE)

        # --- CSI解析（FFT + ウェーブレット + MUSIC） ---
        logger.info(f"Analyzing CSI file: {file_path}")
        analysis_result = await asyncio.to_thread(analyzer.analyze_file, file_path)
        binned_fft_df = analysis_result["fft"]
        binned_wavelet_df = analysis_result["wavelet"]
        binned_music_df = analysis_result["music"]
        if binned_fft_df.empty:
            raise ValueError("PCAP解析に失敗しました: データが空です")

        # --- グラフ保存（ZKP入力前の状態を可視化） ---
        csi_id_str = str(csi_data_id)
        fft_matrix = await asyncio.to_thread(analyzer.extract_matrix_for_zkp, binned_fft_df)
        wavelet_matrix = (
            await asyncio.to_thread(analyzer.extract_matrix_for_zkp, binned_wavelet_df)
            if not binned_wavelet_df.empty else []
        )
        music_matrix = (
            await asyncio.to_thread(analyzer.extract_music_matrix_for_zkp, binned_music_df)
            if not binned_music_df.empty else []
        )
        if fft_matrix:
            await asyncio.to_thread(save_fft_graph, fft_matrix, csi_id_str)
        if wavelet_matrix:
            await asyncio.to_thread(save_wavelet_graph, wavelet_matrix, csi_id_str)
        if music_matrix:
            await asyncio.to_thread(save_music_graph, music_matrix, csi_id_str)
        await asyncio.to_thread(save_combined_graph, fft_matrix, wavelet_matrix, music_matrix, csi_id_str)

        device_id = getattr(csi_data, "device_id", None) if csi_data else None

        # --- FFT ベースCSI比較・ZKP証明生成 ---
        base_csi_comparison = None
        try:
            base_csi_comparison = await run_base_csi_comparison(
                db=db,
                analyzer=analyzer,
                zkp_service=zkp_service,
                fft_dataframe=binned_fft_df,
                wavelet_dataframe=binned_wavelet_df,
                music_dataframe=binned_music_df,
                base_csi_id=base_csi_id,
                user_id=user_id,
            )
        except Exception as e:
            logger.warning(f"Base CSI comparison failed: {e}", exc_info=True)

        # --- ウェーブレット・MUSIC 専用 ZKP 証明生成 + ブロックチェーン記録 ---
        transform_zkp_results: dict = {"wavelet": None, "music": None}
        try:
            transform_zkp_results = await generate_transform_zkp_proofs(
                analyzer=analyzer,
                db=db,
                upload_wavelet_df=binned_wavelet_df,
                upload_music_df=binned_music_df,
                base_csi_id=base_csi_id,
                user_id=user_id,
                wavelet_service=wavelet_zkp_service,
                music_service=music_zkp_service,
                device_id=device_id,
                csi_data_id=csi_data_id,
            )
        except Exception as e:
            logger.warning(f"Transform ZKP proofs failed: {e}", exc_info=True)

        # --- DB保存 ---
        if csi_data:
            csi_data.status = "completed"
            fft_ser, wav_ser, mus_ser = await asyncio.gather(
                asyncio.to_thread(serialize_fft_dataframe, binned_fft_df),
                asyncio.to_thread(serialize_fft_dataframe, binned_wavelet_df),
                asyncio.to_thread(serialize_fft_dataframe, binned_music_df),
            )
            processed_data: dict = {
                "fft_dataframe": fft_ser,
                "wavelet_dataframe": wav_ser,
                "music_dataframe": mus_ser,
                "breathing_rate_comparison": analysis_result["breathing_rate_comparison"],
                "wavelet_zkp": transform_zkp_results.get("wavelet"),
                "music_zkp": transform_zkp_results.get("music"),
            }
            if base_csi_comparison:
                processed_data["base_csi_comparison"] = base_csi_comparison
            csi_data.processed_data = processed_data
            await asyncio.to_thread(db.commit)

            # --- FFT ZKP ブロックチェーン記録 ---
            if base_csi_comparison:
                await record_zkp_proof_on_chain(
                    csi_data=csi_data,
                    base_csi_comparison=base_csi_comparison,
                    csi_data_id=csi_data_id,
                    db=db,
                )

            if base_csi_comparison:
                logger.info(
                    f"Background processing completed for CSI data {csi_data_id}: "
                    f"similarity={base_csi_comparison['similarity_score']:.4f}, "
                    f"wavelet_isNormal={(transform_zkp_results.get('wavelet') or {}).get('is_normal')}, "
                    f"music_isNormal={(transform_zkp_results.get('music') or {}).get('is_normal')}"
                )
            else:
                logger.info(f"Background processing completed for CSI data {csi_data_id}")

    except ValueError as e:
        logger.error(
            f"Validation error in background processing for CSI data {csi_data_id}: {e}",
            exc_info=True,
        )
        if db and csi_data:
            csi_data.status = "error"
            csi_data.processed_data = {
                "error": str(e),
                "error_type": "ValidationError",
                "error_category": "pcap_analysis_failed",
            }
            await asyncio.to_thread(db.commit)

    except Exception as e:
        logger.error(
            f"Background processing failed for CSI data {csi_data_id}: {e}",
            exc_info=True,
        )
        if db and csi_data:
            csi_data.status = "error"
            csi_data.processed_data = {
                "error": str(e),
                "error_type": type(e).__name__,
                "error_category": "processing_failed",
            }
            await asyncio.to_thread(db.commit)

    finally:
        if not settings.RESEARCH_MODE and file_path:
            temp_path = Path(file_path)
            if temp_path.exists():
                try:
                    temp_path.unlink()
                    logger.info(f"Temporary CSI file deleted after background processing: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete temporary CSI file {file_path}: {e}")
            if db and csi_data:
                csi_data.file_path = None
                csi_data.file_size = None
                await asyncio.to_thread(db.commit)
        if db:
            await asyncio.to_thread(db.close)
