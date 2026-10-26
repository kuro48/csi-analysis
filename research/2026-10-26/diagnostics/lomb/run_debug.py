#!/usr/bin/env python3
"""Expose actual E2E circuit stage signals in an independent diagnostic circuit.
Default generates source only. Compile, witness, and proof require explicit flags.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,re,secrets,struct,subprocess,sys,time
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
BASE=HERE.parents[1]
BUILD=HERE/'build'
FIELD=21888242871839275222246405745257275088548364400416034343698204186575808495617
SHAPES=[
 ('csiCommitment',[],False,'original Poseidon commitment'),
 ('isNormal',[],False,'original normality output'),
 ('selectedSubcarrier',[],False,'original selected local column index'),
 ('estimatedFrequencyBin',[],False,'original normal-band peak bin'),
 ('globalPeakFrequencyBin',[],False,'original full-grid peak bin'),
 ('debugSignedI',[64,8],True,'signedI'),('debugSignedQ',[64,8],True,'signedQ'),
 ('debugMagnitudeSquared',[64,8],False,'magnitudeSquared'),('debugCentered',[64,8],True,'centered = 64*mag2 - sum(mag2)'),
 ('debugSignalNorm',[8],False,'signalNorm'),
 ('debugCosBasis',[32,64],True,'timestampBasis.cosBasis - 1024'),('debugSinBasis',[32,64],True,'timestampBasis.sinBasis - 1024'),
 ('debugCosNorm',[32],False,'cosNorm'),('debugSinNorm',[32],False,'sinNorm'),
 ('debugCrossNorm',[32],True,'basisCrossNorm'),('debugDeterminant',[32],False,'determinantBasis'),
 ('debugCosProjection',[8,32],True,'cosineProjection'),('debugSinProjection',[8,32],True,'sineProjection'),
 ('debugNumerator',[8,32],False,'scoreNumerator'),('debugDenominator',[8,32],False,'scoreDenominator'),
 ('debugBandPeak',[8],False,'targetMaxIndex[sc][NORMAL_BINS-1]'),
 ('debugGlobalPeak',[8],False,'globalMaxIndex[sc][FREQS-1]'),
]

def dump(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
def product(shape):return math.prod(shape) if shape else 1

def generate():
    source=ROOT/'zkp/circuits/csi_lomb_scargle_end_to_end.circom'
    text=source.read_text().replace('LombScargleCSIEndToEnd','LombScargleCSIDiagnostic')
    declaration='\n    // DIAGNOSTIC ONLY: these public outputs intentionally reveal private CSI and every analysis stage.\n'
    for name,shape,signed,meaning in SHAPES[5:]:
        declaration+=f"    signal output {name}{''.join('['+str(d)+']' for d in shape)};\n"
    needle='    signal output globalPeakFrequencyBin;'
    assert text.count(needle)==1
    text=text.replace(needle,needle+declaration)
    block='''
    // Bind diagnostic public outputs directly to existing constrained stage signals.
    for (var i = 0; i < SAMPLE_COUNT; i++) {
        for (var sc = 0; sc < SUBCARRIERS; sc++) {
            debugSignedI[i][sc] <== signedI[i][sc];
            debugSignedQ[i][sc] <== signedQ[i][sc];
            debugMagnitudeSquared[i][sc] <== magnitudeSquared[i][sc];
            debugCentered[i][sc] <== centered[i][sc];
        }
    }
    for (var f = 0; f < FREQS; f++) {
        debugCosNorm[f] <== cosNorm[f];
        debugSinNorm[f] <== sinNorm[f];
        debugCrossNorm[f] <== basisCrossNorm[f];
        debugDeterminant[f] <== determinantBasis[f];
        for (var i = 0; i < SAMPLE_COUNT; i++) {
            debugCosBasis[f][i] <== timestampBasis.cosBasis[f][i] - TRIG_OFFSET;
            debugSinBasis[f][i] <== timestampBasis.sinBasis[f][i] - TRIG_OFFSET;
        }
    }
    for (var sc = 0; sc < SUBCARRIERS; sc++) {
        debugSignalNorm[sc] <== signalNorm[sc];
        debugBandPeak[sc] <== targetMaxIndex[sc][NORMAL_BINS-1];
        debugGlobalPeak[sc] <== globalMaxIndex[sc][FREQS-1];
        for (var f = 0; f < FREQS; f++) {
            debugCosProjection[sc][f] <== cosineProjection[sc][f];
            debugSinProjection[sc][f] <== sineProjection[sc][f];
            debugNumerator[sc][f] <== scoreNumerator[sc][f];
            debugDenominator[sc][f] <== scoreDenominator[sc][f];
        }
    }
'''
    marker='\n}\n\n// Feasibility-sized'
    assert text.count(marker)==1
    text=text.replace(marker,block+marker)
    text='// DIAGNOSTIC VARIANT: public CSI and stage signals; not a privacy-preserving deployment.\n'+text
    (HERE/'diagnostic.circom').write_text(text)
    offset=0;fields=[]
    for name,shape,signed,meaning in SHAPES:
        n=product(shape)
        fields.append({'name':name,'shape':shape,'count':n,'public_start_zero_based':offset,'signed':signed,'source_signal':meaning})
        offset+=n
    fields.append({'name':'timestampsMs','shape':[64],'count':64,'public_start_zero_based':offset,'signed':False,'role':'public_input'})
    dump(HERE/'public_schema.json',{'field_modulus':str(FIELD),'array_order':'row-major, final index fastest',
         'integer_json_encoding':'decimal strings, to preserve exact values above2^53',
         'signed_decode':'field value greater than p/2 is represented as value-p',
         'public_outputs':offset,'public_inputs':64,'fields':fields,
         'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
         'diagnostic_sha256':hashlib.sha256(text.encode()).hexdigest(),
         'warning':'All listed outputs are PUBLIC. Diagnostic use only; this reveals CSI and inferred waveforms.'})
    print('Generated',offset,'public outputs +64 timestamp inputs',flush=True)

def command(args,name,timeout=3600):
    start=time.perf_counter()
    with (HERE/name).open('w') as log:
        result=subprocess.run(list(map(str,args)),stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
    elapsed=time.perf_counter()-start
    if result.returncode:raise RuntimeError(f'{name}: returncode {result.returncode}')
    return elapsed

def compile_():
    BUILD.mkdir(exist_ok=True)
    seconds=command([ROOT/'zkp/node_modules/.bin/circom2',HERE/'diagnostic.circom','--O2','--r1cs','--wasm','--sym','-o',BUILD,'-l',ROOT/'zkp/node_modules','-l',ROOT/'zkp/circuits'],'compile.log')
    txt=(HERE/'compile.log').read_text()
    result={'compile_seconds':seconds,'optimization':'O2','nonlinear_constraints':int(re.search(r'non-linear constraints: (\d+)',txt)[1]),'linear_constraints':int(re.search(r'\nlinear constraints: (\d+)',txt)[1])}
    result['constraints']=result['nonlinear_constraints']+result['linear_constraints']
    dump(HERE/'compile_metrics.json',result);print(result,flush=True)

def names(name,shape):
    if not shape:return [name]
    result=[]
    for i in range(shape[0]):result.extend(names(f'{name}[{i}]',shape[1:]))
    return result

def reshape(vals,shape):
    if not shape:return vals[0]
    if len(shape)==1:return vals
    stride=product(shape[1:])
    return [reshape(vals[i*stride:(i+1)*stride],shape[1:]) for i in range(shape[0])]

def decode_public(input_path):
    schema=json.loads((HERE/'public_schema.json').read_text())
    sym={}
    for line in (BUILD/'diagnostic.sym').read_text().splitlines():
        _,witness_index,_,name=line.split(',',3);sym[name]=int(witness_index)
    raw=(BUILD/'witness.wtns').read_bytes()
    assert raw[:4]==b'wtns'
    section_count=struct.unpack_from('<I',raw,8)[0];pos=12;field_bytes=None;section=None
    for _ in range(section_count):
        kind,length=struct.unpack_from('<IQ',raw,pos);pos+=12
        if kind==1:
            field_bytes=struct.unpack_from('<I',raw,pos)[0]
            assert int.from_bytes(raw[pos+4:pos+4+field_bytes],'little')==FIELD
        if kind==2:section=memoryview(raw)[pos:pos+length]
        pos+=length
    assert section is not None and field_bytes==32
    total=schema['public_outputs']+schema['public_inputs']
    public=[str(int.from_bytes(section[i*field_bytes:(i+1)*field_bytes],'little')) for i in range(1,total+1)]
    result={}
    for field in schema['fields']:
        start=field['public_start_zero_based']; vals=[]
        for offset,name in enumerate(names(field['name'],field['shape'])):
            assert sym['main.'+name]==start+offset+1,('public layout mismatch',name,sym['main.'+name],start+offset+1)
            value=int(public[start+offset]);value=value-FIELD if field['signed'] and value>FIELD//2 else value
            vals.append(str(value))
        result[field['name']]=reshape(vals,field['shape'])
    dump(HERE/'public_from_witness.json',public)
    dump(HERE/'decoded_public.json',{'source':'actual diagnostic circuit public witness prefix; not recomputed Python stages',
        'proof_verified':False,'input_file':str(input_path),'input_sha256':hashlib.sha256(input_path.read_bytes()).hexdigest(),
        'data':result})
    validate(result,input_path)
    write_csvs(result,input_path)
    print('Decoded exact public values and CSVs',flush=True)

def write_csv(path,rows):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)

def write_csvs(d,input_path):
    selected=int(d['selectedSubcarrier']);band=int(d['estimatedFrequencyBin']);global_=int(d['globalPeakFrequencyBin'])
    preprocess=json.loads((BASE/'lomb/preprocessing.json').read_text())
    window=input_path.stem.rsplit('_sc',1)[0]
    mapping=next(x for x in preprocess if x['window_id']==window)['subcarrier_indices']
    rows=[]
    for i in range(64):
        rows.append({'sample':i,'time_seconds':int(d['timestampsMs'][i])/1000,'selected_local_sc':selected,
                     'source_tone_index':mapping[selected], 'signed_i':d['debugSignedI'][i][selected],
                     'signed_q':d['debugSignedQ'][i][selected],'magnitude_squared':d['debugMagnitudeSquared'][i][selected],
                     'centered_scaled_by_64':d['debugCentered'][i][selected],
                     'centered_display_divide64':int(d['debugCentered'][i][selected])/64,
                     'cos_basis_at_band_peak':d['debugCosBasis'][band][i],
                     'sin_basis_at_band_peak':d['debugSinBasis'][band][i]})
    write_csv(HERE/'selected_waveform.csv',rows)
    rows=[]
    for sc in range(8):
        for f in range(32):
            num=int(d['debugNumerator'][sc][f]);den=int(d['debugDenominator'][sc][f])
            rows.append({'local_sc':sc,'source_tone_index':mapping[sc],'is_selected':int(sc==selected),'bin':f,
                         'bpm':(127+29*f)/2540*60,'cos_projection':d['debugCosProjection'][sc][f],
                         'sin_projection':d['debugSinProjection'][sc][f],'numerator_exact':str(num),'denominator_exact':str(den),
                         'normalized_score_display_only':num/den,'is_band_peak':int(f==int(d['debugBandPeak'][sc])),
                         'is_global_peak':int(f==int(d['debugGlobalPeak'][sc]))})
    write_csv(HERE/'spectra_all_sc.csv',rows)
    write_csv(HERE/'selected_spectrum.csv',[r for r in rows if r['is_selected']])
    dump(HERE/'selection.json',{'window_id':window,'selected_local_sc':selected,'source_tone_index':mapping[selected],
         'source_indices_first8':mapping[:8],'band_peak_bin':band,'global_peak_bin':global_,
         'normalized_score_note':'CSV ratio numerator/denominator is computed OFF CIRCUIT for display; exact public numerator and denominator remain in CSV/JSON.',
         'centered_display_note':'The circuit exposes64*mag2-sum(mag2); divide64 in CSV is display-only.'})

def validate(d,input_path):
    import numpy as np
    sys.path.insert(0,str(BASE/'lomb'))
    from reference import estimate_integer,basis
    inp=json.loads(input_path.read_text());ref=estimate_integer(inp)
    for k in ['isNormal','selectedSubcarrier','estimatedFrequencyBin','globalPeakFrequencyBin']:assert int(d[k])==ref[k]
    si=np.asarray(inp['csiI'],dtype=object)-2048;sq=np.asarray(inp['csiQ'],dtype=object)-2048
    mag=si*si+sq*sq;y=64*mag-mag.sum(axis=0);c,s=basis(inp['timestampsMs'])
    expected={'debugSignedI':si,'debugSignedQ':sq,'debugMagnitudeSquared':mag,'debugCentered':y,
              'debugSignalNorm':(y*y).sum(axis=0),'debugCosBasis':c,'debugSinBasis':s,
              'debugCosProjection':(c@y).T,'debugSinProjection':(s@y).T}
    cc=(c*c).sum(axis=1);ss=(s*s).sum(axis=1);cs=(c*s).sum(axis=1);det=cc*ss-cs*cs
    cp=c@y;sp=s@y;yy=(y*y).sum(axis=0)
    expected.update(debugCosNorm=cc,debugSinNorm=ss,debugCrossNorm=cs,debugDeterminant=det,
        debugNumerator=(ss[:,None]*cp*cp-2*cs[:,None]*cp*sp+cc[:,None]*sp*sp).T,
        debugDenominator=(det[:,None]*yy[None,:]).T)
    for name,array in expected.items():
        actual=np.asarray(d[name],dtype=object);actual=np.vectorize(int,otypes=[object])(actual)
        assert np.array_equal(actual,array),name
    for sc in range(8):
        one={**inp,'csiI':[[x[sc]] for x in inp['csiI']],'csiQ':[[x[sc]] for x in inp['csiQ']]}
        out=estimate_integer(one,(c,s))
        assert int(d['debugBandPeak'][sc])==out['estimatedFrequencyBin']
        assert int(d['debugGlobalPeak'][sc])==out['globalPeakFrequencyBin']
    dump(HERE/'validation.json',{'status':'PASS','actual_public_values_checked':sum(product(x[1]) for x in SHAPES)-1,
         'commitment_note':'Commitment copied from actual circuit output; independently bound by circuit witness/proof checks.',
         'checks':['public .sym indices and prefix order','field modulus','all stage integer values against independent reference','all8 local peak/global bins','original4 estimator outputs'],
         'reference_used_for_validation_only':True})

def witness_(input_path):
    (HERE/'input.json').write_text(input_path.read_text())
    seconds=command(['node',BUILD/'diagnostic_js/generate_witness.js',BUILD/'diagnostic_js/diagnostic.wasm',HERE/'input.json',BUILD/'witness.wtns'],'witness.log')
    dump(HERE/'witness_metrics.json',{'witness_process_seconds':seconds,'input_source':str(input_path),'includes':'Node startup, WASM load, witness compute and write'})
    decode_public(input_path)

def prove_(ptau):
    snark=ROOT/'zkp/node_modules/.bin/snarkjs'
    metrics={'ptau':str(ptau),'kind':'diagnostic circuit proof; stage values intentionally public; not production timing benchmark'}
    metrics['witness_constraint_check_seconds']=command([snark,'wtns','check',BUILD/'diagnostic.r1cs',BUILD/'witness.wtns'],'witness_check.log')
    metrics['setup_seconds']=command([snark,'groth16','setup',BUILD/'diagnostic.r1cs',ptau,BUILD/'initial.zkey'],'setup.log')
    metrics['contribution_seconds']=command([snark,'zkey','contribute',BUILD/'initial.zkey',BUILD/'diagnostic.zkey','--name=public-stage diagnostic','-e='+secrets.token_hex(32)],'contribute.log')
    command([snark,'zkey','export','verificationkey',BUILD/'diagnostic.zkey',HERE/'verification_key.json'],'vkey.log')
    metrics['prove_seconds']=command([snark,'groth16','prove',BUILD/'diagnostic.zkey',BUILD/'witness.wtns',HERE/'proof.json',HERE/'public.json'],'prove.log')
    metrics['verify_seconds']=command([snark,'groth16','verify',HERE/'verification_key.json',HERE/'public.json',HERE/'proof.json'],'verify.log')
    metrics['verified']='OK!' in (HERE/'verify.log').read_text()
    assert metrics['verified']
    assert json.loads((HERE/'public.json').read_text())==json.loads((HERE/'public_from_witness.json').read_text())
    metrics['proof_public_equals_decoded_public']=True
    # Negative verification: preserve the proof and change one PUBLIC stage value.
    schema=json.loads((HERE/'public_schema.json').read_text())
    field=next(f for f in schema['fields'] if f['name']=='debugMagnitudeSquared')
    index=field['public_start_zero_based']
    tampered=json.loads((HERE/'public.json').read_text())
    before=tampered[index]
    tampered[index]=str((int(before)+1)%FIELD)
    dump(HERE/'public_tampered.json',tampered)
    start=time.perf_counter()
    invalid=subprocess.run(list(map(str,[snark,'groth16','verify',HERE/'verification_key.json',HERE/'public_tampered.json',HERE/'proof.json'])),capture_output=True,text=True,timeout=120)
    invalid_log=invalid.stdout+invalid.stderr
    (HERE/'verify_tampered.log').write_text(invalid_log)
    tamper={'modified_signal':'debugMagnitudeSquared[0][0]',
            'public_index_zero_based':index,'original':before,'tampered':tampered[index],
            'same_proof':'proof.json','verify_seconds':time.perf_counter()-start,
            'returncode':invalid.returncode,
            'rejected_as_invalid_proof':'invalid proof' in invalid_log.lower() and 'OK!' not in invalid_log}
    dump(HERE/'tamper_validation.json',tamper)
    assert tamper['rejected_as_invalid_proof'], 'Tampered stage public value was not explicitly rejected as invalid proof'
    metrics['tampered_intermediate_public_value_rejected']=True
    dump(HERE/'proof_metrics.json',metrics)
    decoded=json.loads((HERE/'decoded_public.json').read_text());decoded['proof_verified']=True
    decoded['proof_file']='proof.json';decoded['public_file']='public.json';dump(HERE/'decoded_public.json',decoded)
    print(metrics,flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--compile',action='store_true');parser.add_argument('--witness',action='store_true');parser.add_argument('--prove',action='store_true');parser.add_argument('--ptau',type=Path)
    parser.add_argument('--input',type=Path,default=BASE/'lomb/inputs/csi_20260526_034004_w0_sc8.json')
    args=parser.parse_args();generate()
    if args.compile:compile_()
    if args.witness:witness_(args.input)
    if args.prove:
        if args.ptau is None:parser.error('--prove requires --ptau')
        prove_(args.ptau)
if __name__=='__main__':main()
