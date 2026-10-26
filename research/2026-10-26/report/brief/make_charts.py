import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import numpy as np
HERE=Path(__file__).resolve().parent
BASE=HERE.parents[1]
font=Path.home()/'Library/Fonts/NotoSansJP-Regular.ttf'
matplotlib.font_manager.fontManager.addfont(str(font))
plt.rcParams.update({'font.family':'Noto Sans JP','font.size':16,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
def read(p): return json.loads((BASE/p).read_text())
def save(name):
 plt.savefig(HERE/(name+'.png'),dpi=180,bbox_inches='tight');plt.close()
a=read('vmd/raw_only/aggregate.json');ks=[1,2,3,4,5,8];rs=[1,2,4,8,16,32]
m=np.array([[next(x['mean_abs_difference_ls_band_bpm'] for x in a if x['kind']=='real' and x['modes']==k and x['iterations']==r) for r in rs] for k in ks])
fig,ax=plt.subplots(figsize=(10,5));im=ax.imshow(m,cmap='Blues',aspect='auto',vmin=0,vmax=m.max());ax.set_xticks(range(6),rs);ax.set_yticks(range(6),ks);ax.set_xlabel('反復数');ax.set_ylabel('モード数')
for i in range(6):
 for j in range(6): ax.text(j,i,f'{m[i,j]:.2f}',ha='center',va='center',color='white' if m[i,j]>m.max()*.55 else '#172b3b')
fig.colorbar(im,ax=ax,label='LS参照との平均絶対差 (BPM)');fig.tight_layout();save('vmd_sweep')
fig,ax=plt.subplots(figsize=(10,4.8));vals=[10.6565625,11.145,1.108125,1.108125];labels=['K3 / 反復4\n既定中心','K3 / 反復32\n既定中心','K4 / 反復4\n中心を追加','K3 / 反復4\n中心を変更']
bars=ax.bar(range(4),vals,color=['#89949c','#89949c','#56829d','#256b90'],width=.6);ax.set_xticks(range(4),labels);ax.set_ylim(0,13);ax.set_ylabel('LS参照との平均絶対差 (BPM)');ax.bar_label(bars,fmt='%.3f',padding=7);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True);fig.tight_layout();save('vmd_centers')
ls=read('lomb/accuracy_summary.json');fig,ax=plt.subplots(figsize=(10,4.8));ax.plot(range(6),[r['absolute_difference_all_sc_bpm_mean'] for r in ls],'o-',color='#256b90',lw=2,ms=8);ax.set_xticks(range(6),[r['subcarriers'] for r in ls]);ax.set_xlabel('サブキャリア本数');ax.set_ylabel('全tone参照との平均絶対差 (BPM)');ax.set_ylim(0,4.2);ax.grid(alpha=.2)
for i,r in enumerate(ls): ax.annotate(f"{r['absolute_difference_all_sc_bpm_mean']:.3f}",(i,r['absolute_difference_all_sc_bpm_mean']),xytext=(0,12),textcoords='offset points',ha='center')
fig.tight_layout();save('ls_difference')
pr=[r for r in read('lomb/proof_summary.json') if r['proof_status']=='verified'];fig,ax=plt.subplots(figsize=(10,4.8));v=[r['prove_seconds_median'] for r in pr];ax.bar(range(5),v,color='#56829d',width=.6,yerr=[[r['prove_seconds_median']-r['prove_seconds_min'] for r in pr],[r['prove_seconds_max']-r['prove_seconds_median'] for r in pr]],capsize=5);ax.set_xticks(range(6),[1,2,4,8,16,32]);ax.set_xlim(-.6,5.7);ax.set_ylim(0,22);ax.set_xlabel('サブキャリア本数');ax.set_ylabel('証明生成時間 (秒)');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
for i,value in enumerate(v): ax.text(i,value+1,f'{value:.2f}',ha='center')
ax.text(5,3,'未取得\n鍵生成で停止',ha='center',fontsize=14,color='#666');fig.tight_layout();save('ls_proof')
v=read('diagnostics/vmd/trace.json');fig,axes=plt.subplots(2,1,figsize=(10,5.2),sharex=True,sharey=True)
for ax,st in zip(axes,[v['stages'][0],v['stages'][3]]):
 for k,mode in enumerate(st['modes']): ax.plot(v['time_seconds'],mode['waveform_inverse_dft_off_circuit'],label=f'モード{k+1}',lw=1.5)
 ax.axvspan(48,64,color='#ddd',alpha=.5);ax.set_title(f"反復 {st['iteration_one_based']}",loc='left',fontsize=16);ax.set_ylabel('表示振幅');ax.grid(alpha=.2)
axes[0].legend(ncol=3,loc='upper right',fontsize=13);axes[-1].set_xlabel('時間 (秒)');fig.tight_layout();save('vmd_trace')
l=read('diagnostics/lomb/decoded_public.json')['data'];sc=int(l['selectedSubcarrier']);ts=np.array(l['timestampsMs'],float)/1000;f=(127+29*np.arange(32))/2540*60
fig,axes=plt.subplots(3,1,figsize=(10,5.6));ys=[np.asarray(l['debugMagnitudeSquared'],float)[:,sc],np.asarray(l['debugCentered'],float)[:,sc],np.asarray(l['debugNumerator'],float)[sc]/np.asarray(l['debugDenominator'],float)[sc]]
for ax,x,y,label in zip(axes,[ts,ts,f],ys,['振幅二乗','平均除去 (64倍)','LSスコア']):
 ax.plot(x,y,color='#256b90');ax.set_ylabel(label);ax.grid(alpha=.2);ax.set_xlabel('周波数 (BPM)' if ax is axes[-1] else '時間 (秒)')
fig.tight_layout();save('ls_trace')
