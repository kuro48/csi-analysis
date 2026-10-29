#!/usr/bin/env python3
"""Render actual diagnostic public outputs; derived display transforms are labelled."""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
OUT=HERE/'trace_figures'
OUT.mkdir(exist_ok=True)


def load(relative):
    return json.loads((BASE/relative).read_text())


def main():
    v=load('diagnostics/vmd/trace.json')
    l=load('diagnostics/lomb/decoded_public.json')
    vp_path=BASE/'diagnostics/vmd/proof_validation.json'
    vp=json.loads(vp_path.read_text()) if vp_path.exists() else {}
    verified=bool(vp.get('proof_verified') and l.get('proof_verified'))
    if '--witness-preview' not in sys.argv:
        assert verified, 'Generate verified diagnostic proofs before publishing the viewer'
        assert vp['tampered_public_rejected'] and load('diagnostics/lomb/tamper_validation.json')['rejected_as_invalid_proof']
    d=l['data']
    selected=int(d['selectedSubcarrier'])
    selection=load('diagnostics/lomb/selection.json')
    times=np.asarray(d['timestampsMs'],dtype=float)/1000
    frequencies=(127+29*np.arange(32))/2540*60
    def arr(key):return np.asarray(d[key],dtype=float)
    mag=arr('debugMagnitudeSquared');centered=arr('debugCentered')
    score=arr('debugNumerator')/arr('debugDenominator')
    datasets=[]
    def add(method,stage,choice,x,ys,names,xlabel,ylabel,note,padding=False):
        datasets.append(dict(method=method,stage=stage,choice=choice,x=np.asarray(x).tolist(),
            series=[dict(name=n,y=np.asarray(y).tolist()) for n,y in zip(names,ys)],
            xlabel=xlabel,ylabel=ylabel,note=note,padding=padding))
    vt=v['time_seconds'];vf=v['frequency_bpm']
    add('VMD','入力波形','入力',vt,[v['input_waveform_public']],['入力PCA波形'],'時間(s)','正規化整数振幅',
        '回路の公開出力debugWaveform。48秒以降の16秒はゼロ埋め後の平均除去部分。',True)
    add('VMD','DFT係数','実部・正sin係数',vf,[v['dft']['real_coefficients_public'],v['dft']['positive_sine_coefficients_public']],
        ['DFT実部','DFT正sin係数'],'周波数(BPM)','整数係数 (scale=1000)','回路内DFTの公開出力。時間波形ではなく周波数ごとの係数。')
    add('VMD','DFTパワー','全bin',vf,[v['dft']['power_off_circuit']],['DFT power'],'周波数(BPM)','power',
        '公開DFT係数の二乗和を描画時に計算。power自体は追加の公開出力ではない。')
    for stage in v['stages']:
        r=stage['iteration_one_based'];modes=stage['modes']
        add('VMD','各反復のモード波形',f'反復 {r}',vt,[m['waveform_inverse_dft_off_circuit'] for m in modes],
            [f'モード {k+1}' for k in range(3)],'時間(s)','逆DFT表示振幅',
            '公開された周波数係数を回路外で逆DFTして表示。回路が時間領域のモード波形を計算したという意味ではない。',True)
        add('VMD','各反復の周波数パワー',f'反復 {r}',vf,[m['power_off_circuit'] for m in modes],
            [f'モード {k+1}' for k in range(3)],'周波数(BPM)','power','各反復の公開モード実部・正sin係数から二乗和を描画時に計算。')
        for field,label in [('real_coefficients_public','各反復のモード実部'),('positive_sine_coefficients_public','各反復のモード正sin係数')]:
            add('VMD',label,f'反復 {r}',vf,[m[field] for m in modes],[f'モード {k+1}' for k in range(3)],
                '周波数(BPM)','公開整数係数','逆DFTする前の、回路が公開した周波数領域のモード係数。')
    centers=np.asarray(v['center_trajectory_public'])
    add('VMD','中心周波数の推移','全モード',np.arange(5),[centers[:,k]*120/128 for k in range(3)],
        [f'モード {k+1}' for k in range(3)],'反復 (0=初期値)','中心(BPM)','公開中心binをBPMへ換算。推定呼吸数と各モード中心は別の値。')
    for sc in range(8):
        label=f'SC {sc}'+('（回路が選択）' if sc==selected else '')
        add('Lomb–Scargle','入力I/Q',label,times,[arr('debugSignedI')[:,sc],arr('debugSignedQ')[:,sc]],['I','Q'],
            '時間(s)','量子化I/Q','回路内でoffset=2048を取り除いた実際の入力信号。')
        add('Lomb–Scargle','振幅二乗',label,times,[mag[:,sc]],['I²+Q²'],'時間(s)','振幅二乗','回路内magnitudeSquaredの公開値。')
        add('Lomb–Scargle','平均除去',label,times,[centered[:,sc]],['64×振幅二乗 − 合計'],'時間(s)','中心化整数値',
            '回路内centeredの公開値。除算を避けるため通常の平均除去波形の64倍になっている。')
        add('Lomb–Scargle','周波数への射影',label,frequencies,[arr('debugCosProjection')[sc],arr('debugSinProjection')[sc]],
            ['cos射影','sin射影'],'周波数(BPM)','射影値','回路内cosineProjection/sineProjectionの公開値。')
        add('Lomb–Scargle','LSスコア',label,frequencies,[score[sc]],['numerator / denominator'],'周波数(BPM)','正規化スコア',
            '回路が公開した整数分子・分母を表示側で割り算。回路のargmaxは除算せず交差乗算で比較する。')
        for field,title in [('debugNumerator','LSスコアの分子'),('debugDenominator','LSスコアの分母')]:
            add('Lomb–Scargle',title,label,frequencies,[arr(field)[sc]],[title],'周波数(BPM)','公開整数値',
                '回路の公開出力。大きい整数の正確な値はJSON/CSV、グラフは浮動小数点で描画。')
    b=int(d['estimatedFrequencyBin'])
    add('Lomb–Scargle','sin/cos基底',f'選択bin {b} ({frequencies[b]:.3f} BPM)',times,
        [arr('debugCosBasis')[b],arr('debugSinBasis')[b]],['cos基底','sin基底'],'時間(s)','基底整数値 (scale=1000)',
        '記録時刻から回路内で計算した、最終選択周波数のsin/cos基底。')
    # Standard scientific plots, suitable for direct PowerPoint insertion.
    plt.rcParams.update({'font.family':'Noto Sans CJK JP','font.size':12,'pdf.fonttype':42})
    fig,axes=plt.subplots(3,1,figsize=(11,8))
    for ax,values,title in zip(axes,[v['input_waveform_public'],v['dft']['real_coefficients_public'],v['dft']['positive_sine_coefficients_public']],
                             ['入力波形（公開出力）','DFT実部（公開出力）','DFT正sin係数（公開出力）']):
        x=vt if ax is axes[0] else vf
        ax.plot(x,values,lw=1.5);ax.set_title(title,fontsize=15);ax.grid(alpha=.2)
        ax.set_xlabel('時間(s)' if ax is axes[0] else '周波数(BPM)')
    axes[0].axvspan(48,64,color='gray',alpha=.15,label='観測外のpadding');axes[0].legend(fontsize=10)
    fig.tight_layout();fig.savefig(OUT/'vmd_input_dft.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(4,1,figsize=(11,10),sharex=True,sharey=True)
    for ax,stage in zip(axes,v['stages']):
        for k,m in enumerate(stage['modes']):ax.plot(vt,m['waveform_inverse_dft_off_circuit'],label=f'モード{k+1}')
        ax.axvspan(48,64,color='gray',alpha=.12);ax.set_title(f"反復 {stage['iteration_one_based']}",fontsize=14);ax.set_ylabel('表示振幅');ax.grid(alpha=.2)
    axes[0].legend(ncol=3);axes[-1].set_xlabel('時間(s)')
    fig.suptitle('VMD公開モード係数を逆DFTして表示（逆DFTは回路外）',fontsize=19)
    fig.text(.08,.012,'灰色部分は観測外のpadding区間。振幅は回路用正規化単位で、身体の変位ではない。',fontsize=11);fig.tight_layout(rect=(0,.035,1,.96));fig.savefig(OUT/'vmd_iterations.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(3,1,figsize=(11,8))
    for ax,values,title in zip(axes,[mag[:,selected],centered[:,selected],score[selected]],
                             ['振幅二乗：公開出力','平均除去：公開出力（64倍）','LSスコア：公開分子÷公開分母を表示側で計算']):
        ax.plot(times if ax is not axes[2] else frequencies,values,marker='.' if ax is axes[2] else None)
        ax.set_title(title,fontsize=15);ax.grid(alpha=.2);ax.set_xlabel('時間(s)' if ax is not axes[2] else '周波数(BPM)')
    for ax,label in zip(axes,['量子化振幅²','中心化整数値','正規化スコア']):ax.set_ylabel(label)
    fig.suptitle(f"Lomb–Scargle 中間値：入力SC {selected} / 元tone {selection['source_tone_index']}",fontsize=19)
    fig.tight_layout(rect=(0,0,1,.96));fig.savefig(OUT/'lomb_stages.png',dpi=180);plt.close(fig)
    data=dict(datasets=datasets,vmd_result=v['result'],ls_selected_sc=selected,ls_bpm=float(frequencies[b]),selection=selection,proof_verified=verified)
    (HERE/'trace_display_data.json').write_text(json.dumps(data,ensure_ascii=False))
    template=(HERE/'trace_viewer_template.html').read_text()
    status='両回路のGroth16証明を検証済みです。' if verified else '現在はwitness生成・照合までのプレビューです。Groth16証明はまだ検証していません。'
    document=template.replace('__TRACE_DATA__',json.dumps(data,ensure_ascii=False)).replace('__PROOF_STATUS__',status)
    if not verified:document=document.replace('../diagnostics/vmd/proof_public.json','../diagnostics/vmd/public.json').replace('../diagnostics/lomb/public.json','../diagnostics/lomb/public_from_witness.json')
    target=HERE/('trace_viewer.html' if verified else 'trace_preview.html')
    target.write_text(document,encoding='utf-8')
    print(target)


if __name__=='__main__':main()
