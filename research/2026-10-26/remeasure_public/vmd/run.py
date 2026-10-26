"""Serialized, resumable public-output comparison. Each trace belongs to its measured proof."""
import argparse
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import time
from pathlib import Path
import numpy as np
from generate import HERE,ROOT,DATE,FIELD,configurations,estimate,sha256
from trace import validate_and_trace


def save(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2));tmp.replace(path)


def execute(command,log,timeout):
    start=time.perf_counter()
    with log.open('w') as f:
        process=subprocess.Popen(['/usr/bin/time','-l']+[str(c) for c in command],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        try:returncode=process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
            raise TimeoutError(f'{log.name} exceeded {timeout}s; process group terminated')
    text=log.read_text();rss=re.search(r'(\d+)\s+maximum resident set size',text)
    result=dict(wall_seconds=time.perf_counter()-start,max_rss_bytes=int(rss[1]) if rss else None,returncode=returncode)
    if returncode:
        if 'heap out of memory' in text.lower() or 'allocation failed' in text.lower():
            raise RuntimeError(f'resource_limit: Node heap allocation failed; see {log}')
        raise RuntimeError(f'Command failed ({returncode}); see {log}')
    return result,text


def run_config(config,args):
    if (HERE/'PAUSE_REQUEST').exists():
        print('Scheduling pause requested; no heavy stage started',flush=True)
        return
    directory=HERE/config['id'];schema=json.loads((directory/'schema.json').read_text())
    circuit=directory/schema['circuit'];build=directory/'build'
    summary_path=directory/'summary.json'
    if summary_path.exists():
        finished=json.loads(summary_path.read_text())
        if finished.get('status')=='verified' and finished.get('proof_count')==10:
            manifests=sorted((directory/'runs').glob('*/manifest.json'))
            if len(manifests)!=10:raise RuntimeError('Completed config has unexpected manifest count')
            source_hash=sha256(circuit);vkey_hash=sha256(directory/'verification_key.json')
            for manifest_path in manifests:
                record=json.loads(manifest_path.read_text())
                if record.get('status')!='verified' or not record.get('verified'):raise RuntimeError('Completed config contains unverified run')
                if record['source_sha256']!=source_hash or record['vkey_sha256']!=vkey_hash:raise RuntimeError('Completed config provenance mismatch')
                for file,expected in record['artifact_sha256'].items():
                    if sha256(manifest_path.parent/file)!=expected:raise RuntimeError('Completed config artifact hash mismatch')
            if args.prune_large and build.exists():
                shutil.rmtree(build);finished['large_artifacts_pruned']=True;save(summary_path,finished)
            update_index()
            print(json.dumps(dict(config=config['id'],status='verified_skipped',verified_runs=10)),flush=True)
            return
    previous_status=directory/'status.json'
    if previous_status.exists() and json.loads(previous_status.read_text()).get('status') in ['failed','timeout','resource_limit']:
        # Retrying after a pruned/failed attempt creates new keys. Preserve any old
        # verified public/proof/vkey together, never relabel them under new keys.
        if (directory/'compile.json').exists() or (directory/'runs').exists():
            archive=directory/'archived_attempts'/time.strftime('%Y%m%d_%H%M%S')
            archive.mkdir(parents=True,exist_ok=False)
            for item in list(directory.iterdir()):
                if item.name in ['build','archived_attempts',circuit.name,'schema.json']:continue
                if item.is_file() or item.name=='runs':shutil.move(str(item),str(archive/item.name))
            shutil.copyfile(circuit,archive/circuit.name);shutil.copyfile(directory/'schema.json',archive/'schema.json')
            if build.exists():shutil.rmtree(build)
            update_index()
    build.mkdir(exist_ok=True)
    status=dict(config=config,status='starting',estimate=estimate(config))
    state=directory/'status.json';save(state,status)
    cli=['node',f'--max-old-space-size={args.heap_mb}',ROOT/'zkp/node_modules/snarkjs/build/cli.cjs']
    def step(name,command,timeout=args.timeout):
        status['active_stage']=name;save(state,status)
        return execute(command,directory/f'{name}.log',timeout)
    try:
        if estimate(config)['minimum_ptau_power_estimate']>21:
            status.update(status='resource_limit',reason='Estimated required ptau exceeds available power21; no compile/setup/proof attempted');save(state,status);return
        if sha256(circuit)!=schema['circuit_sha256']:raise RuntimeError('Source/schema hash mismatch')
        if shutil.disk_usage(HERE).free<args.min_free_gib*1024**3:raise RuntimeError('resource_limit: insufficient free disk before config')
        name=circuit.stem
        r1cs=build/f'{name}.r1cs';wasm=build/f'{name}_js/{name}.wasm';sym=build/f'{name}.sym'
        if not (directory/'compile.json').exists() or not all(x.exists() for x in [r1cs,wasm,sym]):
            timing,text=step('compile',[ROOT/'zkp/node_modules/.bin/circom2',circuit,'--r1cs','--wasm','--sym','-l',ROOT/'zkp/node_modules','-o',build])
            nonlinear=int(re.search(r'non-linear constraints: (\d+)',text)[1]);linear=int(re.search(r'\nlinear constraints: (\d+)',text)[1])
            public=int(re.search(r'public inputs: (\d+)',text)[1])+int(re.search(r'public outputs: (\d+)',text)[1])
            required=(nonlinear+linear+public).bit_length()
            save(directory/'compile.json',dict(**timing,constraints=nonlinear+linear,public_signals=public,required_power_conservative=required,
              source_sha256=sha256(circuit),r1cs_sha256=sha256(r1cs),wasm_sha256=sha256(wasm),sym_sha256=sha256(sym)))
        compiled=json.loads((directory/'compile.json').read_text())
        if compiled['source_sha256']!=sha256(circuit):raise RuntimeError('Compiled source provenance mismatch')
        if compiled['public_signals']!=schema['public_signal_count']:raise RuntimeError('Compiled public count mismatch')
        for artifact,key in [(r1cs,'r1cs_sha256'),(wasm,'wasm_sha256'),(sym,'sym_sha256')]:
            if artifact.exists() and sha256(artifact)!=compiled[key]:raise RuntimeError('Compiled artifact hash mismatch')
        if compiled['required_power_conservative']>21:
            status.update(status='resource_limit',reason='Actual constraints plus public exceed ptau21');save(state,status);return
        if compiled['constraints']>1_000_000:
            cli[1]=f'--max-old-space-size={max(args.heap_mb,12288)}'
        status['effective_heap_mb']=int(cli[1].split('=')[1]);save(state,status)
        ptau=ROOT/'zkp/keys/powersOfTau28_hez_final_19.ptau' if compiled['required_power_conservative']<=19 else args.ptau21
        if not ptau.exists():
            status.update(status='resource_limit',reason=f'Required ptau missing: {ptau}');save(state,status);return
        zkey=build/'final.zkey';vkey=directory/'verification_key.json'
        if not (directory/'setup.json').exists() or not zkey.exists() or not vkey.exists():
            setup,_=step('setup',cli+['groth16','setup',r1cs,ptau,build/'initial.zkey'])
            contribution,_=step('contribution',cli+['zkey','contribute',build/'initial.zkey',zkey,'--name=public comparison local setup','-e='+secrets.token_hex(32)])
            step('export_key',cli+['zkey','export','verificationkey',zkey,vkey])
            save(directory/'setup.json',dict(setup=setup,contribution=contribution,ptau=str(ptau),
              ptau_sha256=sha256(ptau),zkey_sha256=sha256(zkey),vkey_sha256=sha256(vkey),
              source_sha256=sha256(circuit),r1cs_sha256=compiled['r1cs_sha256'],keys_scope='Local experiment only'))
            (build/'initial.zkey').unlink(missing_ok=True)
        setup=json.loads((directory/'setup.json').read_text())
        if setup['vkey_sha256']!=sha256(vkey) or setup['source_sha256']!=sha256(circuit):raise RuntimeError('Key/source provenance mismatch')
        if zkey.exists() and sha256(zkey)!=setup['zkey_sha256']:raise RuntimeError('Proving key hash mismatch')
        sources=sorted((DATE/'common/windows').glob('csi_*.npz'))
        if len(sources)!=8:raise RuntimeError('Expected exactly eight main Raw windows')
        representative=next(s for s in sources if s.stem=='csi_20260526_034004_w0')
        jobs=[(s,0) for s in sources]+[(representative,1),(representative,2)]
        completed=[]
        for source,repeat in jobs:
            run_id=f'{source.stem}_repeat{repeat}';run_dir=directory/'runs'/run_id;run_dir.mkdir(parents=True,exist_ok=True)
            manifest_path=run_dir/'manifest.json'
            if manifest_path.exists():
                old=json.loads(manifest_path.read_text())
                if old.get('status')=='verified':
                    for file,expected in old['artifact_sha256'].items():
                        if sha256(run_dir/file)!=expected:raise RuntimeError(f'Resume hash mismatch: {run_id}/{file}')
                    if old['source_sha256']!=sha256(circuit) or old['vkey_sha256']!=sha256(vkey):raise RuntimeError('Resume config/key mismatch')
                    completed.append(old);continue
            waveform=np.load(source)['signal128'].astype(int).tolist()
            if repeat>0:
                first_input=directory/'runs'/f'{source.stem}_repeat0'/'input.json'
                if not first_input.exists():raise RuntimeError('Representative repeat0 input missing')
                if not (run_dir/'input.json').exists():shutil.copyfile(first_input,run_dir/'input.json')
                if (run_dir/'input.json').read_bytes()!=first_input.read_bytes():raise RuntimeError('Repeated timing input must be byte-identical')
            elif not (run_dir/'input.json').exists():
                save(run_dir/'input.json',dict(waveform=waveform,commitmentNonce=str(secrets.randbits(128)),parentCommitment='0'))
            if json.loads((run_dir/'input.json').read_text())['waveform']!=waveform:raise RuntimeError('Input waveform mismatch')
            run_status=dict(status='running',config=config,run_id=run_id,window=source.stem,repeat=repeat)
            save(manifest_path,run_status)
            def run_step(name,cmd):
                status['active_stage']=f'{run_id}/{name}';save(state,status)
                return execute(cmd,run_dir/f'{name}.log',args.timeout)
            witness,_=run_step('witness',['node',HERE/'witness.js',directory,run_dir])
            proof,_=run_step('prove',cli+['groth16','prove',zkey,run_dir/'witness.wtns',run_dir/'proof.json',run_dir/'public.json'])
            verification,text=run_step('verify',cli+['groth16','verify',vkey,run_dir/'public.json',run_dir/'proof.json'])
            if 'OK!' not in text:raise RuntimeError('Proof verification did not report success')
            public=json.loads((run_dir/'public.json').read_text())
            if public!=json.loads((run_dir/'witness_public.json').read_text()):raise RuntimeError('Proof public differs from same-run witness')
            group=next(g for g in schema['groups'] if g['name']=='debugModeReal')
            changed=public.copy();index=group['public_start_index_zero_based'];changed[index]=str((int(changed[index])+1)%FIELD)
            save(run_dir/'tampered_public.json',changed)
            # snarkjs uses return code1 for a correctly rejected proof; inspect the exact output.
            tamper=subprocess.run([str(x) for x in cli+['groth16','verify',vkey,run_dir/'tampered_public.json',run_dir/'proof.json']],capture_output=True,text=True,timeout=60)
            tamper_text=tamper.stdout+tamper.stderr;(run_dir/'tamper.log').write_text(tamper_text)
            if 'Invalid proof' not in tamper_text or 'OK!' in tamper_text:raise RuntimeError('Intermediate tamper was not rejected')
            binding=dict(config_id=config['id'],window=source.stem,repeat=repeat,run_id=run_id,
              source_sha256=sha256(circuit),input_npz_sha256=sha256(source),input_json_sha256=sha256(run_dir/'input.json'),
              r1cs_sha256=compiled['r1cs_sha256'],wasm_sha256=compiled['wasm_sha256'],vkey_sha256=sha256(vkey),
              proof_sha256=sha256(run_dir/'proof.json'),public_sha256=sha256(run_dir/'public.json'))
            result=validate_and_trace(directory,run_dir,binding)
            record=dict(run_status)
            record.update(status='verified',verified=True,**binding,result=result,proof_verified=True,tamper_rejected=True,
              trace_from='public.json',vkey_path='../../verification_key.json',
              public_schema_verified=True,independent_integer_reference_all_stages_match=True,
              witness=witness,prove=proof,verify=verification,witness_calculation=json.loads((run_dir/'witness_timing.json').read_text()),
              artifact_sha256={file:sha256(run_dir/file) for file in ['input.json','proof.json','public.json','trace.json','witness_public.json']})
            save(manifest_path,record);completed.append(record)
            update_index()
            (run_dir/'witness.wtns').unlink(missing_ok=True)
            status['verified_runs']=len(completed);save(state,status)
        unique=[r for r in completed if r['repeat']==0]
        representative_runs=[r for r in completed if r['window']==representative.stem]
        summary=dict(config=config,status='verified',unique_raw_count=len(unique),proof_count=len(completed),
          representative_prove_seconds=[r['prove']['wall_seconds'] for r in representative_runs],
          representative_prove_median_seconds=float(np.median([r['prove']['wall_seconds'] for r in representative_runs])),
          unique_raw_results=[dict(window=r['window'],**r['result']) for r in unique],compile=compiled,setup=setup)
        save(directory/'summary.json',summary)
        if args.prune_large:
            # Only reproducible files generated under THIS config/build are deleted, after hashes/10 proofs persist.
            if build.resolve().parent!=directory.resolve():raise RuntimeError('Unexpected prune path')
            shutil.rmtree(build)
            summary['large_artifacts_pruned']=True;save(directory/'summary.json',summary)
        status.update(status='verified',verified_runs=len(completed),active_stage=None);save(state,status)
    except Exception as error:
        reason=str(error);status.update(status='timeout' if isinstance(error,TimeoutError) else 'failed',reason=reason)
        if 'resource_limit' in reason or 'No space' in reason:status['status']='resource_limit'
        if args.prune_large and build.exists():
            artifact_hashes={str(f.relative_to(build)):dict(bytes=f.stat().st_size,sha256=sha256(f)) for f in build.rglob('*') if f.is_file()}
            save(directory/'partial_build_hashes.json',artifact_hashes)
            if build.resolve().parent!=directory.resolve():raise RuntimeError('Unexpected failed-build prune path')
            shutil.rmtree(build);status['partial_build_pruned']=True
        save(state,status)
        update_index()
        print(json.dumps(status),flush=True)


def update_index():
    items=[]
    for manifest in sorted(HERE.glob('*/runs/*/manifest.json')):
        record=json.loads(manifest.read_text())
        items.append(dict(config_id=record['config']['id'],window=record['window'],repeat=record['repeat'],
          status=record['status'],verified=record.get('verified',False),manifest_path=str(manifest.relative_to(HERE)),
          trace_path=str((manifest.parent/'trace.json').relative_to(HERE)),
          public_path=str((manifest.parent/'public.json').relative_to(HERE)),
          proof_path=str((manifest.parent/'proof.json').relative_to(HERE)),
          vkey_path=str((manifest.parents[2]/'verification_key.json').relative_to(HERE))))
    save(HERE/'runs_index.json',dict(scope='same-run public-output proof remeasurement, real only',runs=items))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True,choices=[c['id'] for c in configurations()])
    parser.add_argument('--ptau21',type=Path,default=DATE/'.cache/ppot_0080_21.ptau')
    parser.add_argument('--timeout',type=int,default=1800);parser.add_argument('--heap-mb',type=int,default=8192)
    parser.add_argument('--min-free-gib',type=float,default=3);parser.add_argument('--prune-large',action='store_true')
    args=parser.parse_args();run_config(next(c for c in configurations() if c['id']==args.config),args)

if __name__=='__main__':main()
