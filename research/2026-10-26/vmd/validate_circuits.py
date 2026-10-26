"""Compile isolated variants and cross-check outputs, centers and every final mode coefficient."""
import argparse
import re
import json
import subprocess
import time
from pathlib import Path
import numpy as np
from generate_variant import generate
from model import decompose

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
parser=argparse.ArgumentParser();parser.add_argument("--candidate-only",action="store_true");args=parser.parse_args()
records=json.loads((HERE/"circuit_validation.json").read_text()) if args.candidate_only else []
variants=[(3,4,[8,16,24])] if args.candidate_only else [(1,1,None),(3,4,None),(5,8,None),(3,4,[8,16,24])]
for k,r,centers in variants:
 name=f'vmd_k{k}_r{r}' + ('_centers8_16_24' if centers else '')
 circuit=HERE/'circuits'/f'{name}.circom'
 generate(k,r,circuit,centers)
 start=time.perf_counter()
 proc=subprocess.run([str(ROOT/'zkp/node_modules/.bin/circom2'),str(circuit),'--r1cs','--wasm','--sym','-l',str(ROOT/'zkp/node_modules'),'-o',str(HERE/'build')],capture_output=True,text=True,check=True)
 elapsed=time.perf_counter()-start
 (HERE/'build'/f'{name}_compile.log').write_text(proc.stdout+proc.stderr)
 nonlinear=int(re.search(r'non-linear constraints: (\d+)',proc.stdout)[1])
 linear=int(re.search(r'\nlinear constraints: (\d+)',proc.stdout)[1])
 for source in sorted((HERE.parent/'common/windows').glob('*.npz'))[:1]:
  x=np.load(source)['signal128'].astype(int).tolist()
  inp=HERE/'build'/f'{name}_input.json';inp.write_text(json.dumps(dict(waveform=x,commitmentNonce='20261026',parentCommitment='0')))
  ref=decompose(x,k,r,centers);ref['iterations']=r
  refpath=HERE/'build'/f'{name}_reference.json';refpath.write_text(json.dumps(ref))
  proc=subprocess.run(['node',str(HERE/'check_witness.js'),str(HERE/'build'),name,str(inp),str(refpath)],capture_output=True,text=True,check=True)
  result=json.loads(proc.stdout);result['compile_seconds']=elapsed;result['modes']=k;result['iterations']=r;result['initial_centers']=centers;result['nonlinear_constraints']=nonlinear;result['linear_constraints']=linear;result['constraints_total']=nonlinear+linear
  records.append(result)
 (HERE/'circuit_validation.json').write_text(json.dumps(records,indent=2))
 print(name,'validated',flush=True)
