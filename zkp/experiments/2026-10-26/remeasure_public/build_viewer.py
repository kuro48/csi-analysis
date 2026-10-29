"""Publish only locally verified same-run proof/public/trace bindings, never legacy traces."""
import hashlib,html,json,math
from pathlib import Path
HERE=Path(__file__).resolve().parent
OUT=HERE/'view_data';OUT.mkdir(exist_ok=True)
FIELD=21888242871839275222246405745257275088548364400416034343698204186575808495617

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return str(p.resolve().relative_to(HERE.resolve()))
def check(p,h):
    assert p.exists() and sha(p)==h, f'Artifact hash mismatch: {p}'

def decoded(public,fields,vmd=False):
    def shape(a,dims):
        if not dims:return a[0]
        if len(dims)==1:return a
        stride=math.prod(dims[1:]);return [shape(a[i*stride:(i+1)*stride],dims[1:]) for i in range(dims[0])]
    result={}
    for g in fields:
        start=g.get('public_start_index_zero_based') if vmd else g.get('public_start_zero_based')
        dims=g['shape'];count=math.prod(dims) if dims else 1
        values=[int(v) for v in public[start:start+count]]
        assert len(values)==count and all(0<=v<FIELD for v in values)
        signed=g.get('decode_signed') if vmd else g.get('signed')
        if signed:values=[v-FIELD if v>FIELD//2 else v for v in values]
        result[g['name']]=shape(values,dims)
    return result

def numeric_tree(x):
    if isinstance(x,list):return [numeric_tree(v) for v in x]
    if isinstance(x,dict):return {k:numeric_tree(v) for k,v in x.items()}
    return int(x)

runs=[];statuses=[]
for cfg in read(HERE/'vmd/plan.json')['configurations']:
    d=HERE/'vmd'/cfg['id'];state=read(d/'status.json') if (d/'status.json').exists() else {'status':'not_started'}
    statuses.append(dict(method='VMD',config=cfg['id'],status=state['status'],reason=state.get('reason',''),stage=state.get('active_stage'),proofs=0,planned=10))
for mf in sorted((HERE/'vmd').glob('*/runs/*/manifest.json')):
    m=read(mf)
    if not m.get('verified'):continue
    d=mf.parent;cfg=d.parents[1];schema=read(cfg/'schema.json')
    assert m['status']=='verified' and m['tamper_rejected'] and m['public_schema_verified']
    for file,h in m['artifact_sha256'].items():check(d/file,h)
    check(cfg/schema['circuit'],m['source_sha256']);vk=(d/m['vkey_path']).resolve();check(vk,m['vkey_sha256'])
    check(d/'public.json',m['public_sha256']);check(d/'proof.json',m['proof_sha256'])
    tr=read(d/'trace.json');assert tr['binding']['proof_sha256']==m['proof_sha256'] and tr['public_sha256']==m['public_sha256']
    actual=decoded(read(d/'public.json'),schema['groups'],True)
    assert actual['debugWaveform']==tr['input_waveform_public']
    assert actual['debugDftReal']==tr['dft']['real_coefficients_public'] and actual['debugDftImag']==tr['dft']['positive_sine_coefficients_public']
    assert actual['debugCenters']==tr['center_trajectory_public']
    assert actual['estimatedFrequencyBin']*120/128==m['result']['bpm']==tr['result']['bpm']
    for r,stage in enumerate(tr['stages']):
        for k,mode in enumerate(stage['modes']):
            assert actual['debugModeReal'][r][k]==mode['real_coefficients_public']
            assert actual['debugModeImag'][r][k]==mode['positive_sine_coefficients_public']
    row=dict(id='vmd-'+m['config_id']+'-'+m['run_id'],method='VMD',config=m['config_id'],window=m['window'],repeat=m['repeat'],
       seconds=m['prove']['wall_seconds'],public=rel(d/'public.json'),proof=rel(d/'proof.json'),vkey=rel(vk),manifest=rel(mf),
       public_sha256=m['public_sha256'],proof_sha256=m['proof_sha256'],bpm=m['result']['bpm'])
    row['script']='view_data/'+row['id']+'.js'
    (HERE/row['script']).write_text('window.receiveProofTrace('+json.dumps(dict(record=row,trace=tr),ensure_ascii=False,separators=(',',':'))+');\n')
    runs.append(row)
for count in [1,2,4,8,16,32]:
    cfg=HERE/'lomb/configs'/f'sc{count}';state=read(cfg/'status.json') if (cfg/'status.json').exists() else {'status':'not_started'}
    statuses.append(dict(method='LS',config=f'sc{count}',status=state['status'],reason=state.get('failure_reason',''),stage=state.get('active_stage'),proofs=0,planned=10))
for mf in sorted((HERE/'lomb/runs').glob('*/manifest.json')):
    m=read(mf)
    if not m.get('verified'):continue
    artifacts=m['artifacts']
    def artifact(key):
        a=artifacts[key];p=HERE/'lomb'/a['path'];check(p,a['sha256']);return p
    public=artifact('public');proof=artifact('proof');vk=artifact('verification_key')
    artifact('input');artifact('source');dp=artifact('decoded_public');artifact('trace')
    assert m['decoded_from']==artifacts['public']
    dc=read(dp);assert dc['decoded_from']==artifacts['public']
    schema=read(artifact('source_schema'));fields=schema['fields']
    actual=decoded(read(public),fields)
    assert actual==numeric_tree(dc['data'])
    row=dict(id=m['run_id'],method='LS',config=m['config_id'],window=m['window_id'],repeat=m['repeat_id'],
       seconds=m['timings']['prove_seconds'],public=rel(public),proof=rel(proof),vkey=rel(vk),manifest=rel(mf),
       public_sha256=artifacts['public']['sha256'],proof_sha256=artifacts['proof']['sha256'],
       bpm=(127+29*actual['estimatedFrequencyBin'])/2540*60)
    row['script']='view_data/'+row['id']+'.js'
    (HERE/row['script']).write_text('window.receiveProofTrace('+json.dumps(dict(record=row,data=dc['data'],mapping=m['physical_tone_mapping']),ensure_ascii=False,separators=(',',':'))+');\n')
    runs.append(row)
for row in statuses:row['proofs']=sum(r['method']==row['method'] and r['config']==row['config'] for r in runs)
rows=''.join('<tr>'+''.join(f'<td>{html.escape(str(r[k] or "—"))}</td>' for k in ['method','config','status','proofs'])+'</tr>' for r in statuses)
doc=(HERE/'viewer_template.html').read_text().replace('__INDEX__',json.dumps(runs,ensure_ascii=False)).replace('__STATUS_ROWS__',rows).replace('__COUNT__',str(len(runs)))
(HERE/'index.html').write_text(doc)
(HERE/'viewer_validation.json').write_text(json.dumps({'verified_runs_shown':len(runs),'proof_public_trace_bindings_checked':True,'all_displayed_coefficients_match_actual_public':True,'planned_configurations':43,'planned_proofs':430,'runs':runs,'configuration_status':statuses},ensure_ascii=False,indent=2)+'\n')
print('Verified same-run proof views:',len(runs))
