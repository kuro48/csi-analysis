#!/usr/bin/env python3

"""
Python高精度リファレンス実装でコサイン類似度を計算し、ZKP回路の結果と比較
開発モード専用 - ZKP回路での近似計算の精度検証に使用
"""

import json
import sys
import math
from pathlib import Path
from typing import List, Tuple, Dict, Any
from datetime import datetime
import numpy as np

NUM_FREQ_POINTS = 25
NUM_SUBCARRIERS = 245


def generate_sample_csi_data() -> Tuple[List[List[int]], List[List[int]]]:
    """サンプルCSIデータを生成"""
    reference_matrix = []
    candidate_matrix = []

    for f in range(NUM_FREQ_POINTS):
        ref_row = []
        cand_row = []
        for sc in range(NUM_SUBCARRIERS):
            # ベースCSI: 正弦波パターン
            base_value = math.sin((f + sc) * 0.1) * 1000 + 1000
            ref_row.append(round(base_value))

            # 候補CSI: サブキャリアごとに異なるノイズを追加
            noise_level = (sc % 50) * 10
            noise = (np.random.random() - 0.5) * noise_level
            cand_row.append(round(base_value + noise))

        reference_matrix.append(ref_row)
        candidate_matrix.append(cand_row)

    return reference_matrix, candidate_matrix


def load_csi_data_from_file(file_path: str) -> Dict[str, Any]:
    """CSIデータをファイルから読み込み"""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return {
            'referenceMatrix': data.get('referenceMatrix') or data.get('reference_matrix'),
            'candidateMatrix': data.get('candidateMatrix') or data.get('candidate_matrix')
        }
    except Exception as e:
        print(f"Failed to load CSI data from {file_path}: {e}")
        return None


def calculate_cosine_similarity_python(
    ref_vector: np.ndarray,
    cand_vector: np.ndarray
) -> Dict[str, float]:
    """Python高精度でコサイン類似度を計算"""
    dot_product = float(np.dot(ref_vector, cand_vector))
    norm_ref = float(np.linalg.norm(ref_vector))
    norm_cand = float(np.linalg.norm(cand_vector))

    if norm_ref == 0 or norm_cand == 0:
        cosine = 0.0
    else:
        cosine = dot_product / (norm_ref * norm_cand)

    return {
        'cosine': cosine,
        'dot_product': dot_product,
        'norm_ref': norm_ref,
        'norm_cand': norm_cand
    }


def calculate_all_similarities(
    reference_matrix: List[List[int]],
    candidate_matrix: List[List[int]]
) -> Tuple[List[float], List[Dict[str, Any]]]:
    """全サブキャリアの類似度を計算"""
    ref = np.array(reference_matrix, dtype=np.float64)
    cand = np.array(candidate_matrix, dtype=np.float64)

    similarities = []
    details = []

    for sc in range(NUM_SUBCARRIERS):
        ref_vec = ref[:, sc]
        cand_vec = cand[:, sc]

        result = calculate_cosine_similarity_python(ref_vec, cand_vec)
        similarities.append(result['cosine'])

        details.append({
            'subcarrier': sc,
            'similarity': result['cosine'],
            'dot_product': result['dot_product'],
            'norm_ref': result['norm_ref'],
            'norm_cand': result['norm_cand']
        })

    return similarities, details


def get_top_n_lowest(similarities: List[float], n: int = 5) -> List[Dict[str, Any]]:
    """上位N個の低類似度サブキャリアを取得"""
    indexed = [(i, sim) for i, sim in enumerate(similarities)]
    indexed.sort(key=lambda x: x[1])
    return [{'index': i, 'similarity': sim} for i, sim in indexed[:n]]


def get_top_n_highest(similarities: List[float], n: int = 5) -> List[Dict[str, Any]]:
    """上位N個の高類似度サブキャリアを取得"""
    indexed = [(i, sim) for i, sim in enumerate(similarities)]
    indexed.sort(key=lambda x: x[1], reverse=True)
    return [{'index': i, 'similarity': sim} for i, sim in indexed[:n]]


def calculate_statistics(similarities: List[float]) -> Dict[str, float]:
    """統計情報を計算"""
    arr = np.array(similarities)
    return {
        'mean': float(np.mean(arr)),
        'median': float(np.median(arr)),
        'std_dev': float(np.std(arr)),
        'min': float(np.min(arr)),
        'max': float(np.max(arr)),
        'q25': float(np.percentile(arr, 25)),
        'q75': float(np.percentile(arr, 75))
    }


def compare_with_zkp_results(
    python_similarities: List[float],
    zkp_results_file: str
) -> None:
    """ZKP結果との比較"""
    try:
        with open(zkp_results_file, 'r') as f:
            zkp_data = json.load(f)

        zkp_results = zkp_data.get('zkp_results', {})
        zkp_similarities = zkp_results.get('all_similarities', [])

        if not zkp_similarities:
            print("ZKP results not found in file.")
            return

        print("\n🔍 Accuracy Comparison (Python High-Precision vs ZKP Circuit):")
        print("=" * 80)

        # 全体の差分統計
        differences = [abs(p - z) for p, z in zip(python_similarities, zkp_similarities)]
        diff_stats = {
            'mean_diff': np.mean(differences),
            'max_diff': np.max(differences),
            'median_diff': np.median(differences),
            'std_diff': np.std(differences)
        }

        print(f"  Mean Absolute Difference:   {diff_stats['mean_diff']:.8f}")
        print(f"  Max Absolute Difference:    {diff_stats['max_diff']:.8f}")
        print(f"  Median Absolute Difference: {diff_stats['median_diff']:.8f}")
        print(f"  Std Dev of Differences:     {diff_stats['std_diff']:.8f}")

        # 上位5つの比較
        py_top5 = get_top_n_lowest(python_similarities, 5)
        zkp_top5_data = zkp_results.get('top_5', [])

        print("\n📊 Top 5 Lowest Similarities Comparison:")
        print("  Rank | Python SC | Python Sim | ZKP SC    | ZKP Sim    | Diff")
        print("  -----|-----------|------------|-----------|------------|----------")
        for i in range(5):
            py = py_top5[i]
            zkp = zkp_top5_data[i] if i < len(zkp_top5_data) else {'index': 'N/A', 'similarity': 0}
            diff = abs(py['similarity'] - zkp.get('similarity', 0))
            print(
                f"  {i+1}    | {str(py['index']).rjust(9)} | "
                f"{py['similarity']:.6f}   | "
                f"{str(zkp.get('index', 'N/A')).rjust(9)} | "
                f"{zkp.get('similarity', 0):.6f}   | "
                f"{diff:.8f}"
            )

        # ZKP固有の情報も表示
        print(f"\n🔐 ZKP Proof Status: {'✅ Valid' if zkp_data.get('proof_valid') else '❌ Invalid'}")
        print(f"  Min Similarity (ZKP): {zkp_results.get('min_similarity', 0):.6f}")
        print(f"  Min Index (ZKP):      {zkp_results.get('min_index', 0)}")

    except FileNotFoundError:
        print(f"\n⚠️  ZKP results file not found: {zkp_results_file}")
    except Exception as e:
        print(f"\n❌ Error comparing with ZKP results: {e}")


def main():
    print("🐍 Calculating all subcarrier cosine similarities (Python - High Precision)...\n")

    # コマンドライン引数からファイルパスを取得
    # または最新のZKP結果ファイルから入力データを読み込む
    reference_matrix = None
    candidate_matrix = None

    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        print(f"📂 Loading CSI data from: {sys.argv[1]}")
        data = load_csi_data_from_file(sys.argv[1])
        if not data:
            print("Failed to load data. Checking for ZKP results...")
        else:
            reference_matrix = data['referenceMatrix']
            candidate_matrix = data['candidateMatrix']

    # ZKP結果ファイルから入力データを取得（引数がない場合）
    if reference_matrix is None:
        results_dir = Path(__file__).parent.parent / "results"
        zkp_results_pattern = list(results_dir.glob("similarities_*.json"))
        if zkp_results_pattern:
            latest_zkp = max(zkp_results_pattern, key=lambda p: p.stat().st_mtime)
            print(f"📂 Loading input data from latest ZKP results: {latest_zkp.name}")
            try:
                with open(latest_zkp, 'r') as f:
                    zkp_data = json.load(f)
                input_data = zkp_data.get('input_data', {})
                if input_data:
                    reference_matrix = input_data.get('referenceMatrix')
                    candidate_matrix = input_data.get('candidateMatrix')
            except Exception as e:
                print(f"Failed to load from ZKP results: {e}")

    # それでもデータがない場合はサンプルデータを生成
    if reference_matrix is None:
        print("📊 Generating sample CSI data...")
        reference_matrix, candidate_matrix = generate_sample_csi_data()

    print(f"  Matrix dimensions: {NUM_FREQ_POINTS} x {NUM_SUBCARRIERS}\n")

    # 類似度計算
    print("🔢 Calculating similarities (NumPy)...")
    import time
    start_time = time.time()
    similarities, details = calculate_all_similarities(reference_matrix, candidate_matrix)
    elapsed_time = (time.time() - start_time) * 1000
    print(f"✅ Calculation completed in {elapsed_time:.2f}ms\n")

    # 統計情報
    stats = calculate_statistics(similarities)
    print("📈 Statistics:")
    print(f"  Mean:     {stats['mean']:.8f}")
    print(f"  Median:   {stats['median']:.8f}")
    print(f"  Std Dev:  {stats['std_dev']:.8f}")
    print(f"  Min:      {stats['min']:.8f}")
    print(f"  Max:      {stats['max']:.8f}")
    print(f"  Q25:      {stats['q25']:.8f}")
    print(f"  Q75:      {stats['q75']:.8f}\n")

    # 上位5つの低類似度
    top_lowest = get_top_n_lowest(similarities, 5)
    print("📉 Top 5 Lowest Similarities:")
    for rank, item in enumerate(top_lowest, 1):
        detail = details[item['index']]
        print(
            f"  {rank}. Subcarrier {str(item['index']).rjust(3)}: "
            f"{item['similarity']:.8f} "
            f"(dot={detail['dot_product']:.2f}, "
            f"norm_ref={detail['norm_ref']:.2f}, "
            f"norm_cand={detail['norm_cand']:.2f})"
        )

    # 上位5つの高類似度（参考）
    top_highest = get_top_n_highest(similarities, 5)
    print("\n📈 Top 5 Highest Similarities (for reference):")
    for rank, item in enumerate(top_highest, 1):
        detail = details[item['index']]
        print(
            f"  {rank}. Subcarrier {str(item['index']).rjust(3)}: "
            f"{item['similarity']:.8f} "
            f"(dot={detail['dot_product']:.2f}, "
            f"norm_ref={detail['norm_ref']:.2f}, "
            f"norm_cand={detail['norm_cand']:.2f})"
        )

    # 結果をファイルに保存
    results_dir = Path(__file__).parent.parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().isoformat().replace(':', '-').replace('.', '-')
    results_file = results_dir / f"py_similarities_{timestamp}.json"

    results = {
        'timestamp': datetime.now().isoformat(),
        'num_subcarriers': NUM_SUBCARRIERS,
        'num_freq_points': NUM_FREQ_POINTS,
        'calculation_time_ms': elapsed_time,
        'statistics': stats,
        'top_5_lowest': top_lowest,
        'top_5_highest': top_highest,
        'all_similarities': similarities,
        'all_details': details
    }

    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n💾 Results saved to: {results_file}")

    # ZKP結果との比較（存在する場合）
    zkp_results_pattern = list(results_dir.glob("similarities_*.json"))
    if zkp_results_pattern:
        latest_zkp = max(zkp_results_pattern, key=lambda p: p.stat().st_mtime)
        compare_with_zkp_results(similarities, str(latest_zkp))
    else:
        print("\n💡 Tip: Run 'npm run prove:all_subcarriers' first to generate ZKP results for comparison.")


if __name__ == '__main__':
    main()
