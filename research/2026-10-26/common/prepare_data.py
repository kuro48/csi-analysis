"""Reproducible, timestamp-aware common inputs; raw captures remain read-only."""
from __future__ import annotations
import argparse
import hashlib
import json
import types
import __future__
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly
from sklearn.decomposition import PCA

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RAW = Path.home() / 'Research/WiFi-CSI-Privacy/Data/Raw'

def load_pipeline():
    source = ROOT / 'backend/app/services/breathing_pipeline.py'
    module = types.ModuleType('research_pipeline')
    exec(compile(source.read_text(), str(source), 'exec', flags=__future__.annotations.compiler_flag), module.__dict__)
    return module

def inspect_frames(p, path):
    counts, first_metadata = {}, {}
    total = missing = 0
    parser = p._new_chunked_picoscenes_parser()
    for offset, count in p._iter_picoscenes_frame_batches(str(path), 32):
        parser.seek(str(path), offset, count)
        for f in parser.raw:
            total += 1
            c = f.get('CSI')
            if not c or c.get('CSI') is None or p._system_timestamp_ns(f) is None:
                missing += 1
                continue
            n = np.asarray(c['CSI']).size
            counts[str(n)] = counts.get(str(n), 0) + 1
            if str(n) not in first_metadata:
                first_metadata[str(n)] = {k: np.asarray(v).tolist() for k, v in c.items() if k != 'CSI' and np.asarray(v).size < 40}
        parser.raw.clear()
    return {'raw_frame_count': total, 'missing_csi_or_timestamp_frames': missing, 'width_counts': counts,
            'csi_metadata_by_width': first_metadata}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--raw', type=Path, default=RAW)
    args = parser.parse_args()
    p = load_pipeline()
    windows = OUT / 'windows'
    windows.mkdir(exist_ok=True)
    manifest = {'schema_version': 1, 'ground_truth_bpm': None, 'ground_truth_note': 'No synchronous respiration labels found in Raw; filenames kokyu/daremoinai are qualitative only.',
                'protocol': {'window_seconds': 48.0, 'window_start_seconds': 0.0, 'nominal_uniform_fs_hz': 100,
                             'vmd_fs_hz': 2, 'vmd_observed_samples': 96, 'vmd_padding_samples': 32,
                             'subcarrier_selection': 'modal flattened CSI width per repository loader; not necessarily physical subcarriers',
                             'preprocessing': 'sort and deduplicate systemns; interpolate amplitude to 100Hz within first 48sec; SNR select up to256; original bandpass/PCA selection; resample_poly(1,50); zero-pad128; center and scale+-100',
                             'pca_solver': 'full deterministic SVD', 'ground_truth_used_for_selection': False},
                'source_pipeline_sha256': hashlib.sha256((ROOT/'backend/app/services/breathing_pipeline.py').read_bytes()).hexdigest(),
                'files': [], 'excluded': []}
    all_paths = sorted(args.raw.rglob('*'))
    for path in all_paths:
        if not path.is_file(): continue
        if path.suffix != '.csi':
            manifest['excluded'].append({'path':str(path),'reason':'not a PicoScenes .csi capture; separate PCAP decoder needed'})
            continue
        print('PROCESS',path,flush=True)
        try:
            info = inspect_frames(p,path)
            a, ts = p.load_csi_matrix_with_timestamps(str(path))
            original_diff = np.diff(ts).astype(float)/1e9
            order = np.argsort(ts,kind='stable'); a,ts = a[order],ts[order]
            unique=np.r_[True,np.diff(ts)>0];duplicates=int((~unique).sum());a,ts=a[unique],ts[unique]
            t=(ts-ts[0]).astype(float)/1e9
            info.update({'source':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'modal_width':a.shape[1],
                         'retained_rows':len(ts),'duration_seconds':float(t[-1]),'duplicate_timestamps_removed':duplicates,
                         'original_nonpositive_dt_count':int((original_diff<=0).sum()),
                         'dt_median_seconds':float(np.median(np.diff(t))), 'dt_min_seconds':float(np.min(np.diff(t))),
                         'dt_max_seconds':float(np.max(np.diff(t))), 'dt_p95_seconds':float(np.percentile(np.diff(t),95)),
                         'effective_average_hz':float((len(t)-1)/t[-1]), 'gaps_over_500ms':int((np.diff(t)>.5).sum()),
                         'ground_truth_bpm':None})
            if t[-1] < 48 or len(ts)<64:
                info['excluded_reason']='less than48sec or fewer than64frames'
                manifest['excluded'].append(info);continue
            mask=t<48
            wa, wt,wts=a[mask],t[mask],ts[mask]
            # Keep interpolation in amplitude domain; never interpolate complex phase before abs.
            u=np.arange(4800)/100
            amp=np.abs(a)
            uniform=np.column_stack([np.interp(u,t,amp[:,i]) for i in range(a.shape[1])])
            selected,indices,snr=p.select_subcarriers_by_snr(uniform,100,.1,1.,min(256,a.shape[1]))
            filtered=p.bandpass_filter(selected,100,.1,1.)
            pcs=PCA(n_components=3,svd_solver='full').fit_transform(filtered)
            pc,idx,scores=p.select_respiration_pc(pcs,100,.1,1.)
            wave96=resample_poly(pc,1,50)
            wave128=np.pad(wave96,(0,32));wave128-=wave128.mean()
            ints=np.asarray(p.prepare_vmd_approx_input(pc)['waveform'],dtype=np.int64)
            window_id=path.stem+'_w0'
            np.savez_compressed(windows/(window_id+'.npz'), csi_complex=wa,timestamps_ns=wts,time_seconds=wt,
                                waveform128=wave128,signal128=ints,waveform96=wave96,times128=np.arange(128)/2,
                                pc100=pc,pcs100=pcs,selected_indices=indices,snr=snr,
                                raw_amplitude_mean=np.mean(np.abs(wa),axis=1))
            info.update({'window_id':window_id,'npz':'windows/'+window_id+'.npz','window_rows':len(wt),
                         'window_first_seconds':float(wt[0]),'window_last_seconds':float(wt[-1]),'pca_index_zero_based':idx,
                         'pc_scores':list(map(float,scores)),'selected_columns':indices.tolist(),
                         'warning':'Irregular/sparse capture interpolated for VMD; LS retains original timestamps; no physiological ground truth.'})
            manifest['files'].append(info)
            (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
            print('READY',window_id,flush=True)
        except Exception as exc:
            manifest['excluded'].append({'path':str(path),'reason':repr(exc)})
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False))
    print('FINISHED',len(manifest['files']),'windows',flush=True)
if __name__=='__main__': main()
