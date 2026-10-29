"""Run diagnostic stages explicitly; no effect on normal circuits/benchmarks.

Do not run compile/witness/prove concurrently with baseline timing experiments.
"""
import argparse
import json
import re
import secrets
import subprocess
import time
from pathlib import Path
from generate_debug import CIRCUIT_NAME,HERE,ROOT,generate
from prepare_input import prepare
from export_trace import export


def command(args,log):
    start=time.perf_counter()
    proc=subprocess.run([str(x) for x in args],capture_output=True,text=True)
    (HERE/log).write_text(proc.stdout+proc.stderr)
    if proc.returncode:raise RuntimeError(f'Failed, see {log}')
    return time.perf_counter()-start,proc.stdout


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','compile','witness','prove']);args=parser.parse_args()
    build=HERE/'build'
    snark=[ 'node','--max-old-space-size=8192',ROOT/'zkp/node_modules/snarkjs/build/cli.cjs']
    if args.stage=='prepare':
        generate();prepare()
    elif args.stage=='compile':
        seconds,stdout=command([ROOT/'zkp/node_modules/.bin/circom2',HERE/f'{CIRCUIT_NAME}.circom',
          '--r1cs','--wasm','--sym','-l',ROOT/'zkp/node_modules','-o',build],'build/compile.log')
        nonlinear=int(re.search(r'non-linear constraints: (\d+)',stdout)[1]);linear=int(re.search(r'\nlinear constraints: (\d+)',stdout)[1])
        public=int(re.search(r'public inputs: (\d+)',stdout)[1])+int(re.search(r'public outputs: (\d+)',stdout)[1])
        (HERE/'compile.json').write_text(json.dumps(dict(compile_seconds=seconds,nonlinear_constraints=nonlinear,
          linear_constraints=linear,total_constraints=nonlinear+linear,public_signals=public,
          conservative_constraints_plus_public=nonlinear+linear+public,
          fits_ptau19_conservative=nonlinear+linear+public<2**19),indent=2))
    elif args.stage=='witness':
        command(['node',HERE/'export_witness.js'],'build/witness.log')
        command(snark+['wtns','check',build/f'{CIRCUIT_NAME}.r1cs',build/'witness.wtns'],'build/wtns_check.log')
        trace=export();print(json.dumps(trace['result']))
        validation=json.loads((HERE/'witness_validation.json').read_text());validation['r1cs_witness_check_passed']=True
        (HERE/'witness_validation.json').write_text(json.dumps(validation,indent=2))
    elif args.stage=='prove':
        info=json.loads((HERE/'compile.json').read_text())
        if not info['fits_ptau19_conservative']:raise RuntimeError('Circuit exceeds ptau19 conservative bound')
        ptau=ROOT/'zkp/keys/powersOfTau28_hez_final_19.ptau'
        setup_seconds,_=command(snark+['groth16','setup',build/f'{CIRCUIT_NAME}.r1cs',ptau,build/'debug_0000.zkey'],'build/setup.log')
        contribution_seconds,_=command(snark+['zkey','contribute',build/'debug_0000.zkey',build/'debug_final.zkey',
          '--name=local diagnostic contribution','-e='+secrets.token_hex(32)],'build/contribution.log')
        command(snark+['zkey','export','verificationkey',build/'debug_final.zkey',HERE/'verification_key.json'],'build/export_key.log')
        prove_seconds,_=command(snark+['groth16','prove',build/'debug_final.zkey',build/'witness.wtns',HERE/'proof.json',HERE/'proof_public.json'],'build/prove.log')
        if json.loads((HERE/'proof_public.json').read_text())!=json.loads((HERE/'public.json').read_text()):raise RuntimeError('Proof and displayed public outputs differ')
        verify_seconds,stdout=command(snark+['groth16','verify',HERE/'verification_key.json',HERE/'proof_public.json',HERE/'proof.json'],'build/verify.log')
        if 'OK!' not in stdout:raise RuntimeError('Verification did not report OK')
        # A public waveform value is changed to check the verifier rejects altered disclosures.
        tampered=json.loads((HERE/'proof_public.json').read_text());tampered[4]=str((int(tampered[4])+1)%int(json.loads((HERE/'public_schema.json').read_text())['field_modulus']))
        (build/'tampered_public.json').write_text(json.dumps(tampered))
        proc=subprocess.run([str(x) for x in snark+['groth16','verify',HERE/'verification_key.json',build/'tampered_public.json',HERE/'proof.json']],capture_output=True,text=True)
        (build/'tampered_verify.log').write_text(proc.stdout+proc.stderr)
        if 'OK!' in proc.stdout or 'Invalid proof' not in proc.stdout+proc.stderr:raise RuntimeError('Tamper rejection not confirmed')
        (HERE/'proof_validation.json').write_text(json.dumps(dict(proof_generated=True,proof_verified=True,
          proof_public_matches_display=True,tampered_public_rejected=True,public_signal_count=len(tampered),
          setup_seconds=setup_seconds,contribution_seconds=contribution_seconds,prove_seconds=prove_seconds,verify_seconds=verify_seconds,
          keys_scope='Fresh local diagnostic key using existing ptau19; not normal circuit keys or a production trusted-setup ceremony'),indent=2))
        from validate_intermediate_tamper import check
        check()

if __name__=='__main__':main()
