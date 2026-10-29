"""Evaluate initialization candidate on synthetic controls without tuning to their labels."""
import json
from pathlib import Path
import numpy as np
from model import decompose
from run_sweep import controls

HERE=Path(__file__).resolve().parent
cases=list(controls())
for path in sorted((HERE.parent/'common/synthetic').glob('*.npz')):
    data=np.load(path)
    cases.append((path.stem,data['signal128'],float(data['target_bpm']),'synthetic_csi'))
rows=[]
for name,wave,target,kind in cases:
    old=decompose(wave,3,4,[8,24,48])
    candidate=decompose(wave,3,4,[8,16,24])
    rows.append(dict(case=name,kind=kind,ground_truth_bpm=target,
        default_bpm=old['bpm'],candidate_bpm=candidate['bpm'],
        default_abs_error_bpm=abs(old['bpm']-target),candidate_abs_error_bpm=abs(candidate['bpm']-target)))
summary=[]
for kind in ['clean','noise','strong_interferer','synthetic_csi','all_direct_controls','all_synthetic']:
    group=[r for r in rows if r['kind']==kind or kind=='all_synthetic' or (kind=='all_direct_controls' and r['kind']!='synthetic_csi')]
    old=np.asarray([r['default_abs_error_bpm'] for r in group]);new=np.asarray([r['candidate_abs_error_bpm'] for r in group])
    summary.append(dict(kind=kind,n=len(group),default_gt_mae_bpm=float(old.mean()),candidate_gt_mae_bpm=float(new.mean()),
        default_within_1bpm=float(np.mean(old<=1)),candidate_within_1bpm=float(np.mean(new<=1)),
        improved_count=int(np.sum(new<old)),unchanged_count=int(np.sum(new==old)),worsened_count=int(np.sum(new>old)),
        default_max_error_bpm=float(old.max()),candidate_max_error_bpm=float(new.max())))
result=dict(configuration=dict(modes=3,iterations=4,default_initial_centers=[8,24,48],candidate_initial_centers=[8,16,24]),
    interpretation='Candidate chosen from real-data LS agreement, evaluated here against injected synthetic target. This is a sensitivity check, not independent physiological validation.',
    summary=summary,cases=rows)
(HERE/'candidate_validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(summary,indent=2))
