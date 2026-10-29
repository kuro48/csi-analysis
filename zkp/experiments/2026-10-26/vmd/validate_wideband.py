"""Single-tone wideband diagnostic: target is the injected tone, never presumed interference."""
import json
from pathlib import Path
import numpy as np
from model import decompose

HERE=Path(__file__).resolve().parent
rows=[]
for bpm in [3,6,9,12,18,21,24,30,42,51]:
    waveform=np.rint(80*np.sin(2*np.pi*bpm/60*np.arange(128)/2)).astype(int)
    old=decompose(waveform,3,4,[8,24,48])
    candidate=decompose(waveform,3,4,[8,16,24])
    dft=np.abs(np.fft.rfft(waveform))**2
    rows.append(dict(target_bpm=bpm,default_bpm=old['bpm'],candidate_bpm=candidate['bpm'],
        dft_bpm=float((np.argmax(dft[1:64])+1)*120/128),
        default_abs_error_bpm=abs(old['bpm']-bpm),candidate_abs_error_bpm=abs(candidate['bpm']-bpm),
        default_centers=old['centers'],candidate_centers=candidate['centers'],
        default_is_normal=old['is_normal'],candidate_is_normal=candidate['is_normal']))
result=dict(configuration=dict(modes=3,iterations=4,default_initial_centers=[8,24,48],candidate_initial_centers=[8,16,24],
    waveform='round(80*sin(2*pi*target_bpm/60*arange(128)/2))',samples=128,sample_rate_hz=2,observed_seconds=64,padded_samples=0),
    interpretation='Each injected sinusoid is the target. A high-frequency component cannot be identified as physiological target or interference from this signal alone. Low-centered initialization improves the previous low-band controls but can miss genuine higher-rate targets.',
    cases=rows)
(HERE/'wideband_validation.json').write_text(json.dumps(result,indent=2))
for row in rows:print(row['target_bpm'],row['default_bpm'],row['candidate_bpm'],row['dft_bpm'])
