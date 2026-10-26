"""Verify that changing disclosed DFT/mode/center values invalidates the same proof."""
import json
import subprocess
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]

def check():
    schema=json.loads((HERE/'public_schema.json').read_text())
    public=json.loads((HERE/'proof_public.json').read_text())
    prime=int(schema['field_modulus'])
    records=[]
    for group_name in ['debugDftReal','debugModeReal','debugCenters']:
        group=next(g for g in schema['groups'] if g['name']==group_name)
        index=group['public_start_index_zero_based']
        tampered=public.copy();tampered[index]=str((int(tampered[index])+1)%prime)
        path=HERE/'build'/f'tampered_{group_name}.json';path.write_text(json.dumps(tampered))
        start=time.perf_counter()
        proc=subprocess.run(['node',str(ROOT/'zkp/node_modules/snarkjs/build/cli.cjs'),'groth16','verify',str(HERE/'verification_key.json'),str(path),str(HERE/'proof.json')],capture_output=True,text=True)
        output=proc.stdout+proc.stderr
        (HERE/'build'/f'tampered_{group_name}_verify.log').write_text(output)
        rejected='Invalid proof' in output and 'OK!' not in output
        if not rejected:raise RuntimeError(f'Tamper rejection failed for {group_name}')
        records.append(dict(group=group_name,public_index_zero_based=index,original_value=public[index],
          tampered_value=tampered[index],rejected=rejected,verify_seconds=time.perf_counter()-start))
    (HERE/'intermediate_tamper_validation.json').write_text(json.dumps(records,indent=2))
    validation=json.loads((HERE/'proof_validation.json').read_text())
    validation['intermediate_tamper_groups_rejected']=[r['group'] for r in records]
    (HERE/'proof_validation.json').write_text(json.dumps(validation,indent=2))
    return records

if __name__=='__main__':print(json.dumps(check(),indent=2))
