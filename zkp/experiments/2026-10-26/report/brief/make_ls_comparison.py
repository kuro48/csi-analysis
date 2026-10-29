# -*- coding: utf-8 -*-
"""Slide-ready plot of real-data witness estimates versus all-tone floating LS."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / 'lomb/accuracy_summary.csv'
font_manager.fontManager.addfont(str(Path.home() / 'Library/Fonts/NotoSansJP-Regular.ttf'))
plt.rcParams.update({'font.family': 'Noto Sans JP', 'font.size': 17,
                     'svg.fonttype': 'path', 'axes.unicode_minus': False})
rows = list(csv.DictReader(SOURCE.open()))
counts = [int(r['subcarriers']) for r in rows]
values = [float(r['absolute_difference_all_sc_bpm_mean']) for r in rows]
assert counts == [1, 2, 4, 8, 16, 32]
assert all(int(r['valid_windows']) == 8 for r in rows)

fig = plt.figure(figsize=(16, 9), facecolor='white')
fig.text(.08, .92, 'Lomb–Scargle：サブキャリア本数による推定値の変化',
         fontsize=27, weight='bold', color='#182f43')
fig.text(.08, .865, '実データ8収録 ｜ 全サブキャリアの浮動小数点LSを参照',
         fontsize=18, color='#617382')
ax = fig.add_axes([.10, .34, .83, .44])
ax.set_axisbelow(True)
ax.grid(axis='y', color='#e1e8ed', linewidth=1)
for side in ['top', 'right', 'left']:
    ax.spines[side].set_visible(False)
ax.spines['bottom'].set_color('#b9c8d3')
ax.tick_params(axis='both', length=0, pad=12, colors='#455e70')
ax.plot(range(6), values, color='#237d9b', linewidth=2.8, zorder=3)
ax.scatter(range(5), values[:5], s=115, color='#237d9b', edgecolor='white', linewidth=1.8, zorder=4)
ax.scatter([5], values[5:], s=140, facecolor='white', edgecolor='#237d9b', linewidth=2.8, zorder=4)
for i, value in enumerate(values):
    ax.annotate(f'{value:.3f}', (i, value), xytext=(0, 17), textcoords='offset points',
                ha='center', fontsize=20, color='#183f55', weight='bold')
ax.set_xticks(range(6), [f'{c}本' for c in counts])
ax.set_yticks([0, 1, 2, 3, 4])
ax.set_ylim(0, 4.25)
ax.set_xlim(-.35, 5.35)
ax.set_ylabel('参照との平均絶対差（BPM）', labelpad=20, color='#344f62')
ax.set_xlabel('入力サブキャリア数', labelpad=14, color='#344f62')
fig.text(.10, .16, '本数を増やしても単調には改善しない。今回の参照との差は32本で最小。',
         fontsize=19, color='#183f55', bbox=dict(boxstyle='round,pad=.65', facecolor='#edf5f8', edgecolor='none'))
fig.text(.10, .085, '数値は全6条件のwitness計算結果から回路外で集計。正解呼吸数に対する誤差ではありません。',
         fontsize=13, color='#617382')
fig.text(.10, .045, '○ 32本：witness生成は成功。後続の証明用セットアップで停止し、証明生成・検証は未完了。',
         fontsize=13, color='#617382')
stem = HERE / 'ls_subcarrier_comparison_clean'
for suffix in ['png', 'svg']:
    fig.savefig(stem.with_suffix('.' + suffix), dpi=200, facecolor='white')
plt.close(fig)
stem.with_suffix('.json').write_text(json.dumps({
    'source': str(SOURCE), 'sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    'counts': counts, 'mean_absolute_difference_bpm': values, 'n_real_windows': 8,
    'estimate_origin': 'original circuit witness', 'aggregation': 'outside circuit',
    'ground_truth_available': False, 'sc32_proof_verified': False,
}, ensure_ascii=False, indent=2) + '\n')
print(stem.with_suffix('.png'))
