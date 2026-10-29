"""Validate shared-array alignment, quantization, source integrity, and manifest coverage."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

base=Path(__file__).resolve().parent
repo=base.parents[3]

def recorded_path(value):
    """Resolve moved files without modifying the historical manifest itself."""
    text=str(value)
    marker='research/2026-10-26/'
    if marker in text:
        return base.parent / text.split(marker,1)[1]
    path=Path(value)
    if not path.exists() and '/Data/Raw/' in text:
        return repo.parents[1] / 'Data/Raw' / text.split('/Data/Raw/',1)[1]
    return path
manifest=json.loads((base/'manifest.json').read_text())
rows=[]
for record in manifest['files']:
    assert hashlib.sha256(recorded_path(record['source']).read_bytes()).hexdigest()==record['sha256']
    with np.load(base/record['npz']) as d:
        assert d['csi_complex'].ndim==2
        assert len(d['timestamps_ns'])==len(d['csi_complex'])==len(d['time_seconds'])
        assert np.all(np.diff(d['timestamps_ns'])>0)
        assert np.all(np.diff(d['time_seconds'])>0)
        assert d['time_seconds'][0]==0 and d['time_seconds'][-1]<48
        assert len(d['signal128'])==len(d['waveform128'])==128
        assert len(d['waveform96'])==96
        assert max(abs(d['signal128']))<=100
        assert np.issubdtype(d['signal128'].dtype,np.integer)
        for key in d.files: assert np.isfinite(d[key]).all(),(record['window_id'],key)
        assert np.allclose(d['waveform128'][:96]-d['waveform96'],d['waveform128'][96])
        expected=np.rint(d['waveform128']/max(abs(d['waveform128']))*100).astype(int)
        assert np.array_equal(expected,d['signal128'])
    meta=record['csi_metadata_by_width'][str(record['modal_width'])]
    rows.append({k:record[k] for k in ['window_id','raw_frame_count','retained_rows','window_rows','modal_width','duration_seconds','effective_average_hz','dt_median_seconds','dt_p95_seconds','dt_max_seconds','gaps_over_500ms']})
    rows[-1].update({'num_tones':meta['numTones'],'num_tx':meta['numTx'],'num_rx':meta['numRx']})
    assert meta['numTones']*meta['numTx']*meta['numRx']*meta['numCSI']==record['modal_width']
synthetic=json.loads((base/'synthetic/manifest.json').read_text())
for case in synthetic['cases']:
    with np.load(recorded_path(case['npz'])) as d:
        assert float(d['target_bpm'])==case['target_bpm']
        assert d['csi_complex'].shape==(4800,32)
        assert np.all(np.diff(d['timestamps_ns'])>0)
        assert d['signal128'].shape==(128,)
        for key in d.files: assert np.isfinite(d[key]).all()
with (base/'data_quality.csv').open('w') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
result={'status':'PASS','real_windows':len(rows),'synthetic_windows':len(synthetic['cases']),
        'checks':['source SHA256','array/timestamp alignment','strict monotonic timestamps','48s window bounds',
                  'finite arrays','128point integer range','96point zero padding and quantization equivalence',
                  'flat width = tones * tx * rx * numCSI','synthetic targets and shapes']}
(base/'validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
