"""Check four already-compiled circuit variants on every main raw-data window."""
import json
import subprocess
from pathlib import Path
import numpy as np
from model import decompose
HERE=Path(__file__).resolve().parent
rows=[]
for k,r,centers in [(1,1,None),(3,4,None),(5,8,None),(3,4,[8,16,24])]:
 name=f'vmd_k{k}_r{r}'+('_centers8_16_24' if centers else '')
 for source in sorted((HERE.parent/'common/windows').glob('csi_*.npz')):
  wave=np.load(source)['signal128'].astype(int).tolist()
  inp=HERE/'build'/f'{name}_{source.stem}_input.json'
  inp.write_text(json.dumps(dict(waveform=wave,commitmentNonce='20261026',parentCommitment='0')))
  ref=decompose(wave,k,r,centers);ref['iterations']=r
  refpath=HERE/'build'/f'{name}_{source.stem}_reference.json';refpath.write_text(json.dumps(ref))
  proc=subprocess.run(['node',str(HERE/'check_witness.js'),str(HERE/'build'),name,str(inp),str(refpath)],capture_output=True,text=True,check=True)
  row=json.loads(proc.stdout);row.update(case=source.stem,modes=k,iterations=r,initial_centers=centers)
  rows.append(row)
  (HERE/'all_windows_circuit_validation.json').write_text(json.dumps(rows,indent=2))
 print(name,'all main windows verified',flush=True)
