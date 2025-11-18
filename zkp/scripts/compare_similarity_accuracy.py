#!/usr/bin/env python3

"""
コサイン類似度の精度比較

元のFFTデータ（浮動小数点）とPythagorean triple近似（整数演算）の
コサイン類似度計算結果を比較します。
"""

import csv
import json
import numpy as np
from pathlib import Path
import pandas as pd

# オプショナルな可視化ライブラリ
try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    PLOTTING_AVAILABLE = True
except ImportError:
    PLOTTING_AVAILABLE = False
    print('⚠️  matplotlib/seaborn not available - skipping plots')

# ディレクトリ設定
DATA_DIR = Path(__file__).parent.parent / 'data'
SIMILARITY_DIR = DATA_DIR / 'similarity_results'
FFT_CSV_FILE = DATA_DIR / 'csi_fft_real.csv'
APPROX_MATRIX_FILE = SIMILARITY_DIR / 'similarity_matrix.csv'
CONVERTED_VECTORS_FILE = SIMILARITY_DIR / 'converted_vectors.json'

# 出力ディレクトリ
COMPARISON_DIR = DATA_DIR / 'similarity_comparison'
COMPARISON_DIR.mkdir(exist_ok=True)


def load_fft_data():
    """FFT CSVファイルからパワースペクトルデータを読み込み"""
    print('📂 Loading FFT data from CSV...')
    print(f'   File: {FFT_CSV_FILE}')

    fft_data = []
    with open(FFT_CSV_FILE, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            subcarrier_id = int(row['subcarrier_id'])
            # 最初の4周波数ビンを抽出
            power_bins = [float(row[f'power_bin_{i}']) for i in range(4)]
            fft_data.append({
                'subcarrier_id': subcarrier_id,
                'power_bins': np.array(power_bins)
            })

    print(f'✅ Loaded {len(fft_data)} subcarriers with 4 frequency bins each')
    return fft_data


def calculate_cosine_similarity_original(vec_a, vec_b):
    """元データでコサイン類似度を計算（浮動小数点、高精度）"""
    # ゼロベクトルチェック
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    # コサイン類似度 = 内積 / (ノルムA × ノルムB)
    dot_product = np.dot(vec_a, vec_b)
    similarity = dot_product / (norm_a * norm_b)

    return float(similarity)


def calculate_all_similarities_original(fft_data):
    """全サブキャリア間のコサイン類似度を元データで計算"""
    print('\n📊 Calculating similarity matrix from original FFT data...')

    n = len(fft_data)
    matrix = np.zeros((n, n))

    for i in range(n):
        for j in range(n):
            if i == j:
                matrix[i, j] = 1.0
            else:
                similarity = calculate_cosine_similarity_original(
                    fft_data[i]['power_bins'],
                    fft_data[j]['power_bins']
                )
                matrix[i, j] = similarity

    print(f'✅ Calculated {n}x{n} similarity matrix from original data')
    return matrix


def load_approximated_similarities():
    """Pythagorean triple近似の類似度マトリックスを読み込み"""
    print('\n📂 Loading approximated similarity matrix...')
    print(f'   File: {APPROX_MATRIX_FILE}')

    df = pd.read_csv(APPROX_MATRIX_FILE, index_col=0)
    matrix = df.values

    print(f'✅ Loaded {matrix.shape[0]}x{matrix.shape[1]} approximated matrix')
    return matrix


def compare_matrices(original_matrix, approx_matrix):
    """2つの類似度マトリックスを比較"""
    print('\n📊 Comparing original vs approximated similarities...')

    # 差分を計算（対角成分を除く）
    n = original_matrix.shape[0]
    differences = []
    absolute_errors = []
    relative_errors = []

    for i in range(n):
        for j in range(n):
            if i != j:  # 対角成分は除外
                orig = original_matrix[i, j]
                approx = approx_matrix[i, j]
                diff = approx - orig
                abs_error = abs(diff)

                differences.append(diff)
                absolute_errors.append(abs_error)

                # 相対誤差（元の値が小さい場合は除外）
                if abs(orig) > 0.01:
                    rel_error = abs_error / abs(orig) * 100
                    relative_errors.append(rel_error)

    differences = np.array(differences)
    absolute_errors = np.array(absolute_errors)
    relative_errors = np.array(relative_errors)

    # 統計情報
    stats = {
        'num_comparisons': len(differences),
        'mean_absolute_error': float(np.mean(absolute_errors)),
        'max_absolute_error': float(np.max(absolute_errors)),
        'min_absolute_error': float(np.min(absolute_errors)),
        'std_absolute_error': float(np.std(absolute_errors)),
        'median_absolute_error': float(np.median(absolute_errors)),
        'mean_relative_error_percent': float(np.mean(relative_errors)) if len(relative_errors) > 0 else None,
        'max_relative_error_percent': float(np.max(relative_errors)) if len(relative_errors) > 0 else None,
    }

    print('\n📈 Comparison Statistics:')
    print(f'   Number of comparisons: {stats["num_comparisons"]}')
    print(f'   Mean absolute error: {stats["mean_absolute_error"]:.6f}')
    print(f'   Max absolute error: {stats["max_absolute_error"]:.6f}')
    print(f'   Median absolute error: {stats["median_absolute_error"]:.6f}')
    if stats['mean_relative_error_percent'] is not None:
        print(f'   Mean relative error: {stats["mean_relative_error_percent"]:.2f}%')
        print(f'   Max relative error: {stats["max_relative_error_percent"]:.2f}%')

    return stats, differences, absolute_errors, relative_errors


def find_best_and_worst_approximations(original_matrix, approx_matrix):
    """最良・最悪の近似ペアを見つける"""
    print('\n🔍 Finding best and worst approximations...')

    n = original_matrix.shape[0]
    comparisons = []

    for i in range(n):
        for j in range(i + 1, n):  # 上三角のみ
            orig = original_matrix[i, j]
            approx = approx_matrix[i, j]
            abs_error = abs(approx - orig)

            comparisons.append({
                'sc_a': i,
                'sc_b': j,
                'original': orig,
                'approximated': approx,
                'absolute_error': abs_error,
                'relative_error': abs_error / abs(orig) * 100 if abs(orig) > 0.01 else None
            })

    # 絶対誤差でソート
    comparisons.sort(key=lambda x: x['absolute_error'])

    best_10 = comparisons[:10]
    worst_10 = comparisons[-10:]

    print('\n✅ Top 10 Best Approximations (lowest error):')
    for idx, comp in enumerate(best_10, 1):
        print(f'   {idx}. SC {comp["sc_a"]} vs SC {comp["sc_b"]}: '
              f'Original={comp["original"]:.4f}, Approx={comp["approximated"]:.4f}, '
              f'Error={comp["absolute_error"]:.6f}')

    print('\n⚠️  Top 10 Worst Approximations (highest error):')
    for idx, comp in enumerate(worst_10, 1):
        print(f'   {idx}. SC {comp["sc_a"]} vs SC {comp["sc_b"]}: '
              f'Original={comp["original"]:.4f}, Approx={comp["approximated"]:.4f}, '
              f'Error={comp["absolute_error"]:.6f}')

    return best_10, worst_10


def save_comparison_report(stats, best_10, worst_10):
    """比較レポートをJSON形式で保存"""
    output_file = COMPARISON_DIR / 'comparison_report.json'

    report = {
        'statistics': stats,
        'best_approximations': best_10,
        'worst_approximations': worst_10
    }

    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)

    print(f'\n💾 Comparison report saved: {output_file}')


def plot_error_distribution(absolute_errors):
    """誤差分布をプロット"""
    if not PLOTTING_AVAILABLE:
        return

    print('\n📊 Generating error distribution plot...')

    plt.figure(figsize=(12, 5))

    # ヒストグラム
    plt.subplot(1, 2, 1)
    plt.hist(absolute_errors, bins=50, edgecolor='black', alpha=0.7)
    plt.xlabel('Absolute Error')
    plt.ylabel('Frequency')
    plt.title('Distribution of Absolute Errors')
    plt.grid(True, alpha=0.3)

    # 累積分布
    plt.subplot(1, 2, 2)
    sorted_errors = np.sort(absolute_errors)
    cumulative = np.arange(1, len(sorted_errors) + 1) / len(sorted_errors) * 100
    plt.plot(sorted_errors, cumulative, linewidth=2)
    plt.xlabel('Absolute Error')
    plt.ylabel('Cumulative Percentage (%)')
    plt.title('Cumulative Distribution of Errors')
    plt.grid(True, alpha=0.3)

    plt.tight_layout()
    output_file = COMPARISON_DIR / 'error_distribution.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f'💾 Plot saved: {output_file}')
    plt.close()


def plot_similarity_heatmap_comparison(original_matrix, approx_matrix):
    """類似度マトリックスのヒートマップ比較"""
    if not PLOTTING_AVAILABLE:
        return

    print('\n📊 Generating similarity heatmap comparison...')

    # サブサンプリング（20x20のみ表示）
    n = min(20, original_matrix.shape[0])
    orig_subset = original_matrix[:n, :n]
    approx_subset = approx_matrix[:n, :n]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Original
    sns.heatmap(orig_subset, cmap='viridis', vmin=0, vmax=1,
                cbar_kws={'label': 'Similarity'}, ax=axes[0])
    axes[0].set_title('Original FFT Data (Floating Point)')
    axes[0].set_xlabel('Subcarrier ID')
    axes[0].set_ylabel('Subcarrier ID')

    # Approximated
    sns.heatmap(approx_subset, cmap='viridis', vmin=0, vmax=1,
                cbar_kws={'label': 'Similarity'}, ax=axes[1])
    axes[1].set_title('Pythagorean Triple Approximation (Integer)')
    axes[1].set_xlabel('Subcarrier ID')
    axes[1].set_ylabel('Subcarrier ID')

    plt.tight_layout()
    output_file = COMPARISON_DIR / 'similarity_heatmap_comparison.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f'💾 Plot saved: {output_file}')
    plt.close()


def main():
    print('🔍 Comparing Cosine Similarity: Original vs Pythagorean Triple Approximation\n')

    # 1. 元のFFTデータを読み込み
    fft_data = load_fft_data()

    # 2. 元データで類似度マトリックスを計算
    original_matrix = calculate_all_similarities_original(fft_data)

    # 3. Pythagorean triple近似の類似度マトリックスを読み込み
    approx_matrix = load_approximated_similarities()

    # 4. 2つのマトリックスを比較
    stats, differences, absolute_errors, relative_errors = compare_matrices(
        original_matrix, approx_matrix
    )

    # 5. 最良・最悪の近似ペアを見つける
    best_10, worst_10 = find_best_and_worst_approximations(
        original_matrix, approx_matrix
    )

    # 6. 比較レポートを保存
    save_comparison_report(stats, best_10, worst_10)

    # 7. 可視化
    plot_error_distribution(absolute_errors)
    plot_similarity_heatmap_comparison(original_matrix, approx_matrix)

    # 8. 元データの類似度マトリックスも保存
    output_file = COMPARISON_DIR / 'original_similarity_matrix.csv'
    df = pd.DataFrame(original_matrix,
                     index=[f'SC_{i}' for i in range(original_matrix.shape[0])],
                     columns=[f'SC_{i}' for i in range(original_matrix.shape[0])])
    df.to_csv(output_file)
    print(f'\n💾 Original similarity matrix saved: {output_file}')

    print('\n✅ Comparison complete!')
    print(f'\nResults saved in: {COMPARISON_DIR}/')
    print('  - comparison_report.json: Statistical summary')
    print('  - original_similarity_matrix.csv: Original FFT data similarities')
    print('  - error_distribution.png: Error distribution plots')
    print('  - similarity_heatmap_comparison.png: Visual comparison')


if __name__ == '__main__':
    main()
