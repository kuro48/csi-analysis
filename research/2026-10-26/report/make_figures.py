#!/usr/bin/env python3
"""Regenerate publication-sized figures exclusively from saved measurements."""
from pathlib import Path
import csv
import json
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
OUT = HERE / 'figures'
OUT.mkdir(exist_ok=True)
INCLUDE_SYNTHETIC = '--include-synthetic' in sys.argv
plt.rcParams.update({'font.family': 'Noto Sans CJK JP', 'pdf.fonttype': 42, 'font.size': 13,
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'savefig.dpi': 180, 'axes.titlepad': 18})


def save(fig, name):
    fig.savefig(OUT / (name + '.png'), bbox_inches='tight', facecolor='white')
    fig.savefig(OUT / (name + '.pdf'), bbox_inches='tight', facecolor='white')
    plt.close(fig)


def load(relative):
    return json.loads((BASE / relative).read_text())


def vmd_figures():
    data = load('vmd/aggregate.json' if INCLUDE_SYNTHETIC else 'vmd/raw_only/aggregate.json')
    ks = sorted({r['modes'] for r in data})
    rs = sorted({r['iterations'] for r in data})
    for kind, title, field, subtitle in [
        ('real', '実CSI：モード数・反復数による変化',
         'mean_abs_difference_ls_band_bpm', '同じ128点波形のLSとの平均絶対差（BPM）／正解誤差ではない'),
        ('noise', '合成信号＋雑音：モード数・反復数による変化',
         'gt_mae_bpm', '既知の注入周波数に対する平均絶対誤差（BPM）'),
        ('strong_interferer', '強い帯域外成分：回数を増やしても残る誤差',
         'gt_mae_bpm', '既知の注入周波数に対する平均絶対誤差（BPM）'),
    ]:
        if kind != 'real' and not INCLUDE_SYNTHETIC:
            continue
        subset = {(r['modes'], r['iterations']): r for r in data if r['kind'] == kind}
        matrix = np.array([[subset[(k, r)][field] for r in rs] for k in ks])
        fig, ax = plt.subplots(figsize=(10, 7.2))
        im = ax.imshow(matrix, cmap='YlOrRd', vmin=0)
        ax.set_xticks(range(len(rs)), rs)
        ax.set_yticks(range(len(ks)), ks)
        ax.set_xlabel('反復数 R'); ax.set_ylabel('モード数 K')
        ax.set_title(title, fontsize=20)
        for i in range(len(ks)):
            for j in range(len(rs)):
                ax.text(j, i, f'{matrix[i,j]:.2f}', ha='center', va='center',
                        color='white' if matrix[i,j] > matrix.max() * .63 else '#152f44')
        fig.colorbar(im, ax=ax, label='BPM')
        fig.text(.08, .025, subtitle + f"\nn={next(iter(subset.values()))['n']}、初期中心は既定を含む固定の追加順", fontsize=11)
        fig.subplots_adjust(bottom=.18)
        save(fig, 'vmd_' + kind)

    with (BASE / 'vmd/raw_only/sweep.csv').open() as f:
        rows = [r for r in csv.DictReader(f) if r['kind'] == 'real']
    ids = sorted({r['case'] for r in rows})
    fig, ax = plt.subplots(figsize=(11, 6.5))
    for k, r, marker in [(3,4,'o'), (3,32,'^'), (5,4,'s')]:
        lookup = {x['case']: x for x in rows if int(x['modes']) == k and int(x['iterations']) == r}
        ax.plot(range(len(ids)), [float(lookup[i]['bpm']) for i in ids], marker=marker, label=f'近似VMD K={k}, R={r}')
    lookup = {x['case']: x for x in rows}
    ax.plot(range(len(ids)), [float(lookup[i]['ls_band_bpm']) for i in ids], 'k--D', label='同じ波形のLS参照値')
    ax.set_xticks(range(len(ids)), [s[4:12] for s in ids], rotation=25)
    ax.set_ylabel('推定呼吸数（BPM）'); ax.set_title('実CSI 8収録の推定値：LS参照値は正解ではない', fontsize=19)
    ax.legend(fontsize=11); ax.grid(axis='y', alpha=.25)
    fig.tight_layout(); save(fig, 'vmd_real_estimates')


def dataset_figure():
    files = [r for r in load('common/manifest.json')['files'] if Path(r['source']).name.startswith('csi_')]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(range(len(files)), [r['effective_average_hz'] for r in files], color='#26789a')
    ax.axhline(100, color='#c35630', ls='--', label='既存処理の100 Hz前提')
    ax.set_xticks(range(len(files)), [Path(r['source']).name[4:12] for r in files], rotation=25)
    ax.set_ylabel('保持フレーム数 / 実時間（Hz）')
    ax.set_title('Raw収録は等間隔100 Hzではない', fontsize=20)
    ax.legend(); ax.grid(axis='y', alpha=.2)
    fig.tight_layout(); save(fig, 'dataset_rates')


def initialization_figure():
    rows = [r for r in load('vmd/diagnostics_aggregate.json') if r['padding'] == 'zero' and r['iterations'] == 4]
    order = ['[8, 24, 48]', '[8, 16, 24]', '[8, 16, 32]', '[4, 12, 24]', '[16, 32, 48]', '[8, 32, 56]']
    lookup = {r['initial_centers']: r for r in rows}
    values = [lookup[k]['mean_abs_difference_ls_main_input_bpm'] for k in order]
    fig, ax = plt.subplots(figsize=(10,6))
    ax.barh(order, values, color=['#c55a35','#297c98']+['#99b8c5']*4)
    ax.invert_yaxis(); ax.set_xlim(0,max(values)*1.18)
    for i,v in enumerate(values):ax.text(v+.1,i,f'{v:.2f}',va='center')
    ax.set_xlabel('同じ128点波形のLSとの平均絶対差（BPM）')
    ax.set_ylabel('初期中心（DFT bin）')
    ax.set_title('K=3・R=4のまま、初期中心を変更', fontsize=20)
    fig.text(.1,.01,'実CSI 8件・ゼロ埋め固定。参照値は正解ではない。候補選定用の感度分析。',fontsize=10)
    fig.tight_layout(rect=(0,.04,1,1)); save(fig,'vmd_initialization')


def spectrum_example():
    sys.path.insert(0,str(BASE/'vmd'))
    from model import decompose, COS, SIN
    sample = BASE/'common/windows/csi_20260526_034004_w0.npz'
    if not sample.exists():
        return
    x = np.load(sample)['signal128']
    raw = (COS@x)**2 + (SIN@x)**2
    frequencies = np.arange(1,64)*120/128
    fig, axes = plt.subplots(2,1,figsize=(11,8),sharex=True,sharey=True)
    for ax,centers in zip(axes,[[8,24,48],[8,16,24]]):
        result = decompose(x,3,4,centers)
        spectra = np.asarray(result['spectra'],dtype=float)
        power = (spectra**2).sum(axis=2)
        ax.semilogy(frequencies,np.maximum(raw/raw.max(),1e-9),'k--',alpha=.55,label='入力DFT')
        for k in range(3):
            ax.semilogy(frequencies,np.maximum(power[k]/raw.max(),1e-9),label=f'モード{k+1}')
        ax.axvline(result['bpm'],color='#c34c25',ls=':',label=f"選択 {result['bpm']:.2f} BPM")
        ax.set_title(f"K=3 / R=4 / 初期中心 {centers} → {result['bpm']:.2f} BPM",fontsize=15)
        ax.set_ylabel('入力最大power基準');ax.set_ylim(1e-6,2);ax.grid(alpha=.2)
    axes[0].legend(fontsize=10,ncol=5,loc='upper center')
    axes[1].set_xlabel('周波数（BPM）'); axes[1].set_xlim(0,60)
    fig.suptitle('初期中心によって保持される周波数成分が変わる',fontsize=20)
    fig.text(.08,.015,'例：csi_20260526_034004の同じ128点整数入力。呼吸の正解スペクトルを示す図ではない。',fontsize=11)
    fig.tight_layout(rect=(0,.04,1,.96));save(fig,'vmd_spectrum_example')


def lomb_figures():
    p = BASE / 'lomb/accuracy_summary.json'
    if not p.exists():
        return
    rows = load('lomb/accuracy_summary.json')
    fig, ax = plt.subplots(figsize=(10, 6))
    for field, label, marker in [
        ('absolute_difference_same_sc_bpm_mean', '同じ選択列の浮動小数点LSとの差', 'o'),
        ('absolute_difference_all_sc_bpm_mean', '同一アンテナ対の全サブキャリアLSとの差', 's')]:
        ax.plot([r['subcarriers'] for r in rows], [r[field] for r in rows], marker=marker, label=label)
    ax.set_xscale('log', base=2); ax.set_xticks([1,2,4,8,16,32], [1,2,4,8,16,32])
    ax.set_xlabel('サブキャリア数（Tx0/Rx0固定）'); ax.set_ylabel('平均絶対差（BPM）')
    ax.set_title('Lomb–Scargle：本数による推定値の変化', fontsize=20)
    ax.legend(fontsize=11); ax.grid(alpha=.2)
    fig.text(.1,.01,'実CSIの参照手法との差。生理的な正解呼吸数に対する精度ではない。',fontsize=10)
    fig.tight_layout(rect=(0,.03,1,1)); save(fig,'lomb_agreement')
    if INCLUDE_SYNTHETIC and (BASE / 'lomb/synthetic_summary.json').exists():
        synthetic = load('lomb/synthetic_summary.json')
        fig, ax = plt.subplots(figsize=(10,6))
        ax.plot([r['subcarriers'] for r in synthetic], [r['mae_bpm'] for r in synthetic], 'o-', color='#287ca2')
        ax.set_xscale('log',base=2);ax.set_xticks([1,2,4,8,16,32],[1,2,4,8,16,32])
        ax.set_xlabel('サブキャリア数');ax.set_ylabel('既知周波数に対するMAE（BPM）')
        ax.set_title('Lomb–Scargle：合成CSI 40条件の誤差',fontsize=20)
        ax.grid(alpha=.2)
        for r in synthetic:ax.annotate(f"{r['mae_bpm']:.3f}",(r['subcarriers'],r['mae_bpm']),xytext=(4,8),textcoords='offset points')
        fig.text(.1,.01,'同一の信号生成条件内の比較。実際の呼吸精度・VMDの別対照との直接比較には使わない。',fontsize=10)
        fig.tight_layout(rect=(0,.04,1,1));save(fig,'lomb_synthetic')
    if not (BASE / 'lomb/proof_summary.json').exists():
        return
    rows = [r for r in load('lomb/proof_summary.json') if r['proof_status'] == 'verified']
    if not rows:
        return
    fig, ax = plt.subplots(figsize=(10,6))
    xx = np.arange(len(rows)); med = [r['prove_seconds_median'] for r in rows]
    err = [[r['prove_seconds_median']-r['prove_seconds_min'] for r in rows],
           [r['prove_seconds_max']-r['prove_seconds_median'] for r in rows]]
    ax.bar(xx, med, color='#287ca2', yerr=err, capsize=6)
    ax.set_xticks(xx,[str(r['subcarriers']) for r in rows]); ax.set_xlabel('サブキャリア数')
    ax.set_ylabel('Groth16証明生成時間（秒）')
    ax.set_title('Lomb–Scargle：実証明の生成時間', fontsize=20)
    for x,m in zip(xx,med):ax.text(x,m,f'{m:.2f} s',ha='center',va='bottom')
    fig.text(.1,.015,'各3回の中央値・範囲。ローカルMac実測。setup/witness/verifyを含まない。',fontsize=10)
    fig.tight_layout(rect=(0,.04,1,1)); save(fig,'lomb_proof_time')


if __name__ == '__main__':
    vmd_figures()
    dataset_figure()
    initialization_figure()
    spectrum_example()
    lomb_figures()
