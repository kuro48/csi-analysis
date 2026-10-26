"""Sensitivity checks; all outputs are algorithm differences, not measured human accuracy."""
import csv,json
from pathlib import Path
import numpy as np
from scipy.signal import lombscargle
from model import decompose
HERE=Path(__file__).resolve().parent
rows=[]
with (HERE/"baselines.csv").open() as handle:
 baseline_map={r["case"]:float(r["ls_band_bpm"]) for r in csv.DictReader(handle) if r["kind"]=="real"}
for source in sorted((HERE.parent/'common/windows').glob('csi_*.npz')):
 data=np.load(source);observed=data['waveform96']
 f=np.arange(.1,22/60,.00025)
 ls=float(f[np.argmax(lombscargle(np.arange(96)/2,observed-observed.mean(),2*np.pi*f))]*60)
 for pad in ['zero','reflect','edge','wrap']:
  wave=np.pad(observed,(0,32),mode='constant' if pad=='zero' else pad)
  wave-=wave.mean();x=np.rint(wave/np.max(np.abs(wave))*100).astype(int)
  for centers in [[8,24,48],[8,16,24],[8,16,32],[4,12,24],[16,32,48],[8,32,56]]:
   for r in [4,32]:
    result=decompose(x,3,r,centers)
    rows.append(dict(case=source.stem,padding=pad,initial_centers=json.dumps(centers),iterations=r,
     bpm=result['bpm'],band_priority_bpm=result['band_priority_bpm'],ls_observed48s_band_bpm=ls,
     abs_difference_ls_observed48s_bpm=abs(result['bpm']-ls),
     ls_main_input_band_bpm=baseline_map[source.stem],
     abs_difference_ls_main_input_bpm=abs(result['bpm']-baseline_map[source.stem])))
with (HERE/'diagnostics.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(HERE/'diagnostics.json').write_text(json.dumps(rows,indent=2))

aggregate=[]
for pad in ['zero','reflect','edge','wrap']:
 for init in sorted(set(r['initial_centers'] for r in rows)):
  for iteration in [4,32]:
   group=[r for r in rows if r['padding']==pad and r['initial_centers']==init and r['iterations']==iteration]
   aggregate.append(dict(padding=pad,initial_centers=init,iterations=iteration,n=len(group),
    mean_abs_difference_ls_observed48s_bpm=float(np.mean([r['abs_difference_ls_observed48s_bpm'] for r in group])),
    mean_abs_difference_ls_main_input_bpm=float(np.mean([r['abs_difference_ls_main_input_bpm'] for r in group])),
    agreement_ls_main_input_within_1bpm=float(np.mean([r['abs_difference_ls_main_input_bpm']<=1 for r in group]))))
(HERE/'diagnostics_aggregate.json').write_text(json.dumps(aggregate,indent=2))
